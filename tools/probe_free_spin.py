"""Native free-flight angular-velocity calibration; no upstream edits."""
import argparse
import json
from pathlib import Path
import numpy as np
from state_consistency_metrics import angular_pose_increments
from physicalevobench_x.core.hashing import append_json,write_json,file_digest


def run(output):
    output.mkdir(parents=True,exist_ok=False)
    write_json(output/'inputs.json',dict(angular_velocity_command_radps=[0.,0.,.2],physics_dt_s=.005,
        steps=20,initial_position_m=[.7,.2,.4],mass_kg=.2,formal_result_eligible=False,
        scope='Evaluator diagnostic free flight; not task-learning or transfer evidence',tool_sha256=file_digest(__file__)))
    from isaaclab_arena.cli.isaaclab_arena_cli import get_isaaclab_arena_cli_parser
    from isaaclab_arena.utils.isaaclab_utils.simulation_app import SimulationAppContext
    with SimulationAppContext(get_isaaclab_arena_cli_parser().parse_args([])):
        import torch
        from isaaclab_arena.environments.arena_env_builder import ArenaEnvBuilder
        from isaaclab_arena.environments.arena_env_builder_cfg import ArenaEnvBuilderCfg
        from physicalevobench_x.sim.arena_factory import StableLiftEnvironment,StableLiftEnvironmentCfg
        from physicalevobench_x.sim.state_reader import array
        arena=StableLiftEnvironment().build(StableLiftEnvironmentCfg(embodiment='franka_panda',
            axis_mapping_xyzw=(0.,0.,0.,1.),mass_kg=.2))
        env,_=ArenaEnvBuilder(arena,ArenaEnvBuilderCfg(num_envs=1,solve_relations=False,resolve_on_reset=False,
            recorder_dataset_export_dir_path=str(output/'arena'),recorder_dataset_filename='spin')).make_registered_and_return_cfg()
        base=env.unwrapped;base.pebx_task=arena.task
        rows=[]
        try:
            env.reset(seed=710025)
            cube=base.scene['pebx_object']
            cube.write_root_pose_to_sim_index(root_pose=torch.tensor([[.7,.2,.4,0.,0.,0.,1.]],device=base.device))
            cube.write_root_velocity_to_sim_index(root_velocity=torch.tensor([[0.,0.,0.,0.,0.,.2]],device=base.device))
            for index in range(21):
                row=dict(time_s=index*.005,pose=array(cube.root_view.get_transforms())[0].tolist(),
                    raw_velocity=array(cube.root_view.get_velocities())[0].tolist(),
                    api_angular=array(base.arena_world.get_root_angular_velocity_w('pebx_object'))[0].tolist())
                rows.append(row);append_json(output/'samples.jsonl',row)
                if index<20:
                    base.sim.step(render=False);base.scene.update(dt=.005)
        finally:env.close()
        derived=angular_pose_increments([r['time_s'] for r in rows],[r['pose'][3:] for r in rows])
        report=dict(status='FREE_SPIN_CALIBRATION_COMPLETE',formal_result_eligible=False,
            samples=len(rows),pose_derived_angular_z_median_radps=float(np.median(derived[:,2])),
            raw_angular_z_median_radps=float(np.median([r['raw_velocity'][5] for r in rows])),
            max_api_raw_angular_difference=float(max(np.linalg.norm(np.array(r['api_angular'])-
                np.array(r['raw_velocity'][3:])) for r in rows)),
            minimum_height_m=min(r['pose'][2] for r in rows),
            evidence_sha256=file_digest(output/'samples.jsonl'))
        write_json(output/'report.json',report);print(json.dumps(report))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();run(args.output.resolve())
