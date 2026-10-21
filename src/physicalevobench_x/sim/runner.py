"""Real development runner. Requires a live SimulationAppContext.

One environment per episode keeps condition dynamics isolated until a reusable
reset implementation has physical validation. This is deliberately conservative
and must be timed before any pilot; it is not a claimed throughput optimization.
"""
import time
import uuid
from pathlib import Path
import numpy as np
import torch
from isaaclab_arena.environments.arena_env_builder import ArenaEnvBuilder
from isaaclab_arena.environments.arena_env_builder_cfg import ArenaEnvBuilderCfg
from .arena_factory import StableLiftEnvironment, StableLiftEnvironmentCfg
from .state_reader import array
from ..control.adapter import EmbodimentAdapter
from ..control.grasp_lift_executor import GraspLiftExecutor
from ..core.schemas import EpisodeResult
from ..core.hashing import file_digest, write_json


class PhysXRunner:
    def __init__(self, embodiment, output):
        self.embodiment, self.output = embodiment, Path(output)
        self.output.mkdir(parents=True,exist_ok=True)

    def run(self, *, skill, condition, phase, candidate_index, attempt_index):
        started=time.monotonic()
        episode_id=uuid.uuid4().hex
        axis=(0.,0.,0.,1.) if self.embodiment=='franka_panda' else (0.,2**-.5,0.,2**-.5)
        arena=StableLiftEnvironment().build(StableLiftEnvironmentCfg(embodiment=self.embodiment,
            axis_mapping_xyzw=axis, mass_kg=condition['mass_kg'],offset_xy_m=tuple(condition['offset_xy_m']),
            yaw_rad=condition['yaw_rad']))
        env,cfg=ArenaEnvBuilder(arena,ArenaEnvBuilderCfg(num_envs=1,solve_relations=False,
            resolve_on_reset=False,seed=condition['reset_seed'],mimic=False)).make_registered_and_return_cfg()
        base=env.unwrapped
        steps, states, actions = 0, [], []
        try:
            if abs(base.physics_dt-.005)>1e-9 or abs(base.step_dt-.02)>1e-9:
                raise RuntimeError('Control rate does not match lock')
            env.reset(seed=condition['reset_seed'])
            task,reader=arena.task,arena.task.reader
            task.episode_id=episode_id
            task.last_tick=None
            task.last_episode_step=-1
            task.ready=False
            if base.action_manager.total_action_dim != 7:
                raise RuntimeError('Native action dimension/order changed')
            mass=array(base.scene['pebx_object'].data.body_mass).reshape(-1)
            if not np.allclose(mass,condition['mass_kg'],atol=1e-5):
                raise RuntimeError('Mass backend readback mismatch')
            executor,adapter=GraspLiftExecutor(),EmbodimentAdapter(self.embodiment)
            open_action=np.zeros(7)
            open_action[-1]=1. if self.embodiment=='franka_panda' else 0.
            initial=None
            while steps < 780:
                obs=reader.read(base,episode_id)
                if obs.sim_time_s >= .5-1e-9 and initial is None:
                    initial=obs
                    expected=np.array([.5+condition['offset_xy_m'][0],condition['offset_xy_m'][1],.0325])
                    if np.linalg.norm(np.asarray(obs.object_pose_w.position_m)-expected) > .01:
                        raise RuntimeError('INVALID_RESET: object position failed settle readback')
                    executor.reset(skill,obs)
                    task.judge.reset(obs)
                    task.ready=True
                if initial is None:
                    action=open_action.copy()
                else:
                    cmd=executor.step(obs)
                    action=adapter.encode(cmd,reader.root_w,reader.control_w,reader.control_to_tcp)
                states.append(obs.model_dump())
                actions.append(action.copy())
                _,_,terminated,truncated,_=env.step(torch.as_tensor(action,device=base.device,dtype=torch.float32)[None,:])
                steps+=1
                if bool(terminated.any() or truncated.any()):
                    break
            evidence=task.terminal_evidence
            if evidence is None:
                raise RuntimeError('Missing pre-reset terminal evidence')
            trajectory=self.output/(episode_id+'.npz')
            np.savez_compressed(trajectory,sim_time_s=np.array([s['sim_time_s'] for s in states]),
                object_position_m=np.array([s['object_pose_w']['position_m'] for s in states]),
                tcp_position_m=np.array([s['tcp_pose_w']['position_m'] for s in states]),
                native_actions=np.asarray(actions))
            write_json(self.output/(episode_id+'.json'),dict(initial=initial.model_dump(),terminal=evidence,
                embodiment=self.embodiment,condition=condition,mass_readback_kg=mass.tolist(),
                requested_skill=skill.model_dump(),stage_times=executor.stage_times,
                development_unvalidated=True))
            return EpisodeResult(episode_id=episode_id,condition_id=condition['condition_id'],split=condition['split'],
                phase=phase,candidate_index=candidate_index,skill_hash=skill.semantic_hash,backend='physx',
                attempt_index=attempt_index,simulator_steps=steps*4,sim_time_s=steps*.02,
                wall_time_s=time.monotonic()-started,trajectory_path=str(trajectory),
                trajectory_sha256=file_digest(trajectory),**evidence['result'])
        finally:
            env.close()
