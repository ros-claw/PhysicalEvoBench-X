"""Audit every calibration call, replay scores and compare predeclared repeats."""
import argparse
from itertools import zip_longest
import json
from pathlib import Path
import numpy as np
from calibrate_distribution_v1 import verify,check_readback
from audit_pose_native import replay
from audit_pose_physics_v3 import configuration_matches,trace_clock_summary,motion_summary
from physicalevobench_x.core.hashing import digest,file_digest,write_json
from physicalevobench_x.measurement.pose_window import load_pose_window_config

ROOT=Path(__file__).resolve().parents[1]


def compare_traces(a,b,*,actions):
    mismatches=0;first=None;count=0
    with a.open() as left,b.open() as right:
        for index,(aa,bb) in enumerate(zip_longest(left,right)):
            count+=1
            same=False
            if aa is not None and bb is not None:
                aa=json.loads(aa);bb=json.loads(bb)
                for row in (aa,bb):row['observation'].pop('episode_id',None)
                same=(aa['observation']==bb['observation'] and
                    (not actions or aa.get('native_action')==bb.get('native_action')))
            if not same:
                mismatches+=1
                if first is None:first=index
    return dict(compared_rows=count,mismatched_rows=mismatches,first_mismatch_row=first,exactly_equal=mismatches==0)


