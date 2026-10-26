"""Check whether the v3 baseline reproduces the retained selected development rollout."""
import argparse
import json
from pathlib import Path
import numpy as np
from validate_pose_physics_v3 import verify
from physicalevobench_x.core.hashing import file_digest,write_json


def compare(study,output):
    plan=verify(study);source_path=Path(plan['source_disagreement']['path']);source=json.loads(source_path.read_text())
    jobs=[j for j in plan['jobs']['franka_robotiq'] if j['profile']=='baseline' and j['scenario']=='development_disagreement']
    if len(jobs)!=1:raise ValueError('One predefined selected-case baseline required')
    job=jobs[0];path=study/'franka_robotiq'/(job['name']+'.json');result=json.loads(path.read_text())
    trace=study/'franka_robotiq'/job['name']/'control_trace.jsonl'
    if file_digest(trace)!=result['evidence_files'][str(trace)]:raise ValueError('Current baseline trace changed')
    original=Path(source['result']['trajectory_path'])
    if file_digest(original)!=source['result']['trajectory_sha256']:raise ValueError('Source trajectory changed')
    rows=[json.loads(l) for l in trace.read_text().splitlines() if 'native_action' in json.loads(l)]
    arrays=dict(sim_time_s=np.array([r['observation']['sim_time_s'] for r in rows]),
        object_position_m=np.array([r['observation']['object_pose_w']['position_m'] for r in rows]),
        tcp_position_m=np.array([r['observation']['tcp_pose_w']['position_m'] for r in rows]),
        native_actions=np.array([r['native_action'] for r in rows]))
    comparisons={}
    with np.load(original,allow_pickle=False) as archived:
        for name,current in arrays.items():
            same_shape=current.shape==archived[name].shape
            comparisons[name]=dict(source_shape=list(archived[name].shape),current_shape=list(current.shape),
                elementwise_exact_equal=bool(same_shape and np.array_equal(current,archived[name])),
                max_absolute_difference=float(np.max(abs(current-archived[name]))) if same_shape else None)
    source_trace=original.with_name(source['result']['episode_id']+'_trace.jsonl')
    old_observations=[json.loads(l)['observation'] for l in source_trace.read_text().splitlines()]
    def public_state(o):return {k:v for k,v in o.items() if k!='episode_id'}
    all_observations_equal=(len(old_observations)==len(rows) and
        all(public_state(old)==public_state(new['observation']) for old,new in zip(old_observations,rows)))
    record=dict(status='PHYSICS_BASELINE_COMPARISON_COMPLETE',formal_result_eligible=False,plan_hash=plan['plan_hash'],
        arrays=comparisons,all_arrays_equal=all(c['elementwise_exact_equal'] for c in comparisons.values()),
        all_public_observations_equal_except_episode_id=all_observations_equal,
        original_native_success=source['result']['task_success'],current_native_terminal=result['native_50hz'],
        candidate_50hz=result['candidate_50hz'],candidate_200hz=result['candidate_200hz'],
        evidence_files={str(p):file_digest(p) for p in [source_path,original,source_trace,path,trace]},tool_sha256=file_digest(__file__),
        limitation='One previously selected development condition; exact reproduction does not establish generality or learner improvement.')
    if output.exists():raise ValueError('Comparison destination exists')
    write_json(output,record);return record


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--study',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();r=compare(a.study.resolve(),a.output.resolve());print(json.dumps(dict(status=r['status'],all_arrays_equal=r['all_arrays_equal'],all_public_observations_equal=r['all_public_observations_equal_except_episode_id'])))
