"""Physical low/mid/high parameter consumption audit on one nominal condition.

Run with the native Arena interpreter and HEADLESS/EULA/GPU environment set as
in run_native.sh. This is development evidence, never formal transfer scoring.
"""
import argparse
import json
from pathlib import Path
import numpy as np


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--embodiment',choices=['franka_panda','franka_robotiq'],required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    from isaaclab_arena.cli.isaaclab_arena_cli import get_isaaclab_arena_cli_parser
    from isaaclab_arena.utils.isaaclab_utils.simulation_app import SimulationAppContext
    with SimulationAppContext(get_isaaclab_arena_cli_parser().parse_args([])):
        from physicalevobench_x.sim.runner import PhysXRunner
        from physicalevobench_x.core.schemas import BOUNDS,SkillSpec
        from physicalevobench_x.core.conditions import generate
        from physicalevobench_x.core.hashing import append_json,write_json,digest
        args.output.mkdir(parents=True,exist_ok=False)
        runner=PhysXRunner(args.embodiment,args.output/'trajectories')
        base_condition=generate(123,{'dev':1})['dev'][0]
        base_condition.update(offset_xy_m=[0.,0.],yaw_rad=0.,mass_kg=.2)
        results=[]
        for field,(lo,hi) in BOUNDS.items():
            for level,value in [('low',lo),('mid',(lo+hi)/2),('high',hi)]:
                data=SkillSpec.initial().model_dump()
                data['parameters'][field]=value
                skill=SkillSpec.model_validate(data)
                condition=dict(base_condition,condition_id=digest([args.embodiment,field,level])[:24])
                result=runner.run(skill=skill,condition=condition,phase='calibration',candidate_index=0,attempt_index=0)
                append_json(args.output/'episode_results.jsonl',result)
                trace=runner.output/(result.episode_id+'_trace.jsonl')
                rows=[json.loads(line) for line in trace.read_text().splitlines()]
                metadata=json.loads((runner.output/(result.episode_id+'.json')).read_text())
                lift=[r for r in rows if r['stage']=='LIFT']
                peak_speed=None
                if len(lift)>2:
                    times=np.array([r['observation']['sim_time_s'] for r in lift])
                    positions=np.array([r['observation']['tcp_pose_w']['position_m'] for r in lift])
                    peak_speed=float(np.linalg.norm(np.diff(positions,axis=0)/np.diff(times)[:,None],axis=1).max())
                item=dict(field=field,level=level,requested_value=value,episode_id=result.episode_id,
                    success=result.task_success,stage_times=metadata['stage_times'],actual_peak_lift_speed_mps=peak_speed,
                    minimum_actual_tcp_z_m=min(r['observation']['tcp_pose_w']['position_m'][2] for r in rows))
                append_json(args.output/'sensitivity_results.jsonl',item)
                results.append(item)
        # This report exposes the measured differences without claiming every parameter helps success.
        write_json(args.output/'sensitivity.json',dict(backend='physx',status='MEASUREMENTS_COMPLETE',
            embodiment=args.embodiment,planned_episodes=15,completed_episodes=len(results),measurements=results,
            formal_result_eligible=False,note='Inspect actual trajectories/timing for weak or ineffective dimensions before freeze'))


if __name__=='__main__':
    main()
