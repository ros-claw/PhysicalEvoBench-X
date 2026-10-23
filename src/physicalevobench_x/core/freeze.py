"""Fail-closed evidence gate. Development defaults are never silently formalized."""
from pathlib import Path
import json
import re
from .hashing import file_digest, write_json, digest

REQUIRED_CHECKS = ('franka_panda_nominal', 'franka_robotiq_nominal', 'tcp_axes',
                   'gripper_motion', 'mass_readback', 'mass_impulse', 'reset_isolation',
                   'judge_adversarial', 'parameter_sensitivity', 'paired_replay')


def freeze(config, root, output):
    import yaml
    root = Path(root)
    cfg = yaml.safe_load(Path(config).read_text())
    if not cfg.get('development_validated') and cfg.get('development_validation_mode')!='evidence_gate':
        raise ValueError('Task distribution/bounds have not passed development validation')
    from .schemas import BOUNDS
    if cfg.get('parameter_bounds')!={k:list(v) for k,v in BOUNDS.items()}:
        raise ValueError('Frozen task bounds do not match the executable schema')
    development=cfg.get('development_validation_evidence',{})
    if set(development)!={'franka_panda','franka_robotiq'}:
        raise ValueError('Both embodiment range reviews are required')
    for body,name in development.items():
        reviewed=json.loads((root/name).read_text())
        if (reviewed.get('backend')!='physx' or reviewed.get('embodiment')!=body
            or not reviewed.get('all_measured_cases_mechanically_executable')
            or not reviewed.get('all_measured_lift_reference_speeds_bounded')
            or len(reviewed.get('measurements',[]))!=23):
            raise ValueError('Development range review incomplete: '+body)
        run=Path(reviewed['source_run'])
        if file_digest(run/'plan.json')!=reviewed['plan_sha256']:
            raise ValueError('Development range plan changed')
        for measured in reviewed['measurements']:
            for suffix,key in [('_trace.jsonl','trace_sha256'),('.json','metadata_sha256')]:
                if file_digest(run/'trajectories'/(measured['episode_id']+suffix))!=measured[key]:
                    raise ValueError('Development range evidence changed')
    lock = yaml.safe_load((root/'dependencies.lock.yaml').read_text())
    assets=lock.get('assets',{})
    if not assets.get('verified'):
        raise ValueError('Asset dependencies have not been verified')
    inventory_path=root/assets['inventory_path']
    if file_digest(inventory_path)!=assets['inventory_sha256']:
        raise ValueError('Asset inventory hash mismatch')
    inventory=json.loads(inventory_path.read_text())
    if not inventory.get('verified') or inventory.get('unresolved') or not inventory.get('files'):
        raise ValueError('Incomplete asset dependency inventory')
    for name,record in inventory['files'].items():
        path=Path(name) if Path(name).is_absolute() else root/name
        if file_digest(path)!=record['sha256']:
            raise ValueError('Asset content changed: '+name)
    if lock.get('installation_method') == 'native_uv':
        native = lock.get('native', {})
        if not native.get('dependency_metadata_reviewed',False):
            raise ValueError('Native dependency metadata exceptions require review before freeze')
        review_path=root/native['dependency_review_path']
        if file_digest(review_path)!=native['dependency_review_sha256']:
            raise ValueError('Dependency exception review changed')
        review=json.loads(review_path.read_text())
        if (review.get('status')!='REVIEWED_WITH_SCOPED_EXCEPTIONS' or review.get('profile')!='state_ik_physx_only'
            or review.get('uv_lock_sha256')!=native['uv_lock_sha256']
            or review.get('documentation_sha256')!=file_digest(root/'docs/dependency_review.md')):
            raise ValueError('Unreviewed native dependency profile')
        for path_key, hash_key in [('uv_lock_path','uv_lock_sha256'),('runtime_snapshot_path','runtime_snapshot_sha256')]:
            expected = native.get(hash_key, '')
            if not re.fullmatch('[0-9a-f]{64}', expected) or file_digest(root/native[path_key]) != expected:
                raise ValueError('Native runtime provenance mismatch')
        runtime = json.loads((root/native['runtime_snapshot_path']).read_text())
        from ..sim.doctor import ARENA_SHA, LAB_SHA
        if (runtime.get('arena_commit') != ARENA_SHA or runtime.get('isaac_lab_commit') != LAB_SHA
            or runtime.get('uv_lock_sha256') != native['uv_lock_sha256']
            or runtime.get('packages',{}).get('isaacsim') != '6.1.0.0'):
            raise ValueError('Unverified native simulation version')
    elif not re.fullmatch(r'sha256:[0-9a-f]{64}', lock['isaac_sim'].get('image_digest') or ''):
        raise ValueError('Missing locally pulled image digest')
    files = cfg.get('freeze_files', [])
    if not files:
        raise ValueError('No freeze file set')
    hashes = {name: file_digest(root/name) for name in files}
    evidence = cfg.get('gpu_evidence', {})
    for check in REQUIRED_CHECKS:
        path = root/evidence.get(check, '__missing__')
        data = json.loads(path.read_text())
        if data.get('backend') != 'physx' or data.get('status') != 'GPU_VERIFIED':
            raise ValueError('GPU evidence missing: '+check)
        if data.get('frozen_inputs') != hashes:
            raise ValueError('Stale or mismatched GPU evidence: '+check)
        expected_bodies=({'franka_panda'} if check=='franka_panda_nominal' else
            {'franka_robotiq'} if check=='franka_robotiq_nominal' else {'franka_panda','franka_robotiq'})
        if set(data.get('covered_embodiments',[]))!=expected_bodies:
            raise ValueError('GPU check has incomplete embodiment coverage: '+check)
        if not data.get('evidence_files'):
            raise ValueError('Missing raw GPU evidence chain: '+check)
        for name,checksum in data['evidence_files'].items():
            if file_digest(root/name)!=checksum:
                raise ValueError('GPU raw evidence changed: '+check)
    if Path(output).exists():
        raise ValueError('Freeze output already exists; immutable version required')
    snapshot = dict(protocol='pebx_x_v0.1', files=hashes, dependency_lock_hash=file_digest(root/'dependencies.lock.yaml'),
                    config={**cfg,'development_validated':True,'validation_result_source':'verified_gpu_evidence'},
                    gpu_evidence={k:file_digest(root/v) for k,v in evidence.items()},
                    development_reviews={body:file_digest(root/path) for body,path in development.items()})
    snapshot['freeze_hash'] = digest(snapshot)
    write_json(output, snapshot)
    return snapshot
