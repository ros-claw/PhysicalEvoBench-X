"""Wait for the declared study, then audit and archive once; preserve failed attempts."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from physicalevobench_x.core.hashing import write_json,file_digest

ROOT=Path(__file__).resolve().parents[1]


def finalize(study,archive,native_python):
    import fcntl
    with (study/'finalizer.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        state=study/'finalization_status.json'
        if state.exists():raise ValueError('Previous finalization retained; reconcile before another attempt')
        write_json(state,dict(status='WAITING_FOR_WORKERS',formal_result_eligible=False,pid=os.getpid()))
        while True:
            status=json.loads((study/'supervisor.json').read_text())
            if status['status']!='RUNNING':break
            try:os.kill(status['pid'],0)
            except ProcessLookupError:raise RuntimeError('Supervisor stopped without a terminal record')
            time.sleep(.5)
        if status['status']!='CALIBRATION_EXECUTION_COMPLETE':raise RuntimeError('Physical execution incomplete; no audit success claim')
        if any(w['returncode']!=0 for w in status['workers']):raise RuntimeError('Worker nonzero exit retained')
        for name,python,args in [
            ('trace_audit',Path(sys.executable),['tools/audit_distribution_v1.py','--study',str(study),'--output',str(study/'trace_audit.json')]),
            ('report',native_python,['tools/report_distribution_v1.py','--study',str(study),'--archive',str(archive)])]:
            write_json(state,dict(status='RUNNING_'+name.upper(),formal_result_eligible=False))
            with (study/(name+'.log')).open('x') as log:
                result=subprocess.run([str(python),*args],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
            if result.returncode:raise RuntimeError(name+' failed; attempt/log retained; no automatic retry')
        write_json(state,dict(status='ARCHIVED_AWAITING_VISUAL_REVIEW',formal_result_eligible=False,
            archive=str(archive),finalizer_sha256=file_digest(__file__)))


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--study',type=Path,required=True)
    ap.add_argument('--archive',type=Path,required=True);ap.add_argument('--native-python',type=Path,required=True)
    a=ap.parse_args()
    try:finalize(a.study.resolve(),a.archive.resolve(),a.native_python.absolute())
    except Exception as exc:
        path=a.study/'finalization_error.json'
        if not path.exists():write_json(path,dict(status='STOPPED_WITH_ERROR',error=str(exc),formal_result_eligible=False))
        raise
