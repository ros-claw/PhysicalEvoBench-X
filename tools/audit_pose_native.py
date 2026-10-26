"""Recompute native diagnostic outcomes from retained traces, without Isaac imports."""
import argparse
import json
from pathlib import Path
import sys
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from validate_pose_native import verify
from physicalevobench_x.core.hashing import digest,file_digest,write_json
from physicalevobench_x.core.schemas import ObservationFrame
from physicalevobench_x.control.geometry import rotate
from physicalevobench_x.measurement.pose_window import PoseWindowJudge,load_pose_window_config
from physicalevobench_x.sim.judge import StableLiftJudge,robot_hard_failures


def replay(path,config,limits,*,native=False):
    judge=StableLiftJudge() if native else PoseWindowJudge(config)
    started=False;previous=None;frames=0;minimum_gap=None;maximum_gap=0.
    for line in path.read_text().splitlines():
        obs=ObservationFrame.model_validate(json.loads(line)['observation'])
        if previous is not None:
            gap=obs.sim_time_s-previous
            if gap<=0:raise ValueError('Non-increasing trace clock')
            minimum_gap=gap if minimum_gap is None else min(minimum_gap,gap)
            maximum_gap=max(maximum_gap,gap)
        previous=obs.sim_time_s;frames+=1
        if obs.sim_time_s<.5-1e-12:continue
        if not started:
            if abs(obs.sim_time_s-.5)>1e-9:raise ValueError('Missing initial settled observation')
            judge.reset(obs);started=True
        q=obs.object_pose_w.quaternion_xyzw
        radius=sum(abs(rotate(q,np.eye(3)[i])[2])*obs.object_size_m[i]/2 for i in range(3))
        judge.update(obs,static_support_clear=obs.object_pose_w.position_m[2]-radius>.01,
                     hard_failures=robot_hard_failures(obs,limits))
    if not started:raise ValueError('Missing task observations')
    return dict(terminal=judge.terminal,frames=frames,last_time_s=previous,
                min_gap_s=minimum_gap,max_gap_s=maximum_gap)


def audit(study,output):
    study_type=json.loads((study/'plan.json').read_text())['study']
    if study_type=='pose_window_matched_settle_diagnostic_v2':
        from validate_pose_native_v2 import verify as verify_matched
        plan=verify_matched(study)
    elif study_type=='pose_window_native_validation_v1':plan=verify(study)
    else:raise ValueError('Unknown native diagnostic version')
    config=load_pose_window_config(ROOT/'configs/measurement/pose_path_candidate_v1.yaml')
    report=json.loads((study/'report.json').read_text())
    if (report['plan_hash']!=plan['plan_hash'] or report['unresolved_calls'] or
        report['completed_cases']!=plan['planned_calls'] or report['planned_cases']!=plan['planned_calls']):
        raise ValueError('Native diagnostic coverage incomplete')
    expected={(body,job['name']) for body,jobs in plan['jobs'].items() for job in jobs}
    if (len(report['results'])!=len(expected) or
        {(r['body'],r['scenario']) for r in report['results']}!=expected or
        report['formal_result_eligible'] is not False):raise ValueError('Report case coverage/scope mismatch')
    cases=[];all_matched=True;provenance={}
    for body,jobs in plan['jobs'].items():
        identity=study/body/'journal/identity.json'
        if json.loads(identity.read_text())!=dict(plan_hash=plan['plan_hash'],body=body):
            raise ValueError('Journal plan identity mismatch')
        provenance[str(identity)]=file_digest(identity)
        entries=sorted((study/body/'journal').glob('[0-9]*.json'))
        if len(entries)!=len(jobs):raise ValueError('Native journal coverage mismatch')
        for index,job in enumerate(jobs):
            journal=json.loads(entries[index].read_text())
            result_path=study/body/(job['name']+'.json');result=json.loads(result_path.read_text())
            if (journal['status']!='COMPLETE' or journal['request']!=dict(body=body,job=job) or
                journal['request_hash']!=digest(journal['request']) or journal['physical'] is not True or
                journal['result']!=result or result not in report['results'] or
                result['backend']!='physx' or result['infra_failure'] is not None):
                raise ValueError('Native journal/case/report mismatch')
            for path,checksum in result['evidence_files'].items():
                if file_digest(path)!=checksum:raise ValueError('Native trace hash mismatch')
                provenance[path]=checksum
            control=study/body/job['name']/'control_trace.jsonl'
            physics=study/body/job['name']/'physics_trace.jsonl'
            a=replay(control,config,result['effective_joint_limits'])
            b=replay(physics,config,result['effective_joint_limits'])
            legacy=replay(control,config,result['effective_joint_limits'],native=True)
            matched=(a['terminal']==result['candidate_50hz'] and b['terminal']==result['candidate_200hz']
                and legacy['terminal']==result['native_50hz'])
            full_horizon=bool(abs(a['last_time_s']-15.5)<1e-9 and abs(b['last_time_s']-15.5)<1e-9)
            safety_stop=bool(result['terminal']['result']['constraint_violations'])
            clocks_ok=(abs(a['min_gap_s']-.02)<1e-9 and abs(a['max_gap_s']-.02)<1e-9
                and abs(b['min_gap_s']-.005)<1e-9 and abs(b['max_gap_s']-.005)<1e-9)
            case_ok=bool(matched and clocks_ok and (full_horizon or safety_stop))
            all_matched=all_matched and case_ok
            cases.append(dict(body=body,scenario=job['name'],online_replay_matched=matched,
                clocks_verified=clocks_ok,full_horizon=full_horizon,safety_stop=safety_stop,
                candidate_50hz=a,candidate_200hz=b,native_50hz=legacy,audit_passed=case_ok))
            provenance[str(result_path)]=file_digest(result_path)
            provenance[str(entries[index])]=file_digest(entries[index])
    result=dict(status='TRACE_RECOMPUTATION_PASSED' if all_matched else 'TRACE_RECOMPUTATION_FAILED',
        formal_result_eligible=False,plan_hash=plan['plan_hash'],cases=cases,
        native_diagnostic_status=report['status'],source_report_sha256=file_digest(study/'report.json'),
        auditor_sha256=file_digest(__file__),evidence_files=provenance,
        limitations=['Same judge implementation re-executed offline; this checks retained-record consistency, not an independent physical oracle.',
            'Observed 200 Hz physics and 50 Hz control rates; not a physics-timestep sensitivity experiment.'])
    if output.exists():raise ValueError('Audit output already exists')
    write_json(output,result)
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--study',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();result=audit(args.study.resolve(),args.output.resolve())
    print(json.dumps(dict(status=result['status'],cases=len(result['cases']),native_status=result['native_diagnostic_status'])))
