"""Evidence validation, never trusts a user-supplied formal_result_eligible flag."""
import json
import re
from pathlib import Path
from ..core.hashing import file_digest
from ..core.schemas import EpisodeResult


def validate_run(directory):
    root = Path(directory)
    required = ('run_manifest.json','dependency_snapshot.json','protocol_snapshot.yaml',
                'embodiment_diff.json','costs.json','aliases.json')
    for name in required:
        if not (root/name).is_file():
            raise ValueError('Missing evidence: '+name)
    manifest = json.loads((root/'run_manifest.json').read_text())
    for key in ('task_definition_hash','split_manifest_hash','controller_hash','adapter_hash','freeze_hash'):
        if not re.fullmatch('[0-9a-f]{64}', manifest.get(key,'')):
            raise ValueError('Invalid or placeholder '+key)
    if manifest.get('backend') != 'physx':
        raise ValueError('Physical reporting rejects fake backend')
    dependencies = json.loads((root/'dependency_snapshot.json').read_text())
    from ..sim.doctor import ARENA_SHA, LAB_SHA
    if dependencies.get('arena_commit') != ARENA_SHA or dependencies.get('isaac_lab_commit') != LAB_SHA:
        raise ValueError('Unpinned dependencies')
    if dependencies.get('installation_method') == 'native_uv':
        if (not re.fullmatch('[0-9a-f]{64}', dependencies.get('uv_lock_sha256',''))
            or dependencies.get('packages',{}).get('isaacsim') != '6.1.0.0'
            or dependencies.get('packages',{}).get('isaaclab') != '17.0.2'):
            raise ValueError('Missing or invalid native runtime provenance')
        records_hashes=dependencies.get('package_record_sha256',{})
        for name in ('isaacsim','isaaclab','isaaclab-arena','torch'):
            if not re.fullmatch('[0-9a-f]{64}', records_hashes.get(name,'')):
                raise ValueError('Missing native package fingerprint: '+name)
    elif not re.fullmatch('sha256:[0-9a-f]{64}', dependencies.get('image_digest','')):
        raise ValueError('Missing image digest')
    paths = sorted(root.rglob('*results.jsonl'))
    if not paths:
        raise ValueError('No episode evidence')
    records = []
    for path in paths:
        for line in path.read_text().splitlines():
            r = EpisodeResult.model_validate_json(line)
            if r.backend != 'physx':
                raise ValueError('Physical reporting rejects fake records')
            if not r.infra_failure:
                if not r.trajectory_path or not r.trajectory_sha256:
                    raise ValueError('Missing physical trajectory')
                trace = (root/r.trajectory_path).resolve()
                if not trace.is_relative_to(root.resolve()) or file_digest(trace) != r.trajectory_sha256:
                    raise ValueError('Trajectory path/checksum invalid')
            records.append(r)
    if len({r.episode_id for r in records}) != len(records):
        raise ValueError('Duplicate episode IDs')
    costs = json.loads((root/'costs.json').read_text())
    if costs.get('physical_episode_executions') != len(records):
        raise ValueError('Incomplete execution ledger')
    for key in ('logical_episode_requests','aliased_episode_requests','budget_charged_episodes','sim_time_s','wall_time_s'):
        if key not in costs:
            raise ValueError('Missing cost field '+key)
    if abs(costs['sim_time_s']-sum(r.sim_time_s for r in records)) > 1e-6:
        raise ValueError('Simulation cost mismatch')
    # Formal matrices need paired cells, calibration and provenance audit beyond schema validity.
    return dict(status='EVIDENCE_SCHEMA_VALID', records=len(records), formal_result_eligible=False,
        reason='Full matrix and GPU evidence audit still required')
