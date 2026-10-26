"""Fresh native dependency installation from pinned public source; warm caches explicit."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from physicalevobench_x.core.hashing import digest,file_digest,write_json

ROOT=Path(__file__).resolve().parents[1]
PROJECT_COMMIT='66a093e23009cec34d23e57e1d1f5be51e8718db'
ARENA_COMMIT='c7edf3a9d5d8276565208f72422f8f8a0806d6cf'
LAB_COMMIT='91a0906f93802eb859192dcb0bca879f891e92d6'


def plan(directory,cache,gpu):
    if directory.exists():raise ValueError('Fresh reproduction directory required')
    if not cache.is_dir():raise ValueError('Explicit existing download cache required')
    inventory=ROOT/'evidence/native/asset_inventory_complete.json'
    d=dict(study='fresh_native_installation_v1',formal_result_eligible=False,project_commit=PROJECT_COMMIT,
        arena_commit=ARENA_COMMIT,lab_commit=LAB_COMMIT,python='3.12.13',gpu=gpu,
        repository='https://github.com/ros-claw/PhysicalEvoBench-X.git',
        shared_download_cache=str(cache),uv_link_mode='hardlink',
        asset_inventory=str(inventory),asset_inventory_sha256=file_digest(inventory),
        tool_sha256=file_digest(__file__),
        scope='New public-source checkout and freshly installed virtual environment; shared cached packages/assets and same host/GPU, not a cold-network or independent-machine reproduction',
        native_calls_planned=2,nominal_episodes_per_body=1,
        dependency_review='Compare the seven retained metadata incompatibilities; changed exceptions fail review before simulation',
        optional_submodules='Initialize Arena plus IsaacLab and Isaac-GR00T only; unused GR00T optional task submodules remain uninitialized as in the original installation')
    d['plan_hash']=digest(d);directory.mkdir(parents=True);write_json(directory/'plan.json',d);return d


def verify(directory):
    d=json.loads((directory/'plan.json').read_text())
    if d['plan_hash']!=digest({k:v for k,v in d.items() if k!='plan_hash'}) or d['tool_sha256']!=file_digest(__file__):
        raise ValueError('Reproduction plan/tool changed')
    if file_digest(d['asset_inventory'])!=d['asset_inventory_sha256']:raise ValueError('Asset inventory changed')
    return d


def assets(d):
    inventory=json.loads(Path(d['asset_inventory']).read_text())['files']
    for path,record in inventory.items():
        if file_digest(path)!=record['sha256']:raise ValueError('Shared asset differs from locked inventory: '+path)
    return len(inventory)


def incompatible_lines(text):
    return sorted(line.strip() for line in text.splitlines() if line.startswith('The package `'))


def run(directory):
    d=verify(directory)
    if os.environ.get('ACCEPT_EULA')!='Y':raise ValueError('Accepted EULA required')
    if (directory/'status.json').exists():raise ValueError('Existing attempt retained; reconcile explicitly instead of automatic restart')
    project=directory/'project';arena=project/'third_party/IsaacLab-Arena';native=arena/'.venv/bin/python'
    if project.exists():raise ValueError('Project/venv must be absent before installation')
    env={k:v for k,v in os.environ.items() if k not in ('PYTHONPATH','PYTHONHOME','VIRTUAL_ENV')}
    env.update(GIT_LFS_SKIP_SMUDGE='1',GIT_TERMINAL_PROMPT='0',UV_CACHE_DIR=d['shared_download_cache'],UV_LINK_MODE='hardlink',
        ACCEPT_EULA='Y',OMNI_KIT_ACCEPT_EULA='YES',HEADLESS='1',CUDA_VISIBLE_DEVICES=str(d['gpu']),
        ISAACLAB_ARENA_FORCE_EXIT_ON_COMPLETE='1',PYTHONUNBUFFERED='1')
    records=[];started=time.monotonic();native_started=[]
    def command(name,args,cwd,allowed=(0,)):
        verify(directory);record=dict(stage=name,command=list(map(str,args)),cwd=str(cwd),status='STARTED')
        records.append(record);write_json(directory/'status.json',dict(status='RUNNING',stages=records,formal_result_eligible=False))
        tick=time.monotonic()
        with (directory/(name+'.log')).open('x') as stream:
            result=subprocess.run(record['command'],cwd=cwd,env=env,stdout=stream,stderr=subprocess.STDOUT)
        record.update(status='COMPLETE' if result.returncode in allowed else 'FAILED',returncode=result.returncode,
            wall_time_s=time.monotonic()-tick,log_sha256=file_digest(directory/(name+'.log')))
        write_json(directory/'status.json',dict(status='RUNNING',stages=records,formal_result_eligible=False))
        if result.returncode not in allowed:raise RuntimeError(name+' failed with exit '+str(result.returncode))
    try:
        before=assets(d)
        command('clone',['git','clone','--no-checkout','--branch','implementation/v0.1',d['repository'],project],directory)
        command('checkout',['git','checkout','--detach',d['project_commit']],project)
        command('arena_source',['git','submodule','update','--init','third_party/IsaacLab-Arena'],project)
        command('lab_transport',['git','config','submodule.submodules/IsaacLab.url','https://github.com/isaac-sim/IsaacLab.git'],arena)
        command('gr00t_transport',['git','config','submodule.submodules/Isaac-GR00T.url','https://github.com/NVIDIA/Isaac-GR00T.git'],arena)
        command('upstream_source',['git','submodule','update','--init','submodules/IsaacLab','submodules/Isaac-GR00T'],arena)
        for path,expected in [(project,d['project_commit']),(arena,d['arena_commit']),(arena/'submodules/IsaacLab',d['lab_commit'])]:
            if subprocess.check_output(['git','rev-parse','HEAD'],cwd=path,text=True).strip()!=expected:raise ValueError('Source SHA mismatch')
        original_lock=ROOT/'dependencies.lock.yaml'
        import yaml
        lock=yaml.safe_load(original_lock.read_text())
        if file_digest(arena/'uv.lock')!=lock['native']['uv_lock_sha256']:raise ValueError('Fresh source dependency lock mismatch')
        if (arena/'.venv').exists():raise ValueError('Dependency environment already exists')
        command('uv_sync',['uv','sync','--locked','--extra','dev','--python',d['python'],'--project',arena],project)
        command('install_project',['uv','pip','install','--python',native,'--no-deps','-e',project],project)
        (project/'runs').mkdir(exist_ok=True)
        command('cpu_tests',[native,'-m','pytest','-q','-p','no:cacheprovider','--basetemp',directory/'pytest-native'],project)
        command('metadata_check',['uv','pip','check','--python',native],project,allowed=(0,1))
        expected=incompatible_lines((ROOT/'evidence/native/package_check.log').read_text())
        observed=incompatible_lines((directory/'metadata_check.log').read_text())
        if len(expected)!=7 or expected!=observed:raise ValueError('Dependency exceptions differ; do not inherit the original review')
        code="""import sys,json,importlib.util,importlib.metadata as m
