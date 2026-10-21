"""GPU CLI bridge. App starts once, simulation imports happen inside context."""
from pathlib import Path
from ..core.schemas import SkillSpec
from ..core.hashing import append_json, write_json


def execute(args):
    from isaaclab_arena.cli.isaaclab_arena_cli import get_isaaclab_arena_cli_parser
    from isaaclab_arena.utils.isaaclab_utils.simulation_app import SimulationAppContext
    startup=get_isaaclab_arena_cli_parser().parse_args(['--headless'])
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
            after=learn(initial,budget,c[prefix+'_train'],c[prefix+'_validation'],RandomSearch,args.seed,runner,output)
            return dict(output=str(output),skill_hash=after.semantic_hash,formal_result_eligible=False)
        raise ValueError('Unsupported GPU command')
