import argparse
import json
import sys
from pathlib import Path
from .core.hashing import canonical, write_json


def main():
    parser = argparse.ArgumentParser(prog='pebx', description='PhysicalEvoBench-X; evidence before performance claims')
    parser.add_argument('--root', type=Path, default=Path.cwd())
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('doctor', help='Check pinned runtime; --sim executes real upstream reset/step')
    p.add_argument('--sim', action='store_true')
    p.add_argument('--embodiment', choices=['franka_panda','franka_robotiq'], default='franka_panda')
    p.add_argument('--output', type=Path, default=Path('evidence/doctor.json'))
    p = sub.add_parser('freeze', help='Freeze only after all physical development checks pass')
    p.add_argument('--config', required=True, type=Path)
    p.add_argument('--output', type=Path, default=Path('frozen/v0.1.json'))
    p = sub.add_parser('reconstruct', help='Recompute source/target learning decision from complete history')
    p.add_argument('--run-dir', type=Path, required=True)
    p = sub.add_parser('validate-run', help='Validate evidence; rejects fake physical results')
    p.add_argument('--run-dir', type=Path, required=True)
    p = sub.add_parser('skill-check', help='Strictly validate a complete five-dimensional SkillSpec')
    p.add_argument('path', type=Path)
    p = sub.add_parser('generate-conditions', help='Generate private development manifests (unfrozen)')
    p.add_argument('--seed', type=int, required=True)
    p.add_argument('--output', type=Path, required=True)
    p = sub.add_parser('llm-probe', help='Make one bounded real proposal with an explicit learner config')
    p.add_argument('--config',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p = sub.add_parser('run',help='Execute GPU acceptance, engineering smoke, throughput, freeze and full paired pilot')
    p.add_argument('--config',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--gpus',type=int,nargs='+',default=[0,1])
    p = sub.add_parser('report',help='Generate matrix report; --verified-audit independently validates formal eligibility')
    p.add_argument('--run-dir',type=Path,required=True)
    p.add_argument('--verified-audit',action='store_true')
    p.add_argument('--plots',action='store_true',help='Also export SVG/PDF; requires the report extra')
    p = sub.add_parser('evaluate',help='Evaluate a frozen SkillSpec on an evaluator-owned held-out manifest')
    p.add_argument('--skill',type=Path,required=True)
    p.add_argument('--conditions',type=Path,required=True)
    p.add_argument('--split',choices=['target_test','source_audit'],default='target_test')
    p.add_argument('--embodiment',choices=['franka_panda','franka_robotiq'],required=True)
    p.add_argument('--output',type=Path,required=True)
    for name in ('smoke','acquire','adapt','calibrate','dynamics-check'):
        p = sub.add_parser(name, help='Real PhysX development execution; requires pinned simulation environment')
        p.add_argument('--embodiment', choices=['franka_panda','franka_robotiq'], required=True)
        p.add_argument('--output',type=Path,required=True)
        p.add_argument('--seed',type=int,default=0)
        if name == 'smoke':
            p.add_argument('--episodes',type=int,default=10)
        if name in ('acquire','adapt'):
            p.add_argument('--learner',choices=['random_search_v1','bounded_llm_v1'],default='random_search_v1')
            p.add_argument('--learner-config',type=Path,default=Path('configs/learners/kimi_k3.yaml'))
        if name == 'adapt':
            p.add_argument('--budget',type=int,choices=[0,5,20],required=True)
            p.add_argument('--skill',type=Path,required=True)
    args = parser.parse_args()
    try:
        if args.command in ('run','report'):
            import subprocess
            root=args.root.resolve()
            script='complete_pipeline.py' if args.command=='run' else 'summarize_pilot.py'
            command=[sys.executable,str(root/'scripts'/script)]
            if args.command=='run':
                command+=['--config',str(args.config.resolve()),'--output',str(args.output.resolve()),'--gpus',*[str(g) for g in args.gpus]]
            else:
                command+=['--suite',str(args.run_dir.resolve())]
                if args.verified_audit:
                    command+=['--verified-audit']
            code=subprocess.run(command,cwd=root,check=False).returncode
            if not code and args.command=='report' and args.plots:
                code=subprocess.run([sys.executable,str(root/'scripts/plot_report.py'),'--suite',str(args.run_dir.resolve())],cwd=root,check=False).returncode
            return code
        if args.command == 'llm-probe':
            from .learners.factory import proposer_factory
            from .core.schemas import SkillSpec
            args.output.mkdir(parents=True,exist_ok=False)
            proposer=proposer_factory('bounded_llm_v1',args.config,args.output/'calls.jsonl')(0)
            skill=proposer.propose(SkillSpec.initial(),[])
            result=dict(skill=skill.model_dump(),semantic_hash=skill.semantic_hash,
                        fallback=bool(proposer.proposals[-1].get('fallback')),formal_result_eligible=False)
            write_json(args.output/'result.json',result)
            print(canonical(result))
            return 2 if result['fallback'] else 0
        if args.command in ('smoke','acquire','adapt','calibrate','dynamics-check','evaluate'):
            from .sim.doctor import doctor
            readiness = doctor(args.root)
            if readiness['status'] != 'READY_FOR_SIM_PROBE':
                raise RuntimeError('BLOCKED_ENVIRONMENT: run pebx doctor --sim in pinned Arena container')
            from .sim.commands import execute
            print(canonical(execute(args)))
            return 0
        if args.command == 'doctor':
            from .sim.doctor import doctor
            result = doctor(args.root)
            write_json(args.output, result)
            if args.sim:
                if result['status'] != 'READY_FOR_SIM_PROBE':
                    print(canonical(result))
                    return 2
                from .sim.launch import probe
                probe(args.embodiment, args.output.with_name('reset_step_'+args.embodiment+'.json'))
            print(canonical(result))
            return 0 if result['status'] == 'READY_FOR_SIM_PROBE' else 2
        if args.command == 'freeze':
            from .core.freeze import freeze
            result = freeze(args.config, args.root, args.output)
        elif args.command == 'reconstruct':
            from .protocol.learning import reconstruct
            result = reconstruct(args.run_dir)
        elif args.command == 'validate-run':
            from .reporting.validation import validate_run
            result = validate_run(args.run_dir)
        elif args.command == 'skill-check':
            from .core.schemas import SkillSpec
            skill = SkillSpec.model_validate_json(args.path.read_text())
            result = dict(skill=skill.model_dump(), semantic_hash=skill.semantic_hash)
        elif args.command == 'generate-conditions':
            from .core.conditions import generate
            if args.output.exists():
                raise ValueError('Refusing to overwrite a manifest')
            result = generate(args.seed, dict(dev=10, source_train=2, source_validation=4,
                source_audit=50, target_train=2, target_validation=4, target_test=50))
            write_json(args.output, result)
            result = {'output': str(args.output), 'formal_result_eligible': False}
        print(canonical(result))
        return 0
    except (ValueError, RuntimeError, OSError, ImportError) as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
