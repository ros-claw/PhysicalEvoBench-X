"""Review finite development coverage without treating successful lift height as stable success."""
import argparse
import json
from pathlib import Path
import numpy as np
from physicalevobench_x.core.hashing import file_digest, write_json


def analyze(run):
    plan=json.loads((run/'plan.json').read_text())
    raw=json.loads((run/'range_check.json').read_text())
    require_count=len(plan['cases'])==len(raw['measurements'])==23
    if not require_count:
        raise ValueError('Incomplete development range plan')
    measurements=[]
    for case,result in zip(plan['cases'],raw['measurements']):
        if case['case_id']!=result['case_id']:
            raise ValueError('Plan/result order changed')
        trajectory=run/'trajectories'
        trace=trajectory/(result['episode_id']+'_trace.jsonl')
        metadata=trajectory/(result['episode_id']+'.json')
        meta=json.loads(metadata.read_text())
        rows=[json.loads(line) for line in trace.read_text().splitlines()]
        lift=[r for r in rows if r['stage']=='LIFT']
        peak_reference,peak_actual=None,None
        if len(lift)>1:
            times=np.array([r['observation']['sim_time_s'] for r in lift])
            command=np.array([r['canonical_command']['tcp_pose_w']['position_m'] for r in lift])
            actual=np.array([r['observation']['tcp_pose_w']['position_m'] for r in lift])
            peak_reference=float(np.linalg.norm(np.diff(command,axis=0)/np.diff(times)[:,None],axis=1).max())
            peak_actual=float(np.linalg.norm(np.diff(actual,axis=0)/np.diff(times)[:,None],axis=1).max())
        measurements.append(dict(case_id=case['case_id'],episode_id=result['episode_id'],
            task_success=result['task_success'],termination_reason=result['termination_reason'],
            mechanically_reached_task_or_lift_goal=result['task_success'] or 'LIFT' in meta['stage_times'],
            constraint_violations=result['constraint_violations'],
            requested_parameters=case['skill']['parameters'],stage_times=meta['stage_times'],
            peak_reference_lift_speed_mps=peak_reference,peak_actual_lift_speed_mps=peak_actual,
            minimum_actual_tcp_z_m=min(r['observation']['tcp_pose_w']['position_m'][2] for r in rows),
            reference_speed_bound_respected=peak_reference is not None and peak_reference<=case['skill']['parameters']['lift_vmax_mps']+1e-8,
            max_lift_m=result['max_lift_m'],hold_time_s=result['hold_time_s'],
            trace_sha256=file_digest(trace),metadata_sha256=file_digest(metadata)))
    return dict(backend='physx',status='GPU_MEASUREMENTS_REVIEWED',embodiment=plan['embodiment'],
        source_run=str(run.resolve()),
        plan_sha256=file_digest(run/'plan.json'),runtime_inputs_sha256=file_digest(run/'trajectories/runtime_inputs.json'),
        measurements=measurements,successes=sum(m['task_success'] for m in measurements),
        all_measured_cases_mechanically_executable=all(m['mechanically_reached_task_or_lift_goal'] and not m['constraint_violations'] for m in measurements),
        all_measured_lift_reference_speeds_bounded=all(m['reference_speed_bound_respected'] for m in measurements),
        formal_result_eligible=False,limitations='Finite development points; neither continuous-domain safety proof nor formal performance evaluation.')


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--run',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    result=analyze(a.run)
    write_json(a.output,result)
    print(json.dumps({k:result[k] for k in ('embodiment','successes','all_measured_cases_mechanically_executable','all_measured_lift_reference_speeds_bounded')}))
