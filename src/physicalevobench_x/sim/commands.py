"""GPU CLI bridge. App starts once, simulation imports happen inside context."""
from pathlib import Path
from ..core.schemas import SkillSpec
from ..core.hashing import append_json, write_json


def execute(args):
    from isaaclab_arena.cli.isaaclab_arena_cli import get_isaaclab_arena_cli_parser
    from isaaclab_arena.utils.isaaclab_utils.simulation_app import SimulationAppContext
    startup=get_isaaclab_arena_cli_parser().parse_args([])
    with SimulationAppContext(startup):
        from .runner import PhysXRunner
        from ..core.conditions import generate
        from ..learners.random_search import RandomSearch
        from ..protocol.learning import learn
        from ..protocol.orchestration import transfer
        from ..core.hashing import file_digest
        output=Path(args.output).resolve()
        if output.exists():
            raise ValueError('Output exists; refusing to overwrite physical evidence')
        if args.command=='calibrate':
            from .calibration import calibrate
            return calibrate(args.embodiment,output)
        if args.command=='dynamics-check':
            from .dynamics import dynamics_check
            return dynamics_check(args.embodiment,output)
        if args.command=='evaluate':
            import json
            from ..protocol.evaluation import evaluate
            from ..core.conditions import validate_condition
            skill=SkillSpec.model_validate_json(args.skill.read_text())
            manifest=json.loads(args.conditions.read_text())
            conditions=manifest[args.split] if isinstance(manifest,dict) else manifest
            if not conditions or any(c['split']!=args.split for c in conditions):
                raise ValueError('Selected held-out manifest split mismatch')
            for condition in conditions:
                validate_condition(condition)
            output.mkdir(parents=True)
            runner=PhysXRunner(args.embodiment,output/'trajectories')
            records=evaluate(skill,conditions,runner,output/'episode_results.jsonl')
            summary=dict(status='EVALUATION_COMPLETE',backend='physx',episodes=len(records),
                successes=sum(r.task_success for r in records),skill_hash=skill.semantic_hash,formal_result_eligible=False)
            write_json(output/'summary.json',summary)
            return summary
        initial=SkillSpec.initial()
        if args.command=='smoke':
            output.mkdir(parents=True)
            runner=PhysXRunner(args.embodiment,output/'trajectories')
            for c in generate(args.seed,dict(dev=args.episodes))['dev']:
                # Nominal means fixed geometry/dynamics, no sensitivity perturbation yet.
                c.update(offset_xy_m=[0.,0.],yaw_rad=0.,mass_kg=.2)
                r=runner.run(skill=initial,condition=c,phase='calibration',candidate_index=0,attempt_index=0)
                append_json(output/'episode_results.jsonl',r)
            return dict(status='DEVELOPMENT_EPISODES_RECORDED',output=str(output),formal_result_eligible=False)
        if args.command in ('acquire','adapt'):
            budget=20 if args.command=='acquire' else args.budget
            nt,nv=(0,0) if budget==0 else (1,1) if budget==5 else (2,4)
            prefix='source' if args.command=='acquire' else 'target'
            c=generate(args.seed,{prefix+'_train':nt,prefix+'_validation':nv})
            if args.command=='adapt':
                initial=SkillSpec.model_validate_json(Path(args.skill).read_text())
            # Trajectories are outside learn output so its exclusive mkdir remains effective.
            runner=PhysXRunner(args.embodiment,output.parent/(output.name+'_trajectories'))
            from ..learners.factory import proposer_factory
            factory=proposer_factory(args.learner,args.learner_config,output/'model_calls.jsonl')
            after=learn(initial,budget,c[prefix+'_train'],c[prefix+'_validation'],factory,args.seed,runner,output)
            return dict(output=str(output),skill_hash=after.semantic_hash,formal_result_eligible=False)
        raise ValueError('Unsupported GPU command')