from pathlib import Path
from urllib.parse import urlparse,unquote
names=['physicalevobench_x','isaaclab_arena','isaaclab']
paths={name:str(Path(importlib.util.find_spec(name).origin).resolve()) for name in names}
versions={name:m.version(name) for name in ['physicalevobench-x','isaaclab-arena','isaaclab','isaacsim','torch','numpy','pydantic']}
installed=[];editable={}
for dist in m.distributions():
    installed.append(dict(name=dist.metadata['Name'],version=dist.version,metadata_root=str(Path(dist.locate_file('')).resolve())))
    direct=dist.read_text('direct_url.json')
    if direct:
        info=json.loads(direct)
        if info.get('dir_info',{}).get('editable'):
            editable[dist.metadata['Name']]=str(Path(unquote(urlparse(info['url']).path)).resolve())
print(json.dumps(dict(executable=sys.executable,prefix=sys.prefix,python=sys.version.split()[0],packages=versions,import_paths=paths,editable_source_roots=editable,installed_distributions=installed)))
"""
        command('import_provenance',[native,'-c',code],project)
        provenance=json.loads((directory/'import_provenance.log').read_text())
        if provenance['python']!=d['python'] or not Path(provenance['prefix']).is_relative_to(project):raise ValueError('Fresh interpreter provenance mismatch')
        if any(not Path(path).is_relative_to(project) for path in provenance['import_paths'].values()):raise ValueError('Source import escaped fresh checkout')
        if any(not Path(path).is_relative_to(project) for path in provenance['editable_source_roots'].values()):raise ValueError('Editable source escaped fresh checkout')
        if any(not Path(row['metadata_root']).is_relative_to(project) for row in provenance['installed_distributions']):raise ValueError('Distribution metadata escaped fresh environment')
        expected_versions=json.loads((ROOT/'evidence/native/runtime_snapshot.json').read_text())['packages']
        if provenance['packages']!=expected_versions:raise ValueError('Fresh installed runtime versions changed')
        for body in ('franka_panda','franka_robotiq'):
            native_started.append(body)
            command(body+'_smoke',[native,'-m','physicalevobench_x.cli','smoke','--embodiment',body,'--episodes','1','--output',directory/body],project)
        after=assets(d)
        result=dict(status='FRESH_NATIVE_INSTALL_AND_SMOKE_COMMANDS_COMPLETE',formal_result_eligible=False,
            plan_hash=d['plan_hash'],scope=d['scope'],provenance=provenance,shared_assets_verified_before=before,
            shared_assets_verified_after=after,metadata_incompatibilities=observed,stages=records,
            native_smoke_commands_completed=native_started,wall_time_s=time.monotonic()-started,
            files={str(p):file_digest(p) for p in directory.glob('*.log')},
            limitations=['Smoke command completion requires retained-result inspection before claiming task success.',
                'Same machine and shared warm package/asset caches; no cold-network or independent-machine claim.',
                'Only state/IK/PhysX path; seven metadata exceptions retained, optional paths untested.'])
        write_json(directory/'report.json',result);write_json(directory/'status.json',dict(status=result['status'],stages=records,formal_result_eligible=False))
    except Exception as exc:
        write_json(directory/'status.json',dict(status='STOPPED_WITH_ERROR',error=str(exc),stages=records,
            native_smoke_commands_started=native_started,wall_time_s=time.monotonic()-started,formal_result_eligible=False))
        raise


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('command',choices=['plan','run'])
    p.add_argument('--directory',type=Path,required=True);p.add_argument('--cache',type=Path);p.add_argument('--gpu',type=int,default=1)
    args=p.parse_args()
    if args.command=='plan':
        d=plan(args.directory.resolve(),args.cache.resolve(),args.gpu);print(json.dumps(dict(plan_hash=d['plan_hash'],native_calls_planned=2)))
    else:run(args.directory.resolve())
