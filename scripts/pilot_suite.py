"""Explicit dual-direction matrix with private manifests and resumable stages.

Plan/summary are CPU-only. Worker requires a live native Isaac Sim runtime.
Formal execution additionally requires an unchanged, accepted freeze manifest.
"""
import argparse
import json
import os
import time
from pathlib import Path
from physicalevobench_x.core.hashing import digest, file_digest, write_json
from physicalevobench_x.core.conditions import generate
from physicalevobench_x.core.schemas import SkillSpec
from pilot_support import ReplayJournal, ReplayRunner, replay_factory, atomic_json

BODIES = ('franka_panda', 'franka_robotiq')
LEARNERS = ('random_search_v1', 'bounded_llm_v1')


def execution_inputs(root):
    paths = [*root.glob('src/**/*.py'), *root.glob('configs/**/*.yaml'),
             *root.glob('scripts/*.py'), root/'dependencies.lock.yaml', root/'docs/protocol_v0.1.md']
    return {str(p.relative_to(root)): file_digest(p) for p in sorted(paths)}


def plan(output, root, freeze=None, seeds=3, test_count=50, learners=LEARNERS):
    if seeds < 1 or test_count < 1 or not set(learners) <= set(LEARNERS):
        raise ValueError('Invalid experiment dimensions')
    inputs = execution_inputs(root)
    if freeze:
        frozen = json.loads(freeze.read_text())
        contents = {k: v for k, v in frozen.items() if k != 'freeze_hash'}
        if (digest(contents) != frozen.get('freeze_hash')
            or frozen.get('protocol') != 'pebx_x_v0.1'
            or not frozen.get('config', {}).get('development_validated')):
            raise ValueError('Invalid or unvalidated freeze manifest')
        for name, checksum in frozen['files'].items():
            if file_digest(root/name) != checksum:
                raise ValueError('Freeze input mismatch: '+name)
        freeze_hash = frozen['freeze_hash']
    else:
        freeze_hash = None
    output.mkdir(parents=True, exist_ok=False)
    private = output/'private'
    private.mkdir(mode=0o700)
    packages = []
    for seed_id in range(seeds):
        manifest = generate(10001+seed_id, dict(source_train=2, source_validation=4,
            source_audit=test_count, target_train=2, target_validation=4, target_test=test_count))
        path = private/f'seed-{seed_id}.json'
        write_json(path, manifest)
        path.chmod(0o600)
        for learner in learners:
            for source in BODIES:
                packages.append(dict(package_id=f'{learner}/{source}/seed-{seed_id}', learner=learner,
                    source=source, target=BODIES[1-BODIES.index(source)], run_seed_id=seed_id,
                    source_proposal_seed=30001+seed_id, target_proposal_seed=40001+seed_id,
                    conditions_path=str(path.resolve()), conditions_sha256=file_digest(path)))
    data = dict(protocol='pebx_x_v0.1', track='frozen_pilot' if freeze else 'development_matrix',
        freeze_hash=freeze_hash, freeze_path=str(freeze.resolve()) if freeze else None,
        execution_inputs=inputs, test_count=test_count, budgets=[0,5,20], packages=packages,
        logical_episode_requests=len(packages)*(20+50+8*test_count),
        formal_result_eligible=False, eligibility_note='Execution plus full evidence audit required')
    # Per package: source 20, target practice 2*(5+20), source audit 2*n, target tests 6*n.
    write_json(output/'plan.json', data)
    return data


