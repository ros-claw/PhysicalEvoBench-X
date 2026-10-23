"""Summarize complete run packages, preserving incomplete runs and all run points."""
import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean, median
from physicalevobench_x.core.hashing import write_json


def summarize(suite, verified_audit=False):
    audit_result=None
    if verified_audit:
        from audit_suite import audit
        audit_result=audit(suite,Path.cwd())
    plan = json.loads((suite/'plan.json').read_text())
    complete, incomplete, records, inflight = [], [], [], []
    tokens, failures = Counter(), Counter()
    descriptive=defaultdict(list)
    for package in plan['packages']:
        directory = suite/'packages'/package['package_id']
        summary = directory/'summary.json'
        if summary.exists():
            complete.append(json.loads(summary.read_text()))
        else:
            incomplete.append(package['package_id'])
        excluded=set()
        for checkpoint in directory.glob('stages/*/complete.json'):
            selected=Path(json.loads(checkpoint.read_text())['output'])
            attempts=selected/'pair_attempts.jsonl'
            if attempts.exists():
                for line in attempts.read_text().splitlines():
                    attempt=json.loads(line)
                    if not attempt['included']:
                        excluded.update(attempt['episode_ids'])
        for path in sorted(directory.glob('stages/*/journal/physical/[0-9]*.json')):
            call = json.loads(path.read_text())
            if call['status'] != 'COMPLETE':
                inflight.append(str(path.relative_to(suite)))
                continue
            record = call['result']
            record['excluded_from_pair_statistics']=record['episode_id'] in excluded
            if record['backend'] != 'physx':
                raise ValueError('Report rejects CPU/fake physical evidence')
            records.append(record)
            descriptive[(package['package_id'],path.parents[2].name)].append(record)
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
                tokens['valid_responses'] += int(bool(call.get('valid')))
                tokens['cached_input_tokens'] += (usage.get('prompt_tokens_details') or {}).get('cached_tokens',usage.get('cached_tokens',0))
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
        mean_before_success_rate=mean(p['before_success_rate'] for p in points),
        mean_after_success_rate=mean(p['after_success_rate'] for p in points),
        minimum_delta=min(p['delta_new'] for p in points),maximum_delta=max(p['delta_new'] for p in points))
        for k,points in sorted(grouped.items())]
    descriptions=[]
    for (package_id,stage), rows in sorted(descriptive.items()):
        valid=[r for r in rows if not r['infra_failure'] and not r['excluded_from_pair_statistics']]
        successful=[r['completion_time_s'] for r in valid if r['task_success']]
        descriptions.append(dict(package_id=package_id,stage=stage,physical_attempts=len(rows),valid_episodes=len(valid),
            infrastructure_invalid_rate=sum(bool(r['infra_failure']) for r in rows)/len(rows),
            excluded_pair_episode_executions=sum(r['excluded_from_pair_statistics'] for r in rows),
            hard_constraint_episodes=sum(bool(r['constraint_violations']) for r in valid),
            failure_reasons=dict(Counter(r['termination_reason'] for r in valid if not r['task_success'])),
            successful_completion_median_s=median(successful) if successful else None,
            successful_completion_range_s=[min(successful),max(successful)] if successful else None,
            note='Episode-level descriptive diagnostics, not independent learning replicates'))
    events_path=suite/'supervisor_events.jsonl'
    events=[json.loads(line) for line in events_path.read_text().splitlines()] if events_path.exists() else []
    ended={event['log'] for event in events if event['event']=='END'}
    unresolved_processes=[event for event in events if event['event']=='START' and event['log'] not in ended]
    accepted=sum(p['source_selection']['accepted_update'] for p in complete)
    report = dict(track=plan['track'],planned_packages=len(plan['packages']),completed_packages=len(complete),
        incomplete_packages=incomplete,unresolved_calls=inflight,groups=groups,packages=complete,
        failures=dict(failures),model_costs=dict(tokens),descriptive_metrics=descriptions,
        accepted_source_updates=accepted,rolled_back_source_runs=len(complete)-accepted,
        model_service_status='OBSERVED_VALID_RESPONSES' if tokens['valid_responses'] else 'NO_VALID_MODEL_RESPONSES' if tokens['requests'] else 'NO_MODEL_REQUESTS',
        completed_native_process_wall_s=sum(e.get('child_wall_time_s',0) for e in events if e['event']=='END'),
        unresolved_native_processes=unresolved_processes,
        research_status='NO_ACCEPTED_UPDATE' if complete and not incomplete and not accepted else 'INCONCLUSIVE',
        physical_episode_executions=len(records),sim_time_s=sum(r['sim_time_s'] for r in records),
        episode_wall_time_s=sum(r['wall_time_s'] for r in records),formal_result_eligible=bool(audit_result),
        independent_audit=audit_result,
        limitations=['Pilot points are independent learning runs; test episodes are not independent learning replicates.',
            'No significance claim from three learning runs.',
            'Known completed physical calls only; unresolved in-flight work has unknown additional cost.',
            'Excludes development, calibration, and other suites; GPU time is not exclusive occupancy.',
            'Formal eligibility requires independent frozen-evidence audit.'])
    write_json(suite/'report.json',report)
    lines = ['# PhysicalEvoBench-X matrix report','',
        f'Track: `{plan["track"]}`; formal result eligible: **{str(bool(audit_result)).lower()}**.', '',
        f'Complete learning packages: {len(complete)}/{len(plan["packages"])}. '
        f'Unresolved physical calls: {len(inflight)}.', '',
        '| Learner | Direction | Budget | Independent runs | Before SR | After SR | Mean delta | Min / max |',
        '|---|---|---:|---:|---:|---:|---:|---|']
    for g in groups:
        lines.append(f'| {g["learner"]} | {g["source"]} → {g["target"]} | {g["budget"]} | '
            f'{g["independent_learning_runs"]} | {g["mean_before_success_rate"]:.4f} | {g["mean_after_success_rate"]:.4f} | {g["mean_delta"]:.4f} | '
            f'{g["minimum_delta"]:.4f} / {g["maximum_delta"]:.4f} |')
    lines += ['', 'All run points, source acceptance decisions, aliases, failure counts and model costs '
              'are retained in `report.json`. Missing packages are not replaced with zero-gain observations.', '']
    lines += ['- '+limitation for limitation in report['limitations']]
    (suite/'report.md').write_text('\n'.join(lines)+'\n')
    chinese=['# PhysicalEvoBench-X 实验记录','',
        f'完成独立学习包 {len(complete)}/{len(plan["packages"])}；正式结果资格：{bool(audit_result)}。',
        f'源端接受更新 {accepted} 次；回滚或无行为变化 {len(complete)-accepted} 次。研究状态：{report["research_status"]}。','',
        '| 方法 | 方向 | fresh 目标预算 | 独立 run 数 | Before 成功率 | After 成功率 | 平均配对差 | run 差值范围 |',
        '|---|---|---:|---:|---:|---:|---:|---|']
    for g in groups:
        chinese.append(f'| {g["learner"]} | {g["source"]} → {g["target"]} | {g["budget"]} | {g["independent_learning_runs"]} | '
            f'{g["mean_before_success_rate"]:.4f} | {g["mean_after_success_rate"]:.4f} | {g["mean_delta"]:.4f} | '
            f'{g["minimum_delta"]:.4f} / {g["maximum_delta"]:.4f} |')
    chinese+=['','全部 run 点、源审计、失败类型、硬约束、完成时间和物理/模型成本保存在 report.json。'
        '未完成包单列，不当作零收益补入。三个 run 仅为 pilot，不据测试回合数量宣称强显著性。'
        '开发结果不能事后改标签成为正式实验；当前机器人配置与仿真结果不构成任意真机泛化证明。']
    (suite/'report.zh-CN.md').write_text('\n'.join(chinese)+'\n')
    return report


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--suite',type=Path,required=True)
    p.add_argument('--verified-audit',action='store_true')
    args = p.parse_args()
    result = summarize(args.suite,args.verified_audit)
    print(json.dumps({k:result[k] for k in ('planned_packages','completed_packages','physical_episode_executions','formal_result_eligible')}))
