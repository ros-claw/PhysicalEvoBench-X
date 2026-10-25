"""Descriptive trace measurements; never changes the frozen success predicate."""
import json
from pathlib import Path
import numpy as np
from physicalevobench_x.core.hashing import file_digest


def measure_rows(rows, metadata):
    initial = metadata['initial']
    start = initial['sim_time_s']
    observations = [r['observation'] for r in rows if r['observation']['sim_time_s'] >= start]
    terminal = metadata['terminal']['observation']
    if not observations or terminal['sim_time_s'] > observations[-1]['sim_time_s']:
        observations.append(terminal)
    heights = np.array([o['object_pose_w']['position_m'][2] for o in observations])
    elevated = heights-initial['object_pose_w']['position_m'][2] >= .08-1e-12
    linear = np.linalg.norm([o['object_linear_velocity_w'] for o in observations], axis=1)
    angular = np.linalg.norm([o['object_angular_velocity_w'] for o in observations], axis=1)
    n = int(elevated.sum())
    stages = [r['stage'] for r in rows if r['observation']['sim_time_s'] >= start]
    lift_rows = [r for r in rows if r['stage']=='LIFT' and r.get('canonical_command')]
    reference_peak = actual_peak = tracking_peak = None
    if lift_rows:
        times=np.array([r['observation']['sim_time_s'] for r in lift_rows])
        reference=np.array([r['canonical_command']['tcp_pose_w']['position_m'] for r in lift_rows])
        actual=np.array([r['observation']['tcp_pose_w']['position_m'] for r in lift_rows])
        tracking_peak=float(np.linalg.norm(actual-reference,axis=1).max())
        if len(times)>1:
            dt=np.diff(times)
            if np.any(dt<=0):raise ValueError('Nonmonotonic diagnostic trace')
            reference_peak=float(np.max(np.linalg.norm(np.diff(reference,axis=0),axis=1)/dt))
            actual_peak=float(np.max(np.linalg.norm(np.diff(actual,axis=0),axis=1)/dt))
    return dict(recorded_control_samples=len(observations), elevated_samples=n,
                elevated_angular_over_limit_samples=int(np.sum(elevated & (angular > .5))),
                elevated_linear_over_limit_samples=int(np.sum(elevated & (linear > .03))),
                elevated_angular_over_limit_fraction=float(np.mean(angular[elevated] > .5)) if n else None,
                elevated_angular_min_radps=float(np.min(angular[elevated])) if n else None,
                elevated_angular_median_radps=float(np.median(angular[elevated])) if n else None,
                elevated_angular_max_radps=float(np.max(angular[elevated])) if n else None,
                final_object_angular_radps=float(angular[-1]),
                final_stage=stages[-1] if stages else None,
                stage_times_s=metadata.get('stage_times', {}),
                lift_reference_peak_speed_mps=reference_peak,
                lift_measured_tcp_peak_speed_mps=actual_peak,
                lift_reference_tracking_peak_error_m=tracking_peak,
                # Predicates overlap. These counts are not a causal decomposition.
                sample_note='Control samples, including terminal state; not independent learning repeats. Speed blockers overlap.')


def measure_episode(result):
    trajectory = Path(result['trajectory_path'])
    if file_digest(trajectory) != result['trajectory_sha256']:
        raise ValueError('Trajectory checksum mismatch')
    metadata_path = trajectory.with_suffix('.json')
    trace_path = trajectory.with_name(result['episode_id']+'_trace.jsonl')
    metadata = json.loads(metadata_path.read_text())
    rows = [json.loads(line) for line in trace_path.read_text().splitlines()]
    measured = measure_rows(rows, metadata)
    return dict(episode_id=result['episode_id'], task_success=result['task_success'],
                termination_reason=result['termination_reason'], max_lift_m=result['max_lift_m'],
                hold_time_s=result['hold_time_s'], completion_time_s=result['completion_time_s'],
                measurements=measured,
                evidence_files={str(p):file_digest(p) for p in (trajectory, metadata_path, trace_path)})
