"""Physical open/close, world-axis translation and rotated-offset checks."""
import math
from pathlib import Path
import numpy as np
import torch
from isaaclab_arena.environments.arena_env_builder import ArenaEnvBuilder
from isaaclab_arena.environments.arena_env_builder_cfg import ArenaEnvBuilderCfg
from isaaclab_arena.utils.isaaclab_utils.simulation_app import teardown_simulation_app
from .arena_factory import StableLiftEnvironment, StableLiftEnvironmentCfg
from ..core.schemas import CanonicalCommand, Pose, Gripper
from ..core.hashing import append_json, write_json, file_digest
from ..control.adapter import EmbodimentAdapter
from ..control.geometry import angle, multiply


@torch.inference_mode()
def calibrate(embodiment, output):
    output=Path(output)
    output.mkdir(parents=True,exist_ok=False)
    axis=(0.,0.,0.,1.) if embodiment=='franka_panda' else (0.,2**-.5,0.,2**-.5)
    arena=StableLiftEnvironment().build(StableLiftEnvironmentCfg(embodiment=embodiment,axis_mapping_xyzw=axis))
    env,_=ArenaEnvBuilder(arena,ArenaEnvBuilderCfg(num_envs=1,solve_relations=False,resolve_on_reset=False,seed=42,
        recorder_dataset_export_dir_path=str(output/'arena'),recorder_dataset_filename='calibration')).make_registered_and_return_cfg()
    base=env.unwrapped
    base.pebx_task=arena.task
    reader,adapter=arena.task.reader,EmbodimentAdapter(embodiment)
    try:
        env.reset(seed=42)
        initial=reader.read(base,'calibration')
        reference=initial.tcp_pose_w
        def hold(target, gripper, steps):
            for _ in range(steps):
                obs=reader.read(base,'calibration')
                cmd=CanonicalCommand(tcp_pose_w=target,gripper=gripper)
                action=adapter.encode(cmd,reader.root_w,reader.control_w,reader.control_to_tcp)
                append_json(output/'trace.jsonl',dict(observation=obs.model_dump(),command=cmd.model_dump(mode='json'),
                    native_action=action.tolist()))
                _,_,terminated,truncated,_=env.step(torch.as_tensor(action,device=base.device,dtype=torch.float32)[None,:])
                if bool(terminated.any() or truncated.any()):
                    raise RuntimeError('Calibration terminated before plan completed')
            return reader.read(base,'calibration')
        opened=hold(reference,Gripper.OPEN,75)
        closed=hold(reference,Gripper.CLOSE,75)
        reopened=hold(reference,Gripper.OPEN,75)
        gaps=[o.gripper_opening_width_m for o in (opened,closed,reopened)]
        gripper_ok=gaps[0]>.06 and gaps[1]<.02 and gaps[2]>.06
        # Use the settled public TCP as an absolute world reference.
        reference=reopened.tcp_pose_w
        checks=[]
        for i,name in enumerate(('x','y','z')):
            goal=np.asarray(reference.position_m)+np.eye(3)[i]*.01
            target=Pose(position_m=tuple(goal),quaternion_xyzw=reference.quaternion_xyzw)
            result=hold(target,Gripper.OPEN,30)
            delta=np.asarray(result.tcp_pose_w.position_m)-reference.position_m
            error=float(np.linalg.norm(np.asarray(result.tcp_pose_w.position_m)-goal))
            checks.append(dict(axis=name,requested_delta_m=(np.eye(3)[i]*.01).tolist(),
                measured_delta_m=delta.tolist(),position_error_m=error,passed=bool(error<=.0025 and delta[i]>.0075)))
            hold(reference,Gripper.OPEN,30)
        yaw=(0.,0.,math.sin(.1/2),math.cos(.1/2))
        target=Pose(position_m=reference.position_m,quaternion_xyzw=tuple(multiply(yaw,reference.quaternion_xyzw)))
        rotated=hold(target,Gripper.OPEN,50)
        rotation_error=angle(rotated.tcp_pose_w.quaternion_xyzw,target.quaternion_xyzw)
        position_error=float(np.linalg.norm(np.asarray(rotated.tcp_pose_w.position_m)-reference.position_m))
        rotation_ok=rotation_error<=.02 and position_error<=.003
        hold(reference,Gripper.OPEN,50)
        report=dict(backend='physx',embodiment=embodiment,
            status='GPU_VERIFIED' if gripper_ok and all(c['passed'] for c in checks) and rotation_ok else 'GPU_CHECK_FAILED',
            gripper_open_closed_reopened_width_m=gaps,gripper_passed=gripper_ok,world_axes=checks,
            rotation=dict(requested_world_yaw_rad=.1,error_rad=rotation_error,tcp_position_drift_m=position_error,passed=rotation_ok),
            initial=initial.model_dump(),trace_sha256=file_digest(output/'trace.jsonl'),formal_result_eligible=False)
        write_json(output/'calibration.json',report)
        return report
    finally:
        env.close()
        teardown_simulation_app()
