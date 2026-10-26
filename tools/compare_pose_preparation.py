"""Compare the matched native trajectory with its retained development source."""
import argparse
import json
from pathlib import Path
import numpy as np
from validate_pose_native_v2 import verify
from physicalevobench_x.core.hashing import file_digest,write_json


def compare(study,output):
    plan=verify(study);report=json.loads((study/'report.json').read_text())
    audit=json.loads((study/'trace_audit.json').read_text())
    if audit['status']!='TRACE_RECOMPUTATION_PASSED' or audit['source_report_sha256']!=file_digest(study/'report.json'):
        raise ValueError('Matching completed trace audit required')
    source_case=Path(plan['source_disagreement']['path']);source=json.loads(source_case.read_text())
    trajectory=Path(source['result']['trajectory_path'])
    if file_digest(trajectory)!=source['result']['trajectory_sha256']:raise ValueError('Source trajectory changed')
    traces={}
    for job in plan['jobs']['franka_robotiq']:
        path=study/'franka_robotiq'/job['name']/'control_trace.jsonl'
        traces[job['name']]=[json.loads(line) for line in path.read_text().splitlines() if 'native_action' in json.loads(line)]
    rows=traces['matched_original_settle']
    current=dict(sim_time_s=np.array([r['observation']['sim_time_s'] for r in rows]),
        object_position_m=np.array([r['observation']['object_pose_w']['position_m'] for r in rows]),
        tcp_position_m=np.array([r['observation']['tcp_pose_w']['position_m'] for r in rows]),
        native_actions=np.array([r['native_action'] for r in rows]))
    comparisons={}
    with np.load(trajectory,allow_pickle=False) as old:
        for key,value in current.items():
            same_shape=value.shape==old[key].shape
            comparisons[key]=dict(source_shape=list(old[key].shape),current_shape=list(value.shape),
                elementwise_exact_equal=bool(same_shape and np.array_equal(value,old[key])),
                max_absolute_difference=float(np.max(np.abs(value-old[key]))) if same_shape else None)
    matched_initial=next(r['observation'] for r in rows if r['observation']['sim_time_s']>=.5-1e-9)
    fixed_initial=next(r['observation'] for r in traces['fixed_tcp_settle'] if r['observation']['sim_time_s']>=.5-1e-9)
    evidence=dict(status='MATCHED_PREPARATION_COMPARISON_COMPLETE',formal_result_eligible=False,
        source_case_sha256=file_digest(source_case),source_trajectory_sha256=file_digest(trajectory),
        matched_study_plan_hash=plan['plan_hash'],source_report_sha256=file_digest(study/'report.json'),
        audit_sha256=file_digest(study/'trace_audit.json'),tool_sha256=file_digest(__file__),
        arrays=comparisons,all_arrays_equal=all(c['elementwise_exact_equal'] for c in comparisons.values()),
        preparation_tcp_difference_m=float(np.linalg.norm(np.array(matched_initial['tcp_pose_w']['position_m'])-fixed_initial['tcp_pose_w']['position_m'])),
        outcomes=[{k:r[k] for k in ['scenario','candidate_50hz','candidate_200hz','native_50hz','passed']} for r in report['results']],
        limitation='Two controlled reruns of one post-hoc selected development condition; not a population or transfer-effect estimate.')
    if output.exists():raise ValueError('Comparison destination exists')
    write_json(output,evidence);return evidence


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--study',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    result=compare(args.study.resolve(),args.output.resolve());print(json.dumps(dict(status=result['status'],all_arrays_equal=result['all_arrays_equal'])))
