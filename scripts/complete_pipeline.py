"""Run version-bound GPU acceptance, freeze, then the complete internal pilot.

Any failed acceptance stops formal launch. Existing evidence is never overwritten.
No parameter tuning or selection of donor runs is performed by this supervisor.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import yaml
from physicalevobench_x.core.hashing import file_digest, write_json
from pilot_support import atomic_json

CHECK_JOBS={
    'franka_panda_nominal':['panda_nominal'], 'franka_robotiq_nominal':['robotiq_nominal'],
    'tcp_axes':['panda_calibration','robotiq_calibration'],
    'gripper_motion':['panda_calibration','robotiq_calibration'],
    'mass_readback':['panda_dynamics','robotiq_dynamics'],
    'mass_impulse':['panda_dynamics','robotiq_dynamics'],
    'reset_isolation':['panda_dynamics','robotiq_dynamics'],
    'judge_adversarial':['judge_adversarial'],
    'parameter_sensitivity':['panda_sensitivity','robotiq_sensitivity'],
    'paired_replay':['panda_replay','robotiq_replay'],
}


def aggregate(config, acceptance):
    cfg=yaml.safe_load(config.read_text())
    hashes={name:file_digest(name) for name in cfg['freeze_files']}
    for check,jobs in CHECK_JOBS.items():
        files={}
        for job in jobs:
            path=acceptance/job/'attestation.json'
            data=json.loads(path.read_text())
            if data['status']!='GPU_VERIFIED' or data['backend']!='physx' or data['frozen_inputs']!=hashes:
                raise ValueError('Acceptance missing/failed/stale: '+job)
            files[str(path)]=file_digest(path)
            for path,checksum in data['evidence_files'].items():
                if file_digest(path)!=checksum:
                    raise ValueError('Raw acceptance evidence changed')
                files[path]=checksum
        target=Path(cfg['gpu_evidence'][check])
        if target.exists():
            raise ValueError('Immutable acceptance output already exists: '+str(target))
        bodies=['franka_panda'] if check=='franka_panda_nominal' else ['franka_robotiq'] if check=='franka_robotiq_nominal' else ['franka_panda','franka_robotiq']
        write_json(target,dict(backend='physx',status='GPU_VERIFIED',check=check,covered_embodiments=bodies,
            frozen_inputs=hashes,evidence_files=files,formal_result_eligible=False))


def run(args):
    output=args.output.resolve()
    output.mkdir(parents=True,exist_ok=False)
    write_json(output/'pipeline_owner.json',dict(pid=os.getpid()))
    logs=output/'logs'
    logs.mkdir()
    status=output/'pipeline_status.json'
    def update(phase,**extra):
        atomic_json(status,dict(phase=phase,updated_unix_s=time.time(),**{'formal_result_eligible':False,**extra}))
    if os.environ.get('ACCEPT_EULA')!='Y':
        raise ValueError('Set ACCEPT_EULA=Y after accepting NVIDIA Isaac Sim EULA')
    update('GPU_ACCEPTANCE_RUNNING')
    jobs=list(dict.fromkeys(job for values in CHECK_JOBS.values() for job in values))
    pending=jobs.copy()
    active,finished,failed={},[],[]
    while pending or active:
        if not failed:
            for gpu in args.gpus:
                if gpu in active or not pending:
                    continue
                job=pending.pop(0)
                stream=(logs/(job+'.log')).open('w')
                process=subprocess.Popen([sys.executable,'scripts/attest_acceptance.py','--config',str(args.config),
                    '--output',str(output/'acceptance'/job),'--gpu',str(gpu),'--check',job],
                    stdout=stream,stderr=subprocess.STDOUT)
                active[gpu]=(job,process,stream)
        for gpu,(job,process,stream) in list(active.items()):
            code=process.poll()
            if code is None:
                continue
            stream.close()
            (finished if code==0 else failed).append(dict(job=job,returncode=code))
            del active[gpu]
        update('GPU_ACCEPTANCE_FAILED' if failed else 'GPU_ACCEPTANCE_RUNNING',completed=finished,failed=failed,
               active=[dict(gpu=g,job=j,pid=p.pid) for g,(j,p,_) in active.items()],pending=pending)
        if failed and not active:
            return 2
        if pending or active:
            time.sleep(1)
    aggregate(args.config,output/'acceptance')
    update('ENGINEERING_TRANSFER_SMOKE_RUNNING')
    from pilot_suite import plan
    smoke=output/'engineering_smoke'
    plan(smoke,Path.cwd(),seeds=1,test_count=10,learners=('random_search_v1',),sources=('franka_panda',))
    with (logs/'engineering_smoke.log').open('w') as log:
        code=subprocess.run([sys.executable,'scripts/run_suite.py','--suite',str(smoke),'--gpus',str(args.gpus[0])],
            stdout=log,stderr=subprocess.STDOUT,check=False).returncode
    if code:
        update('ENGINEERING_SMOKE_FAILED',returncode=code)
        return 2
    update('THROUGHPUT_MEASUREMENT_RUNNING')
    throughput=[]
    native=Path('third_party/IsaacLab-Arena/.venv/bin/python').absolute()
    for index,body in enumerate(('franka_panda','franka_robotiq')):
        environment=dict(os.environ,CUDA_VISIBLE_DEVICES=str(args.gpus[index%len(args.gpus)]),
            HEADLESS='1',OMNI_KIT_ACCEPT_EULA='YES',ISAACLAB_ARENA_FORCE_EXIT_ON_COMPLETE='1',PYTHONUNBUFFERED='1')
        stream=(logs/(body+'_throughput.log')).open('w')
        process=subprocess.Popen([str(native),'scripts/measure_throughput.py','--embodiment',body,
            '--output',str(output/'throughput'/body)],env=environment,stdout=stream,stderr=subprocess.STDOUT)
        throughput.append((body,process,stream))
        if len(args.gpus)==1:
            code=process.wait()
            stream.close()
            if code:
                update('THROUGHPUT_FAILED',embodiment=body,returncode=code)
                return 2
    failed_throughput=[]
    for body,process,stream in throughput:
        code=process.wait()
        stream.close()
        if code:
            failed_throughput.append(dict(embodiment=body,returncode=code))
    if failed_throughput:
        update('THROUGHPUT_FAILED',failed=failed_throughput)
        return 2
    profiles=[json.loads((output/'throughput'/body/'throughput.json').read_text()) for body,_,_ in throughput]
    typical=sum(profile['episode_wall']['median_s'] for profile in profiles)/2
    write_json(output/'pilot_timing_estimate.json',dict(measured_profiles=profiles,
        estimated_hours_all_source_rollbacks=2940*typical/(3600*len(args.gpus)),
        estimated_hours_without_aliases=5640*typical/(3600*len(args.gpus)),
        excluded='Additional app startups, model latency, infrastructure failures and changes in shared GPU load'))
    from physicalevobench_x.core.freeze import freeze
    frozen=output/'freeze.json'
    freeze(args.config,Path.cwd(),frozen)
    update('FROZEN_PILOT_RUNNING',freeze_path=str(frozen))
    suite=output/'pilot'
    plan(suite,Path.cwd(),frozen)
    with (logs/'pilot_supervisor.log').open('w') as log:
        code=subprocess.run([sys.executable,'scripts/run_suite.py','--suite',str(suite),'--gpus',
            *(str(g) for g in args.gpus)],stdout=log,stderr=subprocess.STDOUT,check=False).returncode
    if code:
        update('PILOT_INCOMPLETE',returncode=code)
        return 2
    from audit_suite import audit
    report=audit(suite,Path.cwd())
    write_json(suite/'independent_audit.json',report)
    from summarize_pilot import summarize
    summarize(suite,verified_audit=True)
    subprocess.run([str(native),'scripts/plot_report.py','--suite',str(suite)],check=True)
    update('FROZEN_INTERNAL_PILOT_AUDITED',audit_path=str(suite/'independent_audit.json'),
           pilot_path=str(suite),release_review_pending=True,formal_result_eligible=report['formal_result_eligible'])
    return 0


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--config',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--gpus',type=int,nargs='+',default=[0,1])
    args=parser.parse_args()
    if len(set(args.gpus))!=len(args.gpus) or not args.gpus or any(g<0 for g in args.gpus):
        raise ValueError('Distinct nonnegative GPU indices required')
    try:
        raise SystemExit(run(args))
    except Exception as exc:
        owner=args.output/'pipeline_owner.json'
        if owner.exists() and json.loads(owner.read_text()).get('pid')==os.getpid():
            atomic_json(args.output/'pipeline_status.json',dict(phase='STOPPED_WITH_ERROR',
                error=type(exc).__name__,message=str(exc),formal_result_eligible=False))
        raise
