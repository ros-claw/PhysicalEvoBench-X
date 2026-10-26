"""Audit fixed-rate physics sensitivity records and retain all profile outcomes."""
import argparse
from collections import Counter
import json
from pathlib import Path
import numpy as np
from validate_pose_physics_v3 import verify
from audit_pose_native import replay
from state_consistency_metrics import angular_pose_increments
from physicalevobench_x.core.hashing import digest,file_digest,write_json
from physicalevobench_x.measurement.pose_window import load_pose_window_config

ROOT=Path(__file__).resolve().parents[1]


def trace_clock_summary(control_times,observer_times,observed_sim_time,expected_samples):
    ct=np.asarray(control_times);pt=np.asarray(observer_times)
    if len(ct)<2 or len(pt)<2:raise ValueError('Missing retained clock samples')
    return dict(clocks_verified=bool(np.allclose(np.diff(ct),.02,atol=1e-9,rtol=0)
        and np.allclose(np.diff(pt),.005,atol=1e-9,rtol=0)
        and len(pt)==expected_samples and abs(pt[-1]-observed_sim_time)<1e-9),
        full_horizon=bool(abs(pt[-1]-15.5)<1e-9 and abs(ct[-1]-15.5)<1e-9))


def configuration_matches(settings,profile):
    rows=settings['articulations']+settings['dynamic_bodies'];scenes=settings['scenes']
    return bool(settings['articulations'] and settings['dynamic_bodies'] and scenes and
        abs(settings['physics_dt_s']-profile['physics_dt_s'])<1e-12 and abs(settings['control_dt_s']-.02)<1e-12 and
        all(r['position']==profile['position_iterations'] and r['velocity']==profile['velocity_iterations'] for r in rows) and
        all(s['min_position']<=profile['position_iterations']<=s['max_position'] and
            s['min_velocity']<=profile['velocity_iterations']<=s['max_velocity'] for s in scenes))


def motion_summary(control_rows,physics_rows,scenario):
    obs=[r['observation'] for r in physics_rows];t=np.array([o['sim_time_s'] for o in obs])
    xyz=np.array([o['object_pose_w']['position_m'] for o in obs])
    if not np.allclose(np.diff(t),.005,rtol=0,atol=1e-9):raise ValueError('Observer rate changed')
    start=np.flatnonzero(abs(t-.5)<1e-9)
    if len(start)!=1:raise ValueError('Missing settled initial state')
    lift=xyz[:,2]-xyz[start[0],2]
    speed=np.r_[np.full(20,np.nan),np.convolve(np.linalg.norm(np.diff(xyz,axis=0),axis=1),np.ones(20),mode='valid')/.1]
    q=np.array([o['object_pose_w']['quaternion_xyzw'] for o in obs])
    rotation_segments=np.linalg.norm(angular_pose_increments(t,q),axis=1)*.005
    angular_window=np.r_[np.full(20,np.nan),np.convolve(rotation_segments,np.ones(20),mode='valid')/.1]
    trigger=next((r['observation']['sim_time_s'] for r in control_rows if r.get('applied')),None)
    mask=(t>=.5)&(lift>=.08)
    if scenario=='oscillate':mask&=t>=((trigger+1.) if trigger is not None else np.inf)
    elevated=speed[mask&np.isfinite(speed)]
    opening=[o['gripper_opening_width_m'] for o in obs if trigger is not None and o['sim_time_s']>trigger]
    active_x=xyz[mask,0]
    final=t>=max(.5,t[-1]-5.)
    native=np.linalg.norm([o['object_angular_velocity_w'] for o in obs],axis=1)
    maximum_lift=float(np.max(lift[t>=.5]));peak=float(np.max(elevated)) if len(elevated) else 0.
    opening_peak=max(opening,default=0.)
    stimulus=(scenario in ('nominal','development_disagreement') or (trigger is not None and maximum_lift>=.08 and
        (scenario!='oscillate' or peak>.03) and (scenario!='release' or opening_peak>=.06)))
    return dict(trigger_time_s=trigger,max_lift_m=maximum_lift,observed_elevated_window_speed_peak_mps=peak,
        elevated_window_samples=len(elevated),elevated_samples_above_speed_limit=int(np.sum(elevated>.03)),
        elevated_world_x_range_m=float(np.ptp(active_x)) if len(active_x) else 0.,release_opening_peak_m=opening_peak,
        final_5s_native_angular_median_radps=float(np.median(native[final])),
        final_5s_pose_angular_window_median_radps=float(np.median(angular_window[final])),
        final_5s_pose_linear_window_median_mps=float(np.median(speed[final])),
        final_5s_height_range_m=float(np.ptp(xyz[final,2])),
        stimulus_confirmed_from_uncensored_pose_trace=bool(stimulus))