def audit(study,output):
    p=verify(study);report=json.loads((study/'report.json').read_text())
    expected={(body,j['name']) for body,jobs in p['jobs'].items() for j in jobs}
    if (report['status']!='CALIBRATION_EXECUTION_COMPLETE' or report['unresolved_calls'] or
        report['formal_result_eligible'] is not False or report['plan_hash']!=p['plan_hash'] or
        report['completed_cases']!=len(expected) or len(report['results'])!=len(expected) or
        {(r['body'],r['scenario']) for r in report['results']}!=expected):raise ValueError('Incomplete/mismatched coverage')
    config=load_pose_window_config(ROOT/'configs/measurement/pose_path_candidate_v1.yaml')
    cases=[];repeats=[];provenance={};costs=dict(known_complete_physical_calls=0,observed_sim_time_s=0.,episode_wall_time_s=0.)
    for body,jobs in p['jobs'].items():
        journal=study/body/'journal';identity=journal/'identity.json'
        if json.loads(identity.read_text())!=dict(body=body,plan_hash=p['plan_hash']):raise ValueError('Journal identity changed')
        entries=sorted(journal.glob('[0-9]*.json'))
        if len(entries)!=len(jobs):raise ValueError('Unexpected physical call coverage')
        for index,job in enumerate(jobs):
            entry=json.loads(entries[index].read_text());result_path=study/body/(job['name']+'.json')
            r=json.loads(result_path.read_text());request=dict(body=body,job=job)
            if (entry['status']!='COMPLETE' or entry['physical'] is not True or entry['request']!=request or
                entry['request_hash']!=digest(request) or entry['result']!=r or r not in report['results'] or
                r['backend']!='physx' or r['infra_failure'] is not None or r['formal_result_eligible'] is not False or
                r['body']!=body or r['scenario']!=job['name'] or r['condition']!=job['condition'] or r['variant']!=job['variant']):
                raise ValueError('Journal/result/report identity mismatch')
            for path,h in r['evidence_files'].items():
                if file_digest(path)!=h:raise ValueError('Raw evidence changed')
                provenance[path]=h
            raw=study/body/job['name'];readback=json.loads((raw/'readback.json').read_text())
            if (readback!=dict(solver=r['solver_readback'],object=r['readback']) or
                not check_readback(job['condition'],r['readback']) or not configuration_matches(r['solver_readback'],p['physics'])):
                raise ValueError('Applied condition/solver readback mismatch')
            control=raw/'control_trace.jsonl';physics=raw/'physics_trace.jsonl'
            cr=[json.loads(line) for line in control.read_text().splitlines()]
            pr=[json.loads(line) for line in physics.read_text().splitlines()]
            if any(o['observation']['object_size_m']!=job['condition']['size_m'] for o in cr+pr):
                raise ValueError('Observation geometry differs from actual condition')
            # Every observed control state after stepping has a corresponding physical sample.
            for a,b in zip(cr[1:],pr[3::4],strict=True):
                aa=dict(a['observation']);bb=dict(b['observation'])
                aa.pop('episode_id',None);bb.pop('episode_id',None)
                if aa!=bb:raise ValueError('Control and physics state disagree at a shared tick')
            clocks=trace_clock_summary([o['observation']['sim_time_s'] for o in cr],
                [o['observation']['sim_time_s'] for o in pr],r['observed_sim_time_s'],r['physics_samples'])
            safety=bool(r['terminal']['result']['constraint_violations'])
            if not clocks['clocks_verified'] or not (clocks['full_horizon'] or safety):raise ValueError('Truncated/unexplained trace')
            if r['physics_steps']!=r['physics_samples'] or abs(r['observed_sim_time_s']-.005*r['physics_steps'])>1e-9:
                raise ValueError('Physics cost accounting mismatch')
            outcomes={key:replay(path,config,r['effective_joint_limits'],native=native)['terminal']
                for key,path,native in [('candidate_50hz',control,False),('candidate_200hz',physics,False),('native_50hz',control,True)]}
            if any(outcomes[k]!=r[k] for k in outcomes):raise ValueError('Online/offline score mismatch')
            motion=motion_summary(cr,pr,'nominal')
            stage_counts={name:sum(row.get('executor_stage')==name for row in cr) for name in sorted({row['executor_stage'] for row in cr if 'executor_stage' in row})}
            cases.append(dict(body=body,scenario=job['name'],condition=job['condition']['name'],variant=job['variant'],
                repeat_of=job['repeat_of'],outcomes=outcomes,clocks=clocks,safety_stop=safety,
                macro_motion=motion,executor_stage_counts=stage_counts,readback_verified=True,online_replay_matched=True))
            costs['known_complete_physical_calls']+=1
            for key in ('observed_sim_time_s','episode_wall_time_s'):costs[key]+=r[key]
            provenance[str(result_path)]=file_digest(result_path);provenance[str(entries[index])]=file_digest(entries[index])
            if job['repeat_of']:
                previous=study/body/job['repeat_of']
                repeats.append(dict(body=body,variant=job['variant'],original=job['repeat_of'],repeat=job['name'],
                    control=compare_traces(previous/'control_trace.jsonl',control,actions=True),
                    physics=compare_traces(previous/'physics_trace.jsonl',physics,actions=False)))
    if costs!=report['costs']:raise ValueError('Report costs disagree with journal')
    result=dict(status='CALIBRATION_TRACE_AUDIT_PASSED',formal_result_eligible=False,plan_hash=p['plan_hash'],
        cases=cases,repeats=repeats,costs=costs,rate_disagreements=sum(c['outcomes']['candidate_50hz']['task_success']!=
            c['outcomes']['candidate_200hz']['task_success'] for c in cases),
        source_report_sha256=file_digest(study/'report.json'),evidence_files=provenance,
        audit_tools={name:file_digest(ROOT/'tools'/name) for name in ('audit_distribution_v1.py','audit_pose_native.py','audit_pose_physics_v3.py','state_consistency_metrics.py')},
        limitations=['Offline reuse of judge checks consistency; not an independent physical oracle.',
            'Only the tall condition has predeclared physical repeats; other contrasts are one paired trial per cell.',
            'Repeats share the same host, condition and reset seed; exact equality is reset reproducibility, not multi-seed or machine robustness.',
            'High-grasp and slow-lift skills were authored before execution, not acquired by a learner.',
            'Initial successes are first terminal decisions, not certification of continuous success through the full horizon.',
            p['interpretation'],'No new formal distribution, held-out learning, LLM effect, positive transfer or population inference.'])
    if output.exists():raise ValueError('Audit output already exists; retain prior attempt')
    write_json(output,result);return result


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--study',type=Path,required=True);ap.add_argument('--output',type=Path,required=True)
    a=ap.parse_args();r=audit(a.study.resolve(),a.output.resolve());print(json.dumps(dict(status=r['status'],cases=len(r['cases']),repeats=len(r['repeats']))))
