"""CPU-only audit of a fully recorded calibration plan."""
from pathlib import Path
import numpy as np
from ..core.schemas import Pose
from ..core.hashing import write_json,file_digest
from ..control.geometry import angle


def recover_completed_trace(output):
    """Recover only the serialization-failed 505-step calibration plan, with provenance."""
    import json
    from ..core.schemas import ObservationFrame
    output=Path(output)
    rows=[json.loads(line) for line in (output/'trace.jsonl').read_text().splitlines()]
    if len(rows)!=505:
        raise ValueError('Calibration plan incomplete; cannot recover')
    observations=[ObservationFrame.model_validate(r['observation']) for r in rows]
    if any(abs(o.sim_time_s-i*.02)>1e-6 for i,o in enumerate(observations)):
        raise ValueError('Unexpected calibration clock')
    gaps=[observations[i].gripper_opening_width_m for i in (75,150,225)]
    gripper_ok=gaps[0]>.06 and gaps[1]<.02 and gaps[2]>.06
    reference=observations[225].tcp_pose_w
    checks=[]
    for i,name in enumerate(('x','y','z')):
        desired=np.asarray(reference.position_m)+np.eye(3)[i]*.01
        result=observations[255+i*60].tcp_pose_w
        delta=np.asarray(result.position_m)-reference.position_m
        error=float(np.linalg.norm(np.asarray(result.position_m)-desired))
        checks.append(dict(axis=name,requested_delta_m=(np.eye(3)[i]*.01).tolist(),
            measured_delta_m=delta.tolist(),position_error_m=error,passed=bool(error<=.0025 and delta[i]>.0075)))
    target=Pose.model_validate(rows[405]['command']['tcp_pose_w'])
    rotated=observations[455].tcp_pose_w
    rotation_error=angle(rotated.quaternion_xyzw,target.quaternion_xyzw)
    position_error=float(np.linalg.norm(np.asarray(rotated.position_m)-reference.position_m))
    rotation_ok=rotation_error<=.02 and position_error<=.003
    report=dict(backend='physx',status='GPU_VERIFIED' if gripper_ok and all(c['passed'] for c in checks) and rotation_ok else 'GPU_CHECK_FAILED',
        gripper_open_closed_reopened_width_m=gaps,gripper_passed=gripper_ok,world_axes=checks,
        rotation=dict(requested_world_yaw_rad=.1,error_rad=rotation_error,tcp_position_drift_m=position_error,passed=rotation_ok),
        initial=observations[0].model_dump(),trace_sha256=file_digest(output/'trace.jsonl'),formal_result_eligible=False,
        recovered_from_completed_trace=True,recovery_reason='numpy boolean JSON serialization failed after all 505 physical steps')
    if (output/'calibration.json').exists():
        raise ValueError('Refusing to overwrite existing report')
    write_json(output/'calibration.json',report)
    return report
