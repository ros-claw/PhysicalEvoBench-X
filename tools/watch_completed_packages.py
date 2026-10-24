"""Audit newly completed packages without touching the frozen pilot worker."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--suite', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    suite = args.suite.resolve()
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output/'owner.json').write_text(json.dumps(dict(pid=os.getpid(), suite=str(suite))))
    previous = None
    while True:
        completed = sorted(str(p.parent.relative_to(suite)) for p in
                           suite.glob('packages/*/*/*/summary.json'))
        if completed != previous:
            target = args.output/f'completed-{len(completed):02d}-{time.time_ns()}.json'
            with target.with_suffix('.log').open('w') as log:
                code = subprocess.run([sys.executable, str(Path(__file__).with_name('check_completed_packages.py')),
                                       '--suite', str(suite), '--output', str(target)],
                                      stdout=log, stderr=subprocess.STDOUT, check=False).returncode
            if code:
                return code
            previous = completed
        status_path = suite/'supervisor_status.json'
        if status_path.exists():
            status = json.loads(status_path.read_text())
            if not status['active'] and status['status'] in ('COMPLETE', 'FAILED'):
                (args.output/'stopped.json').write_text(json.dumps(dict(
                    supervisor_status=status['status'], checked_packages=len(completed),
                    formal_result_eligible=False, note='Full audit is owned by the main pipeline.')))
                return 0 if status['status'] == 'COMPLETE' else 2
        time.sleep(30)


if __name__ == '__main__':
    raise SystemExit(main())