def audit(study,output):
    plan=verify(study);report=json.loads((study/'report.json').read_text())
    expected={(body,j['name']) for body,jobs in plan['jobs'].items() for j in jobs}
    if (report['unresolved_calls'] or report['plan_hash']!=plan['plan_hash'] or report['completed_cases']!=len(expected)
        or len(report['results'])!=len(expected) or {(r['body'],r['scenario']) for r in report['results']}!=expected):
        raise ValueError('Sensitivity coverage incomplete')
    config=load_pose_window_config(ROOT/'configs/measurement/pose_path_candidate_v1.yaml')
    cases=[];provenance={}
    for body,jobs in plan['jobs'].items():
        identity=study/body/'journal/identity.json'
        if json.loads(identity.read_text())!=dict(body=body,plan_hash=plan['plan_hash']):raise ValueError('Journal identity mismatch')
        entries=sorted((study/body/'journal').glob('[0-9]*.json'))
        if len(entries)!=len(jobs):raise ValueError('Journal coverage mismatch')
        for index,job in enumerate(jobs):
            record=json.loads(entries[index].read_text());path=study/body/(job['name']+'.json');r=json.loads(path.read_text())
            request=dict(body=body,job=job)
            if (record['status']!='COMPLETE' or record['physical'] is not True or record['request']!=request or
                record['request_hash']!=digest(request) or record['result']!=r or r not in report['results'] or
                r['backend']!='physx' or r['infra_failure'] is not None or r['profile']!=job['profile'] or
                r['control_scenario']!=job['scenario'] or r['formal_result_eligible'] is not False):raise ValueError('Case/journal/report mismatch')
            for name,checksum in r['evidence_files'].items():
                if file_digest(name)!=checksum:raise ValueError('Evidence hash mismatch')
                provenance[name]=checksum
            directory=study/body/job['name'];settings=json.loads((directory/'solver_readback.json').read_text())
            profile=plan['profiles'][job['profile']]
            if settings!=r['solver_readback'] or not configuration_matches(settings,profile):raise ValueError('Applied solver configuration mismatch')
            if (r['physics_dt_s']!=profile['physics_dt_s'] or abs(r['control_dt_s']-.02)>1e-12 or
                abs(r['observed_sim_time_s']-r['physics_steps']*profile['physics_dt_s'])>1e-9):raise ValueError('Time accounting mismatch')
            control=directory/'control_trace.jsonl';physics=directory/'physics_trace.jsonl'
            cr=[json.loads(line) for line in control.read_text().splitlines()]
            pr=[json.loads(line) for line in physics.read_text().splitlines()]
            ct=np.array([row['observation']['sim_time_s'] for row in cr]);pt=np.array([row['observation']['sim_time_s'] for row in pr])
            clock_summary=trace_clock_summary(ct,pt,r['observed_sim_time_s'],r['physics_samples'])
            clocks=clock_summary['clocks_verified']
            case=dict(body=body,profile=job['profile'],scenario=job['scenario'],source_validation_passed=r['passed'],clocks_verified=clocks)
            if job['scenario']=='configuration_probe':
                matched=bool(len(cr)==2 and len(pr)==8 and abs(pt[-1]-.04)<1e-9 and
                    r['physics_steps']==2*profile['decimation'] and all(r[k] is None for k in ('candidate_50hz','candidate_200hz','native_50hz')))
                case.update(kind='CONFIGURATION_ONLY',audit_passed=bool(clocks and matched))
            else:
                a=replay(control,config,r['effective_joint_limits']);b=replay(physics,config,r['effective_joint_limits'])
                old=replay(control,config,r['effective_joint_limits'],native=True)
                matched=(a['terminal']==r['candidate_50hz'] and b['terminal']==r['candidate_200hz'] and old['terminal']==r['native_50hz'])
                full=clock_summary['full_horizon']
                safety=bool(r['terminal']['result']['constraint_violations'])
                motion=motion_summary(cr,pr,job['scenario'])
                case.update(kind='FULL_HORIZON',candidate_50hz=a['terminal'],candidate_200hz=b['terminal'],native_50hz=old['terminal'],
                    full_horizon=full,safety_stop=safety,online_replay_matched=matched,motion=motion,
                    online_stimulus_flag_matches_uncensored_trace=motion['stimulus_confirmed_from_uncensored_pose_trace']==r['stimulus_confirmed'],
                    audit_passed=bool(clocks and matched and (full or safety)))
            cases.append(case);provenance[str(path)]=file_digest(path);provenance[str(entries[index])]=file_digest(entries[index])
    result=dict(status='PHYSICS_SENSITIVITY_TRACE_AUDIT_PASSED' if all(c['audit_passed'] for c in cases) else 'PHYSICS_SENSITIVITY_TRACE_AUDIT_FAILED',
        formal_result_eligible=False,plan_hash=plan['plan_hash'],native_study_status=report['status'],cases=cases,
        coverage=dict(Counter(c['kind'] for c in cases)),source_report_sha256=file_digest(study/'report.json'),
        evidence_files=provenance,audit_tools={p.name:file_digest(p) for p in [Path(__file__),ROOT/'tools/audit_pose_native.py',ROOT/'tools/state_consistency_metrics.py']},
        limitations=['Same judge implementation replayed; retained-state consistency is not an independent physical oracle.',
            'One fixed control condition plus one selected development case; not a population or learning-effect estimate.',
            'Raw pose-path stimulus summaries use the entire retained trajectory, including after first judge termination.'])
    if output.exists():raise ValueError('Audit destination exists')
    write_json(output,result);return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--study',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();r=audit(args.study.resolve(),args.output.resolve());print(json.dumps(dict(status=r['status'],coverage=r['coverage'])))
