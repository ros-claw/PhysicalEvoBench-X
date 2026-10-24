"""Read-only checks of finished packages while the frozen pilot continues.

This does not grant formal eligibility and never reads partially written stages.
Run the frozen scripts/audit_suite.py after the entire matrix finishes.
"""
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from physicalevobench_x.core.hashing import digest, file_digest, write_json
from physicalevobench_x.core.schemas import EpisodeResult, SkillSpec
from physicalevobench_x.protocol.learning import reconstruct
from pilot_suite import execution_inputs


def require(value, message):
    if not value:
        raise ValueError(message)


def read(path):
    return json.loads(path.read_text())


def check_pairs(directory, records, before, after, conditions):
    attempts = [json.loads(line) for line in
                (directory / 'pair_attempts.jsonl').read_text().splitlines()]
    excluded = {eid for row in attempts if not row['included'] for eid in row['episode_ids']}
    valid = [r for r in records if not r.infra_failure and r.episode_id not in excluded]
    equivalent = before.semantic_hash == after.semantic_hash
    hashes = Counter([before.semantic_hash] if equivalent else [before.semantic_hash, after.semantic_hash])
    require(len(valid) == len(conditions) * (1 if equivalent else 2), 'Wrong paired episode count')
    for condition in conditions:
        require(Counter(r.skill_hash for r in valid if r.condition_id == condition['condition_id']) == hashes,
                'Paired condition/skill coverage mismatch')
    b = sum(r.task_success for r in valid if r.skill_hash == before.semantic_hash)
    a = b if equivalent else sum(r.task_success for r in valid if r.skill_hash == after.semantic_hash)
    expected = dict(pairs=len(conditions), before_successes=b, after_successes=a,
                    delta_new=(a-b)/len(conditions), evaluation_aliased=equivalent)
    require(read(directory / 'summary.json') == expected, 'Paired summary arithmetic mismatch')
    return expected, excluded


