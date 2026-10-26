"""Explicit post-hoc replication of all three Robotiq wide-condition skill cells."""
import argparse
import copy
import json
from pathlib import Path
import subprocess
from calibrate_distribution_v1 import verify
from audit_distribution_v1 import compare_traces
from physicalevobench_x.core.hashing import digest,file_digest,write_json

ROOT=Path(__file__).resolve().parents[1]


def plan(output,source):
    original=verify(source);report=json.loads((source/'report.json').read_text())
    audit=json.loads((source/'trace_audit.json').read_text())
    if report['status']!='CALIBRATION_EXECUTION_COMPLETE' or audit['status']!='CALIBRATION_TRACE_AUDIT_PASSED':
        raise ValueError('Complete source execution and audit required')
    data=copy.deepcopy(original);data.pop('plan_hash')
    jobs=[j for j in data['jobs']['franka_robotiq'] if j['condition']['name']=='wide' and not j['repeat_of']]
    if len(jobs)!=3:raise ValueError('All three wide-condition cells required')
    data.update(study='wide_tradeoff_posthoc_replication_v1',jobs={'franka_robotiq':jobs},planned_calls=3,
        conditions=[jobs[0]['condition']],scope='Explicit post-hoc selected development replication; no new held-out or population evidence',
        interpretation='Repeat all three Robotiq wide cells unchanged after observing high-grasp failure. Preserve both agreeing and disagreeing replications; no outcome-driven retry.',
        replication_source=dict(directory=str(source),files={name:file_digest(source/name) for name in ('plan.json','report.json','trace_audit.json')}),
        plan_generator=dict(path='tools/replicate_wide_tradeoff_v1.py',sha256=file_digest(__file__)),
        repo_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        acceptance=['Unchanged calibration execution inputs and exact cloned skill/condition cells',
            'All three physical calls retained, three scores per call replayed offline',
            'Source/replication comparison includes every public observation and actual action; disagreements are retained'])
    data['plan_hash']=digest(data);output.mkdir(parents=True,exist_ok=False);write_json(output/'plan.json',data)
    return data


def compare(study,output):
    p=verify(study);source=p['replication_source'];directory=Path(source['directory']);before=verify(directory)
    if p['plan_generator']['sha256']!=file_digest(__file__):raise ValueError('Replication generator changed')
    for name,h in source['files'].items():
        if file_digest(directory/name)!=h:raise ValueError('Original source changed')
    audit=json.loads((study/'trace_audit.json').read_text());report=json.loads((study/'report.json').read_text())
    if audit['status']!='CALIBRATION_TRACE_AUDIT_PASSED' or audit['source_report_sha256']!=file_digest(study/'report.json'):
        raise ValueError('Matching full replication audit required')
    cases=[]
    for job in p['jobs']['franka_robotiq']:
        if job not in before['jobs']['franka_robotiq']:raise ValueError('Replication is not an unchanged source cell')
        a=directory/'franka_robotiq'/job['name'];b=study/'franka_robotiq'/job['name']
        old=json.loads((directory/'franka_robotiq'/(job['name']+'.json')).read_text())
        new=json.loads((study/'franka_robotiq'/(job['name']+'.json')).read_text())
        keys=['candidate_50hz','candidate_200hz','native_50hz']
        cases.append(dict(variant=job['variant'],source_scores={k:old[k] for k in keys},replication_scores={k:new[k] for k in keys},
            all_score_fields_exact=all(old[k]==new[k] for k in keys),
            control=compare_traces(a/'control_trace.jsonl',b/'control_trace.jsonl',actions=True),
            physics=compare_traces(a/'physics_trace.jsonl',b/'physics_trace.jsonl',actions=False)))
    result=dict(status='WIDE_REPLICATION_COMPARISON_COMPLETE',formal_result_eligible=False,cases=cases,costs=report['costs'],
        all_trajectories_exact=all(c['control']['exactly_equal'] and c['physics']['exactly_equal'] for c in cases),
        source_plan_hash=before['plan_hash'],replication_plan_hash=p['plan_hash'],
        source_supervisor=json.loads((directory/'supervisor.json').read_text()),
        replication_supervisor=json.loads((study/'supervisor.json').read_text()),
        limitations=['Post-hoc selected condition; no held-out, multi-seed or population inference.',
            'Same host and reset seed; original GPU 1, replication GPU 0, both RTX A6000.',
            'Authored skill contrast, not source learning or transfer.'])
    if output.exists():raise ValueError('Existing comparison retained')
    write_json(output,result);return result


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('command',choices=['plan','compare']);ap.add_argument('--study',type=Path,required=True)
    ap.add_argument('--source',type=Path);ap.add_argument('--output',type=Path);a=ap.parse_args()
    if a.command=='plan':r=plan(a.study.resolve(),a.source.resolve());print(json.dumps(dict(plan_hash=r['plan_hash'],planned_calls=r['planned_calls'])))
    else:r=compare(a.study.resolve(),a.output.resolve());print(json.dumps(dict(status=r['status'],all_trajectories_exact=r['all_trajectories_exact'])))