def stage(package, name, identity, operation):
    directory = package/'stages'/name
    directory.mkdir(parents=True, exist_ok=True)
    complete = directory/'complete.json'
    if complete.exists():
        checkpoint = json.loads(complete.read_text())
        if checkpoint['identity'] != identity:
            raise ValueError('Completed stage identity mismatch')
        for path, checksum in checkpoint['files'].items():
            if file_digest(path) != checksum:
                raise ValueError('Completed stage evidence changed: '+path)
        return Path(checkpoint['output'])
    attempt = directory/f'attempt-{len(list(directory.glob("attempt-*")))+1:03d}'
    operation(attempt, directory/'journal')
    files = {str(p.resolve()): file_digest(p) for p in attempt.rglob('*') if p.is_file()}
    # Physical records may point outside the selected attempt directory.
    for path in attempt.rglob('*results.jsonl'):
        for line in path.read_text().splitlines():
            record = json.loads(line)
            if record.get('trajectory_path'):
                trace = Path(record['trajectory_path'])
                if file_digest(trace) != record['trajectory_sha256']:
                    raise ValueError('Physical evidence checksum mismatch')
                files[str(trace.resolve())] = record['trajectory_sha256']
    atomic_json(complete, dict(identity=identity, output=str(attempt.resolve()), files=files))
    return attempt


def _worker(suite, package_id, root):
    started = time.monotonic()
    data = json.loads((suite/'plan.json').read_text())
    if execution_inputs(root) != data['execution_inputs']:
        raise ValueError('Suite code/config changed; create a new version, do not mix comparisons')
    package = next(p for p in data['packages'] if p['package_id'] == package_id)
    path = Path(package['conditions_path'])
    if file_digest(path) != package['conditions_sha256']:
        raise ValueError('Private condition manifest changed')
    conditions = json.loads(path.read_text())
    output = suite/'packages'/package_id
    output.mkdir(parents=True, exist_ok=True)
    identity = dict(package=package, execution_inputs_hash=digest(data['execution_inputs']))
    initial = SkillSpec.initial()
    from isaaclab_arena.cli.isaaclab_arena_cli import get_isaaclab_arena_cli_parser
    from isaaclab_arena.utils.isaaclab_utils.simulation_app import SimulationAppContext
    with SimulationAppContext(get_isaaclab_arena_cli_parser().parse_args([])):
        from physicalevobench_x.sim.runner import PhysXRunner
        from physicalevobench_x.protocol.learning import learn, reconstruct
        from physicalevobench_x.protocol.paired import paired_evaluate
        from physicalevobench_x.learners.factory import proposer_factory

        def learning(name, body, skill, budget, train, val, seed):
            def execute(attempt, journals):
                physical = ReplayJournal(journals/'physical', identity)
                proposals = ReplayJournal(journals/'proposals', identity)
                runner = ReplayRunner(physical, PhysXRunner(body, output/'trajectories'/name))
                factory = replay_factory(proposals, proposer_factory(package['learner'],
                    root/'configs/learners/kimi_k3.yaml', output/'model_calls'/f'{name}.jsonl'))
                learn(skill,budget,train,val,factory,seed,runner,attempt)
                if budget:
                    write_json(attempt/'reconstruction.json', reconstruct(attempt))
            path = stage(output,name,identity,execute)
            return SkillSpec.model_validate_json((path/'after.json').read_text()), path

        def paired(name, body, before, after, conditions, phase):
            def execute(attempt, journals):
                physical = ReplayJournal(journals/'physical', identity)
                runner = ReplayRunner(physical, PhysXRunner(body, output/'trajectories'/name))
                pairs = paired_evaluate(before, after, conditions, lambda side: runner, attempt,
                    equivalent=before.semantic_hash == after.semantic_hash, phase=phase)
                write_json(attempt/'summary.json', dict(pairs=len(pairs),
                    before_successes=sum(p[0].task_success for p in pairs),
                    after_successes=sum(p[1].task_success for p in pairs),
                    delta_new=sum(int(p[1].task_success)-int(p[0].task_success) for p in pairs)/len(pairs),
                    evaluation_aliased=before.semantic_hash == after.semantic_hash))
            return stage(output,name,identity,execute)

        after, source_dir = learning('source', package['source'], initial,20,
            conditions['source_train'],conditions['source_validation'],package['source_proposal_seed'])
        audit = paired('source_audit',package['source'],initial,after,conditions['source_audit'],'source_audit')
        cells, aliases = [], []
        for budget in data['budgets']:
            nt,nv = (0,0) if budget==0 else (1,1) if budget==5 else (2,4)
            before_target, before_dir = learning(f'target_{budget}_before',package['target'],initial,budget,
                conditions['target_train'][:nt],conditions['target_validation'][:nv],package['target_proposal_seed'])
            equivalent = initial.semantic_hash == after.semantic_hash
            if equivalent:
                after_target = before_target
                aliases.append(dict(request=f'target_{budget}_after',alias_of=f'target_{budget}_before',
                    aliased_episode_requests=budget,reason='IDENTICAL_INPUT_CONTEXT_RNG_AND_VERSIONS'))
            else:
                after_target, _ = learning(f'target_{budget}_after',package['target'],after,budget,
                    conditions['target_train'][:nt],conditions['target_validation'][:nv],package['target_proposal_seed'])
            evaluation = paired(f'evaluation_{budget}',package['target'],before_target,after_target,
                                conditions['target_test'],'evaluation')
            cell = json.loads((evaluation/'summary.json').read_text())
            cell.update(budget=budget,adaptation_aliased=equivalent)
            cells.append(cell)
        # Count only journaled physical executions, once, including completed retries.
        records = []
        for entry in sorted((output/'stages').glob('*/journal/physical/[0-9]*.json')):
            record = json.loads(entry.read_text())
            if record['status'] != 'COMPLETE':
                raise ValueError('Unresolved physical call')
            records.append(record['result'])
        logical = 20+50+8*data['test_count']
        alias_count = sum(a['aliased_episode_requests'] for a in aliases)
        alias_count += data['test_count']*int(initial.semantic_hash==after.semantic_hash)
        alias_count += sum(c['pairs'] for c in cells if c['evaluation_aliased'])
        valid = sum(not r['infra_failure'] for r in records)
        if logical != valid+alias_count:
            raise ValueError('Logical/actual/alias accounting mismatch')
        costs = dict(logical_episode_requests=logical,physical_episode_executions=len(records),
            aliased_episode_requests=alias_count,budget_charged_episodes=sum(r['phase'] in ('exploration','validation')
                and not r['infra_failure'] for r in records),
            sim_time_s=sum(r['sim_time_s'] for r in records),wall_time_s=sum(r['wall_time_s'] for r in records),
            current_worker_wall_time_s=time.monotonic()-started,
            gpu_seconds_estimation='Episode wall time on one selected GPU; no exclusive utilization claim')
        write_json(output/'costs.json',costs)
        write_json(output/'aliases.json',aliases)
        write_json(output/'summary.json',dict(package=package, source_selection=json.loads((source_dir/'selection.json').read_text()),
            source_audit=json.loads((audit/'summary.json').read_text()), cells=cells,costs=costs,
            formal_result_eligible=False,track=data['track']))


