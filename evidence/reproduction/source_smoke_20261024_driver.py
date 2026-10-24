import os,subprocess,sys,json,time
from pathlib import Path
root=Path('/code/rosclaw/physicalEvoBench_X');base=Path('/home/dell/pebx-reproduction/source-smoke-20261024')
base.mkdir(parents=True,exist_ok=False);checkout=base/'checkout'
commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()
subprocess.run(['git','clone','--no-hardlinks','--no-checkout',str(root),str(checkout)],check=True)
subprocess.run(['git','checkout','--detach',commit],cwd=checkout,check=True)
subprocess.run(['git','diff','--exit-code'],cwd=checkout,check=True)
# Shared pinned upstream checkout/runtime; this is not a fresh dependency install.
(checkout/'third_party/IsaacLab-Arena').rmdir()
(checkout/'third_party/IsaacLab-Arena').symlink_to(root/'third_party/IsaacLab-Arena',target_is_directory=True)
python=root/'third_party/IsaacLab-Arena/.venv/bin/python'
env=dict(os.environ,PYTHONPATH=str(checkout/'src'),CUDA_VISIBLE_DEVICES='2',HEADLESS='1',ACCEPT_EULA='Y',OMNI_KIT_ACCEPT_EULA='YES',ISAACLAB_ARENA_FORCE_EXIT_ON_COMPLETE='1',PYTHONUNBUFFERED='1')
origin=subprocess.check_output([str(python),'-c','import physicalevobench_x;print(physicalevobench_x.__file__)'],cwd=checkout,env=env,text=True).strip()
assert Path(origin).is_relative_to(checkout)
results=[]
for body in ('franka_panda','franka_robotiq'):
 output=base/body;start=time.monotonic()
 with (base/(body+'.log')).open('w') as log:
  code=subprocess.run([str(python),'-m','physicalevobench_x.cli','smoke','--embodiment',body,'--episodes','1','--seed','710024','--output',str(output)],cwd=checkout,env=env,stdout=log,stderr=subprocess.STDOUT).returncode
 result={'embodiment':body,'returncode':code,'process_wall_s':time.monotonic()-start}
 path=output/'episode_results.jsonl'
 if path.exists():
  rows=[json.loads(l) for l in path.read_text().splitlines()];result.update(episodes=len(rows),successes=sum(r['task_success'] for r in rows),infra_failures=sum(bool(r['infra_failure']) for r in rows))
 results.append(result)
 if code:break
report={'status':'SOURCE_SMOKE_PASSED' if len(results)==2 and all(r['returncode']==0 and r.get('successes')==1 and not r.get('infra_failures') for r in results) else 'SOURCE_SMOKE_FAILED','formal_result_eligible':False,'scope':'Clean project source; shared existing pinned upstream checkout, installed native runtime and cached assets. Not independent-machine reproduction or clean dependency installation.','project_commit':commit,'import_origin':origin,'gpu':2,'results':results,'output':str(base)}
(base/'review.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
