"""Summarize complete run packages, preserving incomplete runs and all run points."""
import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean
from physicalevobench_x.core.hashing import write_json


def summarize(suite):
    plan = json.loads((suite/'plan.json').read_text())
    complete, incomplete, records, inflight = [], [], [], []
    tokens, failures = Counter(), Counter()
    for package in plan['packages']:
        directory = suite/'packages'/package['package_id']
        summary = directory/'summary.json'
        if summary.exists():
            complete.append(json.loads(summary.read_text()))
        else:
            incomplete.append(package['package_id'])
        for path in sorted(directory.glob('stages/*/journal/physical/[0-9]*.json')):
            call = json.loads(path.read_text())
            if call['status'] != 'COMPLETE':
                inflight.append(str(path.relative_to(suite)))
                continue
            record = call['result']
            if record['backend'] != 'physx':
                raise ValueError('Report rejects CPU/fake physical evidence')
            records.append(record)
            if record['infra_failure']:
                failures['INFRA:'+record['infra_failure']] += 1
            elif not record['task_success']:
                failures[record['termination_reason']] += 1
        for path in directory.glob('model_calls/*.jsonl'):
            for line in path.read_text().splitlines():
                call = json.loads(line)
                tokens['requests'] += 1
                usage = call.get('usage') or {}
                tokens['input_tokens'] += usage.get('prompt_tokens',0)
                tokens['output_tokens'] += usage.get('completion_tokens',0)
                tokens['reasoning_tokens'] += (usage.get('completion_tokens_details') or {}).get('reasoning_tokens',0)
                tokens['requests_without_usage'] += int(not usage)
                tokens['invalid_or_failed_requests'] += int(not call.get('valid'))
    if len({r['episode_id'] for r in records}) != len(records):
        raise ValueError('Physical journal contains duplicate execution IDs')
    grouped = defaultdict(list)
    for package in complete:
        info = package['package']
        for cell in package['cells']:
            key = (info['learner'],info['source'],info['target'],cell['budget'])
            grouped[key].append(dict(run_seed_id=info['run_seed_id'],delta_new=cell['delta_new'],
                before_success_rate=cell['before_successes']/cell['pairs'],
                after_success_rate=cell['after_successes']/cell['pairs'],
                source_accepted_update=package['source_selection']['accepted_update'],
                adaptation_aliased=cell['adaptation_aliased']))
    groups = [dict(learner=k[0],source=k[1],target=k[2],budget=k[3],points=points,
        independent_learning_runs=len(points),mean_delta=mean(p['delta_new'] for p in points),
        minimum_delta=min(p['delta_new'] for p in points),maximum_delta=max(p['delta_new'] for p in points))
        for k,points in sorted(grouped.items())]
    report = dict(track=plan['track'],planned_packages=len(plan['packages']),completed_packages=len(complete),
        incomplete_packages=incomplete,unresolved_calls=inflight,groups=groups,packages=complete,
        failures=dict(failures),model_costs=dict(tokens),
        physical_episode_executions=len(records),sim_time_s=sum(r['sim_time_s'] for r in records),
        episode_wall_time_s=sum(r['wall_time_s'] for r in records),formal_result_eligible=False,
        limitations=['Pilot points are independent learning runs; test episodes are not independent learning replicates.',
            'No significance claim from three learning runs.',
            'Known completed physical calls only; unresolved in-flight work has unknown additional cost.',
            'Excludes development, calibration, and other suites; GPU time is not exclusive occupancy.',
            'Formal eligibility requires independent frozen-evidence audit.'])
    write_json(suite/'report.json',report)
    lines = ['# PhysicalEvoBench-X matrix report','',
        f'Track: `{plan["track"]}`; formal result eligible: **false**.', '',
        f'Complete learning packages: {len(complete)}/{len(plan["packages"])}. '
        f'Unresolved physical calls: {len(inflight)}.', '',
        '| Learner | Direction | Budget | Independent runs | Mean delta | Min / max |',
        '|---|---|---:|---:|---:|---|']
    for g in groups:
        lines.append(f'| {g["learner"]} | {g["source"]} → {g["target"]} | {g["budget"]} | '
            f'{g["independent_learning_runs"]} | {g["mean_delta"]:.4f} | '
            f'{g["minimum_delta"]:.4f} / {g["maximum_delta"]:.4f} |')
    lines += ['', 'All run points, source acceptance decisions, aliases, failure counts and model costs '
              'are retained in `report.json`. Missing packages are not replaced with zero-gain observations.', '']
    lines += ['- '+limitation for limitation in report['limitations']]
    (suite/'report.md').write_text('\n'.join(lines)+'\n')
    return report


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--suite',type=Path,required=True)
    args = p.parse_args()
    result = summarize(args.suite)
    print(json.dumps({k:result[k] for k in ('planned_packages','completed_packages','physical_episode_executions','formal_result_eligible')}))
