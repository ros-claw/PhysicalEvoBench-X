"""Reproducible measured command/tracking diagnostics; no causal contact claims."""
import argparse
import json
from pathlib import Path
import numpy as np
from physicalevobench_x.core.hashing import write_json, file_digest


def diagnose(run):
    report = json.loads((run/'sensitivity.json').read_text())
    results = []
    for item in report['measurements']:
        trace = run/'trajectories'/(item['episode_id']+'_trace.jsonl')
        rows = [json.loads(line) for line in trace.read_text().splitlines()]
        stages = {}
        for stage in dict.fromkeys(row['stage'] for row in rows):
            group = [r for r in rows if r['stage'] == stage and r['canonical_command']]
            if not group:
                continue
            t = np.array([r['observation']['sim_time_s'] for r in group])
            actual = np.array([r['observation']['tcp_pose_w']['position_m'] for r in group])
            desired = np.array([r['canonical_command']['tcp_pose_w']['position_m'] for r in group])
            tracking = np.linalg.norm(desired-actual, axis=1)
            peak = lambda pos: float(np.linalg.norm(np.diff(pos, axis=0)/np.diff(t)[:, None], axis=1).max()) if len(t)>1 else None
            stages[stage] = dict(samples=len(group), command_peak_speed_mps=peak(desired),
                actual_peak_speed_mps=peak(actual), max_tracking_error_m=float(tracking.max()),
                final_tracking_error_m=float(tracking[-1]),
                final_requested_z_m=float(desired[-1, 2]), final_actual_z_m=float(actual[-1, 2]))
        held = [r for r in rows if r['stage'] == 'HOLD']
        stability = None
        if held:
            linear = np.linalg.norm([r['observation']['object_linear_velocity_w'] for r in held], axis=1)
            angular = np.linalg.norm([r['observation']['object_angular_velocity_w'] for r in held], axis=1)
            stability = dict(samples=len(held),linear_speed_exceedances=int((linear>.03).sum()),
                angular_speed_exceedances=int((angular>.5).sum()),maximum_linear_speed_mps=float(linear.max()),
                maximum_angular_speed_radps=float(angular.max()),
                note='Speed conditions only; relative-pose drift and continuous hold are judged separately.')
        results.append(dict(**item, trace_sha256=file_digest(trace), stages=stages,hold_stability=stability))
    return dict(backend='physx', embodiment=report['embodiment'], measurements=results,
                formal_result_eligible=False,
                limitations='Kinematic tracking measurements cannot establish collision/contact causality.')


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--run', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    write_json(a.output, diagnose(a.run))
