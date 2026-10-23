"""Bind NEW acceptance executions to exact frozen inputs without rewriting old evidence.

Invoked by a CPU supervisor around native children. No mock fallback is available.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import time
import yaml
from physicalevobench_x.core.hashing import file_digest, write_json


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--config',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--gpu',type=int,required=True)
    p.add_argument('--check',choices=['panda_nominal','robotiq_nominal','panda_calibration','robotiq_calibration',
        'panda_dynamics','robotiq_dynamics','panda_sensitivity','robotiq_sensitivity','panda_replay','robotiq_replay',
        'judge_adversarial'],required=True)
    a=p.parse_args()
    if os.environ.get('ACCEPT_EULA')!='Y':
        raise ValueError('Set ACCEPT_EULA=Y after accepting the NVIDIA Isaac Sim EULA')
    config=yaml.safe_load(a.config.read_text())
    if a.check.endswith('sensitivity'):
        body='franka_panda' if a.check.startswith('panda') else 'franka_robotiq'
        if Path(config['development_validation_evidence'][body]).exists():
            raise ValueError('Immutable development review already exists; choose a new evidence version')
    hashes={name:file_digest(name) for name in config['freeze_files']}
    if a.output.exists():
        raise ValueError('Refusing to overwrite an acceptance execution')
    a.output.mkdir(parents=True)
    write_json(a.output/'inputs.json',dict(frozen_inputs=hashes,check=a.check))
    python=Path('third_party/IsaacLab-Arena/.venv/bin/python').absolute()
    body='franka_panda' if a.check.startswith('panda') else 'franka_robotiq'
    run=a.output/'run'
    if a.check.endswith('nominal'):
        command=[str(python),'-m','physicalevobench_x.cli','smoke','--embodiment',body,'--episodes','10','--output',str(run)]
        report_name=None
    elif a.check.endswith(('calibration','dynamics')):
        kind='calibrate' if a.check.endswith('calibration') else 'dynamics-check'
        report_name='calibration.json' if kind=='calibrate' else 'dynamics.json'
        command=[str(python),'-m','physicalevobench_x.cli',kind,'--embodiment',body,'--output',str(run)]
    elif a.check.endswith('sensitivity'):
        report_name='range_check.json'
        command=[str(python),'scripts/check_common_range.py','--embodiment',body,'--output',str(run)]
    elif a.check.endswith('replay'):
        report_name='replay.json'
        command=[str(python),'scripts/check_paired_replay.py','--embodiment',body,'--output',str(run)]
    else:
        report_name='judge_adversarial.json'
        command=[str(python),'scripts/check_adversarial_judge.py','--output',str(run)]
    environment=dict(os.environ,CUDA_VISIBLE_DEVICES=str(a.gpu),HEADLESS='1',OMNI_KIT_ACCEPT_EULA='YES',
        ISAACLAB_ARENA_FORCE_EXIT_ON_COMPLETE='1',PYTHONUNBUFFERED='1')
    started=time.monotonic()
    with (a.output/'execution.log').open('w') as log:
        code=subprocess.run(command,env=environment,stdout=log,stderr=subprocess.STDOUT,check=False).returncode
    unchanged=all(file_digest(name)==checksum for name,checksum in hashes.items())
    passed=False
    if code==0 and unchanged:
        if report_name is None:
            records=[json.loads(line) for line in (run/'episode_results.jsonl').read_text().splitlines()]
            passed=len(records)==10 and all(r['backend']=='physx' and r['task_success'] and not r['infra_failure'] for r in records)
        else:
            report=json.loads((run/report_name).read_text())
            if a.check.endswith('sensitivity'):
                from analyze_common_range import analyze
                reviewed=analyze(run)
                write_json(config['development_validation_evidence'][body],reviewed)
                # Consumption, not guaranteed success. Each dimension must produce distinct observed motion/timing.
                by_field={}
                for m in reviewed['measurements']:
                    if not m['case_id'].startswith('combined/'):
                        by_field.setdefault(m['case_id'].split('/')[0],[]).append(m)
                passed=(report.get('backend')=='physx' and len(by_field)==5
                    and all(len(v)==3 for v in by_field.values()) and len(reviewed['measurements'])==23
                    and reviewed['all_measured_cases_mechanically_executable']
                    and reviewed['all_measured_lift_reference_speeds_bounded'])
                for field, measures in by_field.items():
                    signatures=[(round(m['minimum_actual_tcp_z_m'],5),
                                 tuple(sorted((k,round(v,3)) for k,v in m['stage_times'].items()))) for m in measures]
                    passed=passed and len(set(signatures))>=2
            else:
                passed=report.get('backend')=='physx' and report.get('status')=='GPU_VERIFIED'
    all_files={str(path):file_digest(path) for path in a.output.rglob('*') if path.is_file()}
    write_json(a.output/'attestation.json',dict(backend='physx',status='GPU_VERIFIED' if passed else 'GPU_CHECK_FAILED',
        check=a.check,returncode=code,inputs_unchanged=unchanged,frozen_inputs=hashes,
        selected_gpu=a.gpu,child_process_wall_time_s=time.monotonic()-started,
        gpu_time_scope='Selected GPU allocation envelope; shared utilization, not exclusive compute time',
        evidence_files=all_files,formal_result_eligible=False))
    return 0 if passed else 2


if __name__=='__main__':
    raise SystemExit(main())