def worker(suite, package_id, root):
    import fcntl
    data = json.loads((suite/'plan.json').read_text())
    if package_id not in {p['package_id'] for p in data['packages']}:
        raise ValueError('Unknown package')
    directory = suite/'packages'/package_id
    directory.mkdir(parents=True, exist_ok=True)
    with (directory/'.worker.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError('Package already has an active worker') from exc
        return _worker(suite, package_id, root)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--root',type=Path,default=Path.cwd())
    sub = p.add_subparsers(dest='command',required=True)
    s = sub.add_parser('plan')
    s.add_argument('--output',type=Path,required=True)
    s.add_argument('--freeze',type=Path)
    s.add_argument('--seeds',type=int,default=3)
    s.add_argument('--test-count',type=int,default=50)
    s.add_argument('--learner',action='append',choices=LEARNERS)
    s = sub.add_parser('worker')
    s.add_argument('--suite',type=Path,required=True)
    s.add_argument('--package',required=True)
    args = p.parse_args()
    if args.command == 'plan':
        result = plan(args.output.resolve(),args.root.resolve(),args.freeze,args.seeds,args.test_count,args.learner or LEARNERS)
        print(json.dumps(dict(packages=len(result['packages']),logical_episode_requests=result['logical_episode_requests'],
                              track=result['track'])))
    else:
        worker(args.suite.resolve(),args.package,args.root.resolve())


if __name__ == '__main__':
    main()
