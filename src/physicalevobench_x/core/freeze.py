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
    if not cfg.get('development_validated'):
        raise ValueError('Task distribution/bounds have not passed development validation')
    lock = yaml.safe_load((root/'dependencies.lock.yaml').read_text())
    if not re.fullmatch(r'sha256:[0-9a-f]{64}', lock['isaac_sim'].get('image_digest') or ''):
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
    if Path(output).exists():
        raise ValueError('Freeze output already exists; immutable version required')
    snapshot = dict(protocol='pebx_x_v0.1', files=hashes, dependency_lock_hash=file_digest(root/'dependencies.lock.yaml'),
                    config=cfg, gpu_evidence={k:file_digest(root/v) for k,v in evidence.items()})
    snapshot['freeze_hash'] = digest(snapshot)
    write_json(output, snapshot)
    return snapshot