def check_package(directory, info, plan, seen_ids):
    summary = read(directory / 'summary.json')
    require(summary['package'] == info, 'Package identity mismatch')
    manifest_path = Path(info['conditions_path'])
    require(file_digest(manifest_path) == info['conditions_sha256'], 'Condition manifest changed')
    conditions = read(manifest_path)
    condition_map = {c['condition_id']: c for values in conditions.values() for c in values}
    require(len(condition_map) == sum(map(len, conditions.values())), 'Split overlap')
    selected = {}
    for checkpoint in directory.glob('stages/*/complete.json'):
        data = read(checkpoint)
        require(data['identity'] == dict(package=info, execution_inputs_hash=digest(plan['execution_inputs'])),
                'Checkpoint identity mismatch')
        for name, checksum in data['files'].items():
            require(Path(name).resolve().is_relative_to(directory.resolve()), 'Evidence path escapes package')
            require(file_digest(name) == checksum, 'Checkpoint evidence changed')
        selected[checkpoint.parent.name] = Path(data['output'])
    records = defaultdict(list)
    for path in directory.glob('stages/*/journal/physical/[0-9]*.json'):
        entry = read(path)
        require(entry['status'] == 'COMPLETE', 'Finished package has an unresolved physical call')
        request = entry['request']
        result = EpisodeResult.model_validate(entry['result'])
        require(result.episode_id not in seen_ids, 'Duplicate physical execution')
        seen_ids.add(result.episode_id)
        require(result.backend == 'physx' and entry['request_hash'] == digest(request), 'Invalid execution')
        require(request['condition'] == condition_map.get(result.condition_id), 'Executed condition changed')
        require(result.skill_hash == SkillSpec.model_validate(request['skill']).semantic_hash,
                'Executed skill changed')
        require((result.phase, result.candidate_index, result.attempt_index, result.split) ==
                (request['phase'], request['candidate_index'], request['attempt_index'], request['condition']['split']),
                'Execution identity mismatch')
        if not result.infra_failure:
            require(file_digest(result.trajectory_path) == result.trajectory_sha256, 'Trajectory changed')
        records[path.parents[2].name].append(result)
    selected_ids = []
    for output in selected.values():
        path = output / 'episode_results.jsonl'
        if path.exists():
            selected_ids.extend(json.loads(line)['episode_id'] for line in path.read_text().splitlines())
    actual = [r for rows in records.values() for r in rows]
    require(Counter(selected_ids) == Counter(r.episode_id for r in actual), 'Journal/stage coverage mismatch')
    initial = SkillSpec.initial()
    require(SkillSpec.model_validate(read(selected['source'] / 'before.json')) == initial, 'Wrong source initial skill')
    rebuilt = reconstruct(selected['source'])
    require(all(rebuilt[k] == summary['source_selection'][k] for k in
                ('accepted_update', 'reason', 'selected_index')), 'Source decision mismatch')
    after = SkillSpec.model_validate(rebuilt['skill'])
    source, excluded = check_pairs(selected['source_audit'], records['source_audit'],
                                   initial, after, conditions['source_audit'])
    require(source == summary['source_audit'], 'Source audit mismatch')
    cells = []
    for budget in (0, 5, 20):
        names = [f'target_{budget}_before', f'target_{budget}_after']
        same = initial.semantic_hash == after.semantic_hash
        if same:
            names[1] = names[0]
        skills = []
        for name, incoming in zip(names, (initial, after)):
            path = selected[name]
            require(SkillSpec.model_validate(read(path / 'before.json')) == incoming, 'Wrong target input')
            skills.append(SkillSpec.model_validate(reconstruct(path)['skill']))
        stage = f'evaluation_{budget}'
        paired, discarded = check_pairs(selected[stage], records[stage], *skills, conditions['target_test'])
        excluded.update(discarded)
        cell = dict(paired, budget=budget, adaptation_aliased=same)
        require(cell == next(c for c in summary['cells'] if c['budget'] == budget), 'Target cell mismatch')
        cells.append(cell)
    costs = summary['costs']
    valid = [r for r in actual if not r.infra_failure]
    discarded_valid = sum(r.episode_id in excluded for r in valid)
    require(costs['physical_episode_executions'] == len(actual), 'Physical cost mismatch')
    require(costs['excluded_valid_pair_episode_executions'] == discarded_valid, 'Excluded cost mismatch')
    require(costs['logical_episode_requests'] == len(valid)-discarded_valid+costs['aliased_episode_requests'],
            'Logical/physical/alias accounting mismatch')
    require(costs['budget_charged_episodes'] == sum(r.phase in ('exploration', 'validation') for r in valid),
            'Practice cost mismatch')
    require(abs(costs['sim_time_s']-sum(r.sim_time_s for r in actual)) < 1e-6, 'Simulation cost mismatch')
    require(abs(costs['wall_time_s']-sum(r.wall_time_s for r in actual)) < 1e-6, 'Episode wall cost mismatch')
    return dict(package_id=info['package_id'], accepted_source_update=rebuilt['accepted_update'],
                source_audit=source, cells=cells, costs=costs)


def check(suite, root):
    plan = read(suite / 'plan.json')
    require(execution_inputs(root) == plan['execution_inputs'], 'Frozen execution inputs changed')
    points, pending, seen = [], [], set()
    # A package's final summary is published after all checkpoints and journals.
    # Capture this set once; a concurrently finishing package belongs to the next check.
    complete = [p for p in plan['packages'] if (suite/'packages'/p['package_id']/'summary.json').exists()]
    for info in plan['packages']:
        if info in complete:
            points.append(check_package(suite/'packages'/info['package_id'], info, plan, seen))
        else:
            pending.append(info['package_id'])
    return dict(status='COMPLETED_PACKAGE_CHECKS_PASSED', formal_result_eligible=False,
                checked_at_utc=datetime.now(timezone.utc).isoformat(),
                scope='Completed packages only; not the full frozen-suite acceptance audit',
                completed_packages=len(points), planned_packages=len(plan['packages']),
                checked_physical_calls=len(seen), pending_packages=pending, points=points)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--suite', type=Path, required=True)
    parser.add_argument('--root', type=Path, default=Path.cwd())
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        result = check(args.suite.resolve(), args.root.resolve())
    except (ValueError, OSError, KeyError, StopIteration) as exc:
        result = dict(status='COMPLETED_PACKAGE_CHECK_FAILED', formal_result_eligible=False,
                      reason=str(exc))
    require(not args.output.exists(), 'Use a new review output; previous evidence is immutable')
    write_json(args.output, result)
    print(json.dumps(result))
    raise SystemExit(0 if result['status'] == 'COMPLETED_PACKAGE_CHECKS_PASSED' else 2)
