"""Independent-target-budget paired physical smoke of a reconstructed source artifact.

Explicitly a development bridge, not a frozen pilot or an official report.
"""
import argparse
import json
from pathlib import Path
from .core.schemas import SkillSpec
from .core.hashing import write_json,file_digest
from .protocol.learning import reconstruct
from .core.conditions import generate


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--target',choices=['franka_panda','franka_robotiq'],required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--target-budget',type=int,choices=[0,5,20],default=0)
    parser.add_argument('--test-conditions',type=int,default=2)
    args=parser.parse_args()
    if args.output.exists() or args.test_conditions<1:
        raise ValueError('New output and nonempty paired test plan required')
    reconstruction=reconstruct(args.source)
    before=SkillSpec.model_validate_json((args.source/'before.json').read_text())
    after=SkillSpec.model_validate(reconstruction['skill'])
    costs=json.loads((args.source/'costs.json').read_text())
    if costs['charged']!={'exploration':12,'validation':8}:
        raise ValueError('Expected a complete 20-episode source acquisition')
    nt,nv=(0,0) if args.target_budget==0 else (1,1) if args.target_budget==5 else (2,4)
    manifest=generate(0,{'target_train':nt,'target_validation':nv,'target_test':args.test_conditions})
    conditions=manifest['target_test']
    from isaaclab_arena.cli.isaaclab_arena_cli import get_isaaclab_arena_cli_parser
    from isaaclab_arena.utils.isaaclab_utils.simulation_app import SimulationAppContext
    with SimulationAppContext(get_isaaclab_arena_cli_parser().parse_args([])):
        from .sim.runner import PhysXRunner
        from .protocol.paired import paired_evaluate
        args.output.mkdir(parents=True,exist_ok=False)
        write_json(args.output/'source_lineage.json',dict(source_directory=str(args.source.resolve()),
            before_sha256=file_digest(args.source/'before.json'),after_sha256=file_digest(args.source/'after.json'),
            reconstruction=reconstruction,source_budget_charged=20))
        write_json(args.output/'private_conditions.json',manifest)
        write_json(args.output/'input_before.json',before)
        write_json(args.output/'input_after.json',after)
        adaptation_aliased=before.semantic_hash==after.semantic_hash
        if args.target_budget:
            from .learners.random_search import RandomSearch
            from .protocol.learning import learn
            target_runner=PhysXRunner(args.target,args.output/'adaptation_trajectories')
            frozen_before=learn(before,args.target_budget,manifest['target_train'],manifest['target_validation'],
                RandomSearch,0,target_runner,args.output/'adapt_before')
            if adaptation_aliased:
                frozen_after=frozen_before
                write_json(args.output/'adaptation_alias.json',dict(request='after',alias_of='adapt_before',
                    reason='IDENTICAL_INPUT_PROPOSER_RNG_AND_CONDITIONS',aliased_episode_requests=args.target_budget))
            else:
                frozen_after=learn(after,args.target_budget,manifest['target_train'],manifest['target_validation'],
                    RandomSearch,0,target_runner,args.output/'adapt_after')
        else:
            frozen_before,frozen_after=before,after
        write_json(args.output/'frozen_before.json',frozen_before)
        write_json(args.output/'frozen_after.json',frozen_after)
        pairs=paired_evaluate(frozen_before,frozen_after,conditions,
            lambda side:PhysXRunner(args.target,args.output/'trajectories'/side),args.output/'paired',
            equivalent=frozen_before.semantic_hash==frozen_after.semantic_hash)
        summary=dict(backend='physx',track='development_paired_transfer_smoke',target_body=args.target,
            target_adaptation_budget=args.target_budget,
            target_budget_charged=args.target_budget*(1 if adaptation_aliased else 2),
            target_adaptation_aliased=adaptation_aliased,planned_pairs=len(conditions),valid_pairs=len(pairs),
            source_accepted_update=reconstruction['accepted_update'],
            before_successes=sum(p[0].task_success for p in pairs),after_successes=sum(p[1].task_success for p in pairs),
            paired_success_rate_delta=sum(int(p[1].task_success)-int(p[0].task_success) for p in pairs)/len(pairs),
            aliases=frozen_before.semantic_hash==frozen_after.semantic_hash,formal_result_eligible=False,
            note='Small mechanical protocol smoke; no research significance claim')
        write_json(args.output/'summary.json',summary)
        print(json.dumps(summary),flush=True)


if __name__=='__main__':
    main()
