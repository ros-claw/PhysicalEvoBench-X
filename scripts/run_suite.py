"""Supervise planned native GPU workers without shell interpolation or silent retry."""
import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from pilot_support import atomic_json


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--suite',type=Path,required=True)
    p.add_argument('--gpus',type=int,nargs='+',default=[0,1])
    p.add_argument('--python',type=Path,default=Path('third_party/IsaacLab-Arena/.venv/bin/python'))
    args = p.parse_args()
    if len(set(args.gpus))!=len(args.gpus) or any(g<0 for g in args.gpus):
        raise ValueError('Expected distinct nonnegative GPU indices')
    if os.environ.get('ACCEPT_EULA')!='Y':
        raise ValueError('Set ACCEPT_EULA=Y after accepting the NVIDIA Isaac Sim EULA')
    suite = args.suite.resolve()
    plan = json.loads((suite/'plan.json').read_text())
    pending = [p['package_id'] for p in plan['packages'] if not (suite/'packages'/p['package_id']/'summary.json').exists()]
    active, finished, failures = {}, [], []
    logdir = suite/'worker_logs'
    logdir.mkdir(exist_ok=True)
    started = time.time()
    while pending or active:
        if not failures:
            for gpu in args.gpus:
                if gpu in active or not pending:
                    continue
                package = pending.pop(0)
                logfile = logdir/(package.replace('/','__')+f'__{time.time_ns()}.log')
                stream = logfile.open('w')
                environment = dict(os.environ,CUDA_VISIBLE_DEVICES=str(gpu),HEADLESS='1',
                    OMNI_KIT_ACCEPT_EULA='YES',ISAACLAB_ARENA_FORCE_EXIT_ON_COMPLETE='1',PYTHONUNBUFFERED='1')
                process = subprocess.Popen([str(args.python.absolute()),'scripts/pilot_suite.py','worker',
                    '--suite',str(suite),'--package',package],stdout=stream,stderr=subprocess.STDOUT,env=environment)
                active[gpu] = dict(process=process,package=package,stream=stream,log=str(logfile))
        for gpu, item in list(active.items()):
            code = item['process'].poll()
            if code is None:
                continue
            item['stream'].close()
            entry = dict(package=item['package'],returncode=code,log=item['log'],gpu=gpu)
            if code==0 and (suite/'packages'/item['package']/'summary.json').is_file():
                finished.append(entry)
            else:
                failures.append(entry)
            print(json.dumps(entry),flush=True)
            del active[gpu]
        atomic_json(suite/'supervisor_status.json',dict(started_unix_s=started,
            active=[dict(package=i['package'],pid=i['process'].pid,gpu=gpu,log=i['log']) for gpu,i in active.items()],
            completed_this_invocation=finished,failed=failures,pending=pending,
            status='FAILED' if failures else 'RUNNING' if pending or active else 'COMPLETE'))
        if failures and not active:
            break
        if pending or active:
            time.sleep(1)
    result = subprocess.run([sys.executable,'scripts/summarize_pilot.py','--suite',str(suite)],check=False)
    return 2 if failures or result.returncode else 0


if __name__=='__main__':
    raise SystemExit(main())
