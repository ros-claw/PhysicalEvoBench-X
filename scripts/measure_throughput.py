"""Required 100-episode per-body timing before scheduling the formal pilot."""
import argparse
import json
import time
from pathlib import Path
import numpy as np
from physicalevobench_x.core.hashing import write_json, append_json
from physicalevobench_x.core.conditions import generate
from physicalevobench_x.core.schemas import SkillSpec


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--embodiment',choices=['franka_panda','franka_robotiq'],required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--episodes',type=int,default=100)
    a=p.parse_args()
    if a.episodes<1:
        raise ValueError('Positive episode count required')
    a.output.mkdir(parents=True,exist_ok=False)
    conditions=generate(880019,{'dev':a.episodes})['dev']
    write_json(a.output/'private_conditions.json',conditions)
    startup=time.monotonic()
    from isaaclab_arena.cli.isaaclab_arena_cli import get_isaaclab_arena_cli_parser
    from isaaclab_arena.utils.isaaclab_utils.simulation_app import SimulationAppContext
    with SimulationAppContext(get_isaaclab_arena_cli_parser().parse_args([])):
        app_startup_s=time.monotonic()-startup
        from physicalevobench_x.sim.runner import PhysXRunner
        runner=PhysXRunner(a.embodiment,a.output/'trajectories')
        results,valid,timings=[],[],[]
        retries=0
        for condition in conditions:
            for attempt in range(2):
                import shutil
                if shutil.disk_usage(a.output).free<2*1024**3:
                    raise RuntimeError('DISK_LIMIT: preserve partial throughput measurements')
                result=runner.run(skill=SkillSpec.initial(),condition=condition,phase='calibration',candidate_index=0,attempt_index=attempt)
                append_json(a.output/'episode_results.jsonl',result)
                results.append(result)
                if not result.infra_failure:
                    valid.append(result)
                    metadata=json.loads((runner.output/(result.episode_id+'.json')).read_text())
                    timings.append(metadata.get('timings',{}))
                    break
                if attempt==1 or retries>=2:
                    write_json(a.output/'status.json',dict(status='INCOMPLETE',completed=len(valid),attempts=len(results)))
                    raise RuntimeError('Throughput infrastructure retry limit reached')
                retries+=1
            write_json(a.output/'progress.json',dict(completed=len(valid),planned=a.episodes,actual_attempts=len(results)))
        def distribution(values):
            return dict(median_s=float(np.median(values)),p95_s=float(np.percentile(values,95,method='linear')),
                        minimum_s=float(min(values)),maximum_s=float(max(values)))
        phase_names=set.intersection(*(set(t) for t in timings)) if timings else set()
        report=dict(backend='physx',status='GPU_VERIFIED' if len(valid)==100 else 'DEVELOPMENT_MEASUREMENTS_COMPLETE',
            embodiment=a.embodiment,completed_episodes=len(valid),physical_attempts=len(results),
            app_startup_s=app_startup_s,episode_wall=distribution([r.wall_time_s for r in valid]),
            phases={key:distribution([t[key] for t in timings]) for key in sorted(phase_names)},
            simulator_time_s=sum(r.sim_time_s for r in results),total_episode_wall_time_s=sum(r.wall_time_s for r in results),
            successes=sum(r.task_success for r in valid),formal_result_eligible=False,
            note='Shared GPU wall timing includes scene construction/reset/control/recording/teardown, not exclusive GPU utilization.')
        write_json(a.output/'throughput.json',report)


if __name__=='__main__':
    main()
