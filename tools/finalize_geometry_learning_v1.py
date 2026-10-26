"""Finalize the fixed 72-call development study once, with no hidden retries."""
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
        if state.exists():raise ValueError('Existing finalization attempt retained')
        write_json(state,dict(status='WAITING_FOR_WORKERS',pid=os.getpid(),formal_result_eligible=False))
        while True:
            status=json.loads((study/'supervisor.json').read_text())
            if status['status']!='RUNNING':break
            try:os.kill(status['pid'],0)
            except ProcessLookupError:raise RuntimeError('Supervisor disappeared without completion')
            time.sleep(.5)
        if status['status']!='DEVELOPMENT_LEARNING_EXECUTION_COMPLETE' or any(w['returncode']!=0 for w in status['workers']):
            raise RuntimeError('Learning execution incomplete; no audit success claim')
        for name,python,args in [
            ('trace_audit',sys.executable,['tools/audit_geometry_learning_v1.py','--study',str(study),'--output',str(study/'trace_audit.json'),'--replay-root',str(study/'audit_replay')]),
            ('report',str(native_python),['tools/report_geometry_learning_v1.py','--study',str(study),'--archive',str(archive)])]:
            write_json(state,dict(status='RUNNING_'+name.upper(),formal_result_eligible=False))
            with (study/(name+'.log')).open('x') as log:
                result=subprocess.run([python,*args],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
            if result.returncode:raise RuntimeError(name+' failed; output and attempt retained, no automatic retry')
        write_json(state,dict(status='ARCHIVED_AWAITING_FIGURE_REVIEW',formal_result_eligible=False,
            archive=str(archive),finalizer_sha256=file_digest(__file__)))


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--study',type=Path,required=True)
    ap.add_argument('--archive',type=Path,required=True);ap.add_argument('--native-python',type=Path,required=True);a=ap.parse_args()
    try:finalize(a.study.resolve(),a.archive.resolve(),a.native_python.absolute())
    except Exception as exc:
        path=a.study/'finalization_error.json'
        if not path.exists():write_json(path,dict(status='STOPPED_WITH_ERROR',formal_result_eligible=False,error=str(exc)))
        raise
