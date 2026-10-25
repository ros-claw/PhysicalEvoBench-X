"""Isolated native instrumentation: API velocities, direct PhysX, and pose increments.

The production source is unchanged. Runtime wrappers only collect state; this
probe is not a benchmark score or an accepted parameter intervention result.
"""
import argparse
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from physicalevobench_x.core.hashing import append_json,write_json,file_digest
from physicalevobench_x.core.schemas import SkillSpec


def run(output,study):
    data=json.loads((study/'plan.json').read_text())
    output.mkdir(parents=True,exist_ok=False)
    write_json(output/'inputs.json',dict(study_plan_sha256=file_digest(study/'plan.json'),
        diagnostic_tool_sha256=file_digest(__file__),condition=data['conditions'][0],
        skill=data['variants']['kimi_after'],formal_result_eligible=False,
        scope='Native state instrumentation on first predeclared development condition'))
    from isaaclab_arena.cli.isaaclab_arena_cli import get_isaaclab_arena_cli_parser
    from isaaclab_arena.utils.isaaclab_utils.simulation_app import SimulationAppContext
    with SimulationAppContext(get_isaaclab_arena_cli_parser().parse_args([])):
        import numpy as np
        from isaaclab_arena.environments.arena_env_builder import ArenaEnvBuilder
        from physicalevobench_x.sim.state_reader import StateReader,array
        from physicalevobench_x.sim.runner import PhysXRunner
        original_make=ArenaEnvBuilder.make_registered_and_return_cfg
        original_read=StateReader.read
        physics=[]
        controls=[]

        def instrumented_make(builder,*args,**kwargs):
            env,cfg=original_make(builder,*args,**kwargs)
            base=env.unwrapped
            if base._physics_handles_decimation:
                raise RuntimeError('Probe requires individually observable PhysX substeps')
            original_step=base.sim.step
            def step(*args,**kwargs):
                result=original_step(*args,**kwargs)
                obj=base.scene['pebx_object']
                row=dict(physics_step=base.sim.get_physics_step_count(),dt_s=base.physics_dt,
                    pose=array(obj.root_view.get_transforms())[0].tolist(),
                    raw_velocity=array(obj.root_view.get_velocities())[0].tolist())
                physics.append(row)
                append_json(output/'physics_samples.jsonl',row)
                return result
            base.sim.step=step
            return env,cfg

        def instrumented_read(reader,env,eid):
            obs=original_read(reader,env,eid)
            obj=env.scene['pebx_object']
            row=dict(time_s=obs.sim_time_s,reported_linear=obs.object_linear_velocity_w,
                     reported_angular=obs.object_angular_velocity_w,
                     raw_velocity=array(obj.root_view.get_velocities())[0].tolist())
            controls.append(row)
            append_json(output/'control_samples.jsonl',row)
            return obs

        ArenaEnvBuilder.make_registered_and_return_cfg=instrumented_make
        StateReader.read=instrumented_read
        try:
            runner=PhysXRunner('franka_panda',output/'trajectories')
            result=runner.run(skill=SkillSpec.model_validate(data['variants']['kimi_after']),
                condition=data['conditions'][0],phase='calibration',candidate_index=0,attempt_index=0)
            write_json(output/'episode_result.json',result)
        finally:
            ArenaEnvBuilder.make_registered_and_return_cfg=original_make
            StateReader.read=original_read
        if result.infra_failure:raise RuntimeError('Native instrumentation episode failed')
        q=np.array([p['pose'][3:] for p in physics]);q/=np.linalg.norm(q,axis=1)[:,None]
        omega=2*np.arccos(np.clip(np.abs(np.sum(q[1:]*q[:-1],axis=1)),0,1))/.005
        raw=np.array([p['raw_velocity'][3:] for p in physics])
        # Store, do not equate instantaneous velocity with integrated pose motion.
        report=dict(status='NATIVE_STATE_PROBE_COMPLETE',formal_result_eligible=False,
            episode_success=result.task_success,physics_samples=len(physics),control_reads=len(controls),
            max_api_raw_angular_difference=float(max(np.linalg.norm(np.array(c['reported_angular'])-
                np.array(c['raw_velocity'][3:])) for c in controls)),
            max_api_raw_linear_difference=float(max(np.linalg.norm(np.array(c['reported_linear'])-
                np.array(c['raw_velocity'][:3])) for c in controls)),
            raw_angular_norm_median=float(np.median(np.linalg.norm(raw,axis=1))),
            pose_increment_angular_median=float(np.median(omega)),
            note='Includes settle/motion; inspect stable elevated interval and signed substep sequences before attributing a cause.',
            evidence_files={str(p):file_digest(p) for p in output.glob('*.jsonl')})
        write_json(output/'report.json',report)
        print(json.dumps(report))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--study',type=Path,required=True)
    args=p.parse_args()
    run(args.output.resolve(),args.study.resolve())
