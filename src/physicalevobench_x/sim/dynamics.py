"""Development-only free-body mass/inertia/readback and impulse/reset audit."""
from pathlib import Path
import numpy as np
import torch
from isaaclab_arena.environments.arena_env_builder import ArenaEnvBuilder
from isaaclab_arena.environments.arena_env_builder_cfg import ArenaEnvBuilderCfg
from isaaclab_arena.utils.isaaclab_utils.simulation_app import teardown_simulation_app
from .arena_factory import StableLiftEnvironment, StableLiftEnvironmentCfg
from .state_reader import array
from ..core.hashing import write_json


@torch.inference_mode()
def dynamics_check(embodiment, output):
    output=Path(output)
    output.mkdir(parents=True,exist_ok=False)
    axis=(0.,0.,0.,1.) if embodiment=='franka_panda' else (0.,2**-.5,0.,2**-.5)
    rows=[]
    for mass in (.1,.5,.1):
        _isolated_mass(embodiment,axis,mass,output,rows)
    replay_ok=abs(rows[0]['actual_delta_vx_mps']-rows[2]['actual_delta_vx_mps'])<1e-5
    report=dict(backend='physx',embodiment=embodiment,
        status='GPU_VERIFIED' if all(r['passed'] for r in rows) and replay_ok else 'GPU_CHECK_FAILED',
        tests=rows,low_high_low_reset_replay_passed=replay_ok,
        note='Independent scenes reproduce the production runner condition-isolation strategy',formal_result_eligible=False)
    write_json(output/'dynamics.json',report)
    return report


@torch.inference_mode()
def _isolated_mass(embodiment,axis,mass,output,rows):
    import warp as wp
    arena=StableLiftEnvironment().build(StableLiftEnvironmentCfg(embodiment=embodiment,axis_mapping_xyzw=axis,mass_kg=mass))
    env,_=ArenaEnvBuilder(arena,ArenaEnvBuilderCfg(num_envs=1,solve_relations=False,resolve_on_reset=False,
        recorder_dataset_export_dir_path=str(output/('arena_'+str(len(rows)))),recorder_dataset_filename='dynamics')).make_registered_and_return_cfg()
    base=env.unwrapped
    base.pebx_task=arena.task
    cube=base.scene['pebx_object']
    try:
        env.reset(seed=42)
        arena.task.ready=False
        arena.task.last_tick=None
        pose=torch.tensor([[.7,.2,.3,0.,0.,0.,1.]],device=base.device)
        cube.write_root_pose_to_sim_index(root_pose=pose)
        cube.write_root_velocity_to_sim_index(root_velocity=torch.zeros((1,6),device=base.device))
        size=np.array([.045,.045,.065])
        diag=mass*np.array([size[1]**2+size[2]**2,size[0]**2+size[2]**2,size[0]**2+size[1]**2])/12
        inertia=torch.tensor(np.diag(diag).reshape(1,1,9),dtype=torch.float32,device=base.device)
        wp.synchronize()
        raw_mass=cube.root_view.get_masses()
        wp.synchronize()
        mass_readback=array(raw_mass).reshape(-1).tolist()
        raw_inertia=cube.root_view.get_inertias()
        wp.synchronize()
        inertia_readback=array(raw_inertia).reshape(3,3).tolist()
        raw_material=cube.root_view.get_material_properties()
        wp.synchronize()
        material=array(raw_material).tolist()
        initial_velocity=array(cube.data.root_lin_vel_w)[0].copy()
        force=torch.tensor([[[2.,0.,0.]]],device=base.device)
        zero=torch.zeros_like(force)
        cube.permanent_wrench_composer.reset()
        cube.permanent_wrench_composer.add_forces_and_torques(force,zero,is_global=True)
        action=torch.zeros((1,7),device=base.device)
        action[:,-1]=1. if embodiment=='franka_panda' else 0.
        env.step(action)
        velocity=array(cube.data.root_lin_vel_w)[0]
        cube.permanent_wrench_composer.reset()
        expected=2.*base.step_dt/mass
        dv=float(velocity[0]-initial_velocity[0])
        rows.append(dict(requested_mass_kg=mass,backend_mass_kg=mass_readback,
            backend_inertia=inertia_readback,expected_inertia=np.diag(diag).tolist(),backend_material=material,
            force_N=[2.,0.,0.],duration_s=base.step_dt,initial_velocity_mps=initial_velocity.tolist(),
            final_velocity_mps=velocity.tolist(),expected_delta_vx_mps=expected,actual_delta_vx_mps=dv,
            passed=bool(np.allclose(mass_readback,mass,atol=1e-6) and np.allclose(inertia_readback,np.diag(diag),atol=1e-8)
                and np.allclose(np.asarray(material)[...,:3],[1.,1.,0.],atol=1e-6)
                and abs(dv-expected)<=.02*expected)))
        write_json(output/'partial.json',rows)
    finally:
        env.close()
        teardown_simulation_app()
