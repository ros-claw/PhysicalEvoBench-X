"""Read-only development freeze gap inventory; never changes acceptance flags."""
import argparse
import json
from pathlib import Path
import yaml
from physicalevobench_x.core.hashing import file_digest, write_json
from physicalevobench_x.core.freeze import REQUIRED_CHECKS


def inspect(root, config):
    cfg = yaml.safe_load(config.read_text())
    lock = yaml.safe_load((root/'dependencies.lock.yaml').read_text())
    gaps, evidence = [], {}
    reviewed=bool(cfg.get('development_validated'))
    if cfg.get('development_validation_mode')=='evidence_gate':
        paths=cfg.get('development_validation_evidence',{})
        reviewed=len(paths)==2 and all((root/name).is_file() and
            json.loads((root/name).read_text()).get('all_measured_cases_mechanically_executable') for name in paths.values())
    if not reviewed:
        gaps.append('Task distribution / parameter bounds not development-validated')
    if not lock.get('native',{}).get('dependency_metadata_reviewed'):
        gaps.append('Dependency review not yet adopted into lock')
    if not lock.get('assets',{}).get('verified'):
        gaps.append('Asset inventory not yet adopted into lock')
    files = cfg.get('freeze_files', [])
    if not files:
        gaps.append('No explicit frozen file set')
    hashes = {name:file_digest(root/name) for name in files if (root/name).is_file()}
    for check in REQUIRED_CHECKS:
        path = root/cfg.get('gpu_evidence',{}).get(check,'__missing__')
        if not path.is_file():
            state = 'MISSING'
        else:
            data = json.loads(path.read_text())
            state = 'VERIFIED' if (data.get('backend')=='physx' and data.get('status')=='GPU_VERIFIED'
                and hashes and data.get('frozen_inputs')==hashes) else 'UNVERIFIED_OR_STALE'
        evidence[check]=state
        if state!='VERIFIED':
            gaps.append(check+': '+state)
    return dict(status='READY_FOR_FREEZE_ATTEMPT' if not gaps else 'NOT_READY',gaps=gaps,
        checks=evidence,formal_result_eligible=False)


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--root',type=Path,default=Path.cwd())
    p.add_argument('--config',type=Path,default=Path('configs/tasks/stable_lift_dev.yaml'))
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    report=inspect(a.root,a.config)
    write_json(a.output,report)
    print(json.dumps(report))
