"""Independent actual replay check for reset/condition/skill determinism."""
import argparse
from pathlib import Path
import numpy as np
from physicalevobench_x.core.hashing import write_json, append_json, digest
from physicalevobench_x.core.conditions import generate
from physicalevobench_x.core.schemas import SkillSpec


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--embodiment',choices=['franka_panda','franka_robotiq'],required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    a.output.mkdir(parents=True,exist_ok=False)
    condition=generate(99123,{'dev':1})['dev'][0]
    skill=SkillSpec.initial()
    from isaaclab_arena.cli.isaaclab_arena_cli import get_isaaclab_arena_cli_parser
    from isaaclab_arena.utils.isaaclab_utils.simulation_app import SimulationAppContext
    with SimulationAppContext(get_isaaclab_arena_cli_parser().parse_args([])):
        from physicalevobench_x.sim.runner import PhysXRunner
        runner=PhysXRunner(a.embodiment,a.output/'trajectories')
        results=[runner.run(skill=skill,condition=condition,phase='calibration',candidate_index=0,attempt_index=0)
                 for _ in range(2)]
        for result in results:
            append_json(a.output/'episode_results.jsonl',result)
        first,second=[np.load(r.trajectory_path) for r in results]
        count=min(len(first['sim_time_s']),len(second['sim_time_s']))
        object_error=float(np.linalg.norm(first['object_position_m'][:count]-second['object_position_m'][:count],axis=1).max())
        tcp_error=float(np.linalg.norm(first['tcp_position_m'][:count]-second['tcp_position_m'][:count],axis=1).max())
        passed=(not any(r.infra_failure for r in results)
            and results[0].task_success==results[1].task_success
            and abs(results[0].completion_time_s-results[1].completion_time_s)<=.04
            and object_error<=.002 and tcp_error<=.002)
        write_json(a.output/'replay.json',dict(backend='physx',status='GPU_VERIFIED' if passed else 'GPU_CHECK_FAILED',
            embodiment=a.embodiment,condition_hash=digest(condition),skill_hash=skill.semantic_hash,
            compared_samples=count,maximum_object_position_error_m=object_error,maximum_tcp_position_error_m=tcp_error,
            paired_replays=[r.model_dump() for r in results],formal_result_eligible=False))


if __name__=='__main__':
    main()
