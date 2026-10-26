"""Finish retained-state auditing and archive all physics-profile results after workers stop."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from physicalevobench_x.core.hashing import file_digest,write_json

ROOT=Path(__file__).resolve().parents[1]


def finalize(study,archive,native_python):
    import fcntl
    with (study/'finalizer.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (study/'finalization_status.json').exists():raise ValueError('Existing finalization retained; reconcile before another attempt')
        write_json(study/'finalization_status.json',dict(status='WAITING_FOR_WORKERS',formal_result_eligible=False))
        while json.loads((study/'supervisor.json').read_text())['status']=='RUNNING':time.sleep(15)
        report=json.loads((study/'report.json').read_text())
        if report['completed_cases']!=44 or report['unresolved_calls']:raise ValueError('Native study incomplete; full result publication stopped')
        if file_digest(archive/'plan.json')!=file_digest(study/'plan.json'):raise ValueError('Predeclared plan archive changed')
        for name in ['report.json','supervisor.json']:shutil.copy2(study/name,archive/name)
        env=dict(os.environ,PYTHONPATH=str(ROOT/'src'))
        write_json(study/'finalization_status.json',dict(status='RECOMPUTING_ALL_RETAINED_TRACES',formal_result_eligible=False))
        with (study/'trace_audit.log').open('x') as stream:
            subprocess.run([sys.executable,str(ROOT/'tools/audit_pose_physics_v3.py'),'--study',str(study),'--output',str(study/'trace_audit.json')],
                cwd=ROOT,env=env,stdout=stream,stderr=subprocess.STDOUT,check=True)
        audit=json.loads((study/'trace_audit.json').read_text());shutil.copy2(study/'trace_audit.json',archive/'trace_audit.json')
        if audit['status']!='PHYSICS_SENSITIVITY_TRACE_AUDIT_PASSED':raise ValueError('Retained-state integrity check failed; no validated figures produced')
        with (study/'plot.log').open('x') as stream:
            subprocess.run([str(native_python.absolute()),str(ROOT/'tools/plot_physics_sensitivity.py'),'--study',str(study),'--output',str(archive/'figures')],
                cwd=ROOT,env=env,stdout=stream,stderr=subprocess.STDOUT,check=True)
        probes=[r for r in report['results'] if r.get('kind')=='CONFIGURATION_ONLY']
        tasks=[r for r in report['results'] if r.get('kind')!='CONFIGURATION_ONLY']
        selected=[r for r in tasks if r['control_scenario']=='development_disagreement']
        fields=['scenario','profile','stimulus_confirmed','rate_agreement','positive_timing_agreement','candidate_50hz','candidate_200hz','native_50hz']
        summary=dict(status=report['status'],formal_result_eligible=False,configuration_probes=len(probes),configuration_probes_passed=sum(r['passed'] for r in probes),
            full_horizon_tasks=len(tasks),full_horizon_tasks_passed=sum(r['passed'] for r in tasks),
            rate_disagreements=sum(not r['rate_agreement'] for r in tasks),
            positive_completion_time_max_difference_s=max(abs(r['candidate_50hz']['completion_time_s']-r['candidate_200hz']['completion_time_s']) for r in tasks if r['candidate_50hz']['task_success']),
            failed_cases=[{**{k:r[k] for k in fields},'body':r['body']} for r in tasks if not r['passed']],
            selected_development_case=[{k:r[k] for k in fields} for r in selected],costs=report['costs'],
            motion_stimulus_flags_match_uncensored_trace=all(c.get('online_stimulus_flag_matches_uncensored_trace',True) for c in audit['cases']),
            plan_hash=report['plan_hash'],source_report_sha256=file_digest(study/'report.json'),trace_audit_sha256=file_digest(study/'trace_audit.json'),
            finalizer_sha256=file_digest(__file__),
            limitations=['Fixed controls and one post-hoc selected development condition; no population or learner-effect estimate.',
                'Solver readback is live USD configuration, not a measurement of solver iteration work.',
                'Control/observer rates fixed at 50/200 Hz. The finer physical step is 400 Hz; its intermediate states were not all observed.',
                'Candidate not adopted or formally frozen; old v0.1 pilot remains unchanged.'])
        write_json(archive/'summary.json',summary)
        lines=['# 物理步长与求解器敏感性 v3：实际结果','',f"状态：`{report['status']}`；`formal_result_eligible=false`。",'',
            f"配置探针 {summary['configuration_probes_passed']}/{len(probes)} 通过；完整任务 {summary['full_horizon_tasks_passed']}/{len(tasks)} 通过。",
            f"候选观察频率分类分歧 {summary['rate_disagreements']}，成功完成时间最大差 {summary['positive_completion_time_max_difference_s']:.4f} s。",'',
            '| 本体 | 场景 | 配置 | 验证 | 候选 50 Hz | 候选 200 Hz | 旧原生判据 |','|---|---|---|---|---|---|---|']
        for r in tasks:
            labels=['成功' if r[k]['task_success'] else '失败' for k in ['candidate_50hz','candidate_200hz','native_50hz']]
            lines.append(f"| {r['body']} | {r['control_scenario']} | {r['profile']} | {'通过' if r['passed'] else '未通过'} | {' | '.join(labels)} |")
        lines+=['','全部结果均保留，配置探针没有任务成功成绩。改变物理参数可能改变真实轨迹，不将全部差异归咎于判据。',
            '固定控制与事后选定开发病例不能估计总体效果，测量变更不能解释为学习收益。',
            '场景读回仅认证 USD 求解器设置。观察固定为 200 Hz，未记录更细 400 Hz 物理步长的全部中间状态。',
            '候选尚未采用为默认 judge，也未冻结新的正式 benchmark。v0.1 的成绩保持原定义。','']
        (archive/'report.zh-CN.md').write_text('\n'.join(lines))
        write_json(archive/'archive_manifest.json',dict(formal_result_eligible=False,files={str(p.relative_to(archive)):file_digest(p) for p in archive.rglob('*') if p.is_file()}))
        write_json(study/'finalization_status.json',dict(status='ARCHIVED_AWAITING_FIGURE_REVIEW',native_study_status=report['status'],formal_result_eligible=False))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--study',type=Path,required=True)
    p.add_argument('--archive',type=Path,required=True);p.add_argument('--native-python',type=Path,required=True);a=p.parse_args()
    try:finalize(a.study.resolve(),a.archive.resolve(),a.native_python)
    except Exception as exc:
        write_json(a.study/'finalization_status.json',dict(status='STOPPED_WITH_ERROR',error=str(exc),formal_result_eligible=False));raise
