"""New development geometry task: genuine budgeted source learning and zero-budget transfer."""
import argparse
import json
import math
import os
from pathlib import Path
import random
import shutil
import subprocess
import sys
import time
import uuid

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'));sys.path.insert(0,str(ROOT/'tools'))
from physicalevobench_x.core.hashing import digest,file_digest,write_json
from physicalevobench_x.core.schemas import SkillSpec,EpisodeResult
from physicalevobench_x.learners.factory import proposer_factory,load_local_credential
from physicalevobench_x.protocol.learning import learn,reconstruct
from physicalevobench_x.protocol.paired import paired_evaluate
from pilot_support import ReplayJournal,ReplayRunner,replay_factory,atomic_json
from pilot_suite import stage
import calibrate_distribution_v1 as calibration

COUNTS={'source_train':2,'source_validation':4,'source_audit':4,'target_test':4}


def inputs():
    result=calibration.inputs();result['tools/learn_geometry_v1.py']=file_digest(__file__)
    return result


def scene_fingerprint(c):
    return digest({k:c[k] for k in ('size_m','mass_kg','friction','offset_xy_m','yaw_rad')})


def generate_conditions():
    manifests={}
    for split,count in COUNTS.items():
        rng=random.Random(int(digest(dict(study='geometry-learning-v1',seed=2026102604,split=split)),16))
        rows=[]
        for i in range(count):
            family='tall_narrow' if i%2==0 else 'wide'
            side=rng.uniform(.034,.036) if family=='tall_narrow' else rng.uniform(.064,.066)
            height=rng.uniform(.138,.142) if family=='tall_narrow' else rng.uniform(.064,.066)
            c=dict(name=family,size_m=[side,side,height],mass_kg=rng.uniform(.18,.22),
                friction=1. if family=='tall_narrow' else .5,offset_xy_m=[0.,0.],yaw_rad=0.,
                reset_seed=rng.randrange(2**31),split=split)
            c['condition_id']=digest(dict(revision='DEVELOPMENT_GEOMETRY_LEARNING_V1',condition=c))[:24]
            rows.append(c)
        manifests[split]=rows
    validate_manifests(manifests)
    return manifests


def validate_manifests(manifests):
    if set(manifests)!=set(COUNTS):raise ValueError('Unexpected learning split')
    ids=[];scenes=[];prior={scene_fingerprint(c) for c in calibration.conditions()}
    expected={'name','size_m','mass_kg','friction','offset_xy_m','yaw_rad','reset_seed','split','condition_id'}
    for split,rows in manifests.items():
        if len(rows)!=COUNTS[split]:raise ValueError('Wrong split count')
        for c in rows:
            if set(c)!=expected or c['split']!=split or c['name'] not in ('tall_narrow','wide'):
                raise ValueError('Condition field/split mismatch')
            if type(c['reset_seed']) is not int or not 0<=c['reset_seed']<2**31:raise ValueError('Invalid reset seed')
            nums=[*c['size_m'],c['mass_kg'],c['friction'],*c['offset_xy_m'],c['yaw_rad']]
            if any(type(v) not in (int,float) or not math.isfinite(v) for v in nums):raise ValueError('Nonfinite condition')
            if len(c['size_m'])!=3 or c['offset_xy_m']!=[0.,0.] or c['yaw_rad']!=0. or not .18<=c['mass_kg']<=.22:
                raise ValueError('Unsupported placement/mass')
            side,height,mu=((.034,.036),(.138,.142),1.) if c['name']=='tall_narrow' else ((.064,.066),(.064,.066),.5)
            if not all(side[0]<=v<=side[1] for v in c['size_m'][:2]) or not height[0]<=c['size_m'][2]<=height[1] or c['friction']!=mu:
                raise ValueError('Outside declared geometry/material stratum')
            if c['condition_id']!=digest(dict(revision='DEVELOPMENT_GEOMETRY_LEARNING_V1',condition={k:v for k,v in c.items() if k!='condition_id'}))[:24]:
                raise ValueError('Condition identity mismatch')
            ids.append(c['condition_id']);scenes.append(scene_fingerprint(c))
        if [c['name'] for c in rows].count('tall_narrow')!=len(rows)//2:raise ValueError('Unbalanced split')
    if len(set(ids))!=len(ids) or len(set(scenes))!=len(scenes) or set(scenes)&prior:
        raise ValueError('Overlapping conditions or reused calibration scene')
    return manifests


def plan(study):
    manifest=generate_conditions()
    packages=[dict(package_id=name,learner=learner,source='franka_panda',target='franka_robotiq',proposal_seed=0)
              for name,learner in [('random','random_search_v1'),('kimi','bounded_llm_v1')]]
    data=dict(study='geometry_source_learning_and_zero_budget_transfer_v1',task_revision='DEVELOPMENT_GEOMETRY_LEARNING_V1',
        formal_result_eligible=False,scope='Two development packages, one learning seed, Panda to Robotiq; not a formal benchmark release',
        packages=packages,split_counts=COUNTS,manifest_sha256=digest(manifest),initial_skill=SkillSpec.initial().model_dump(),
        source_budget=20,target_adaptation_budget=0,planned_physical_calls=72,physical_calls_per_package=36,
        primary_score='candidate_50hz',diagnostic_scores=['candidate_200hz','native_50hz'],
        physics=dict(calibration.PROFILES['baseline']),execution_inputs=inputs(),
        repo_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        sampling=dict(generator_seed=2026102604,strata=['tall_narrow','wide'],equal_stratum_weights=True,
            placement='central, yaw zero',mass_kg=[.18,.22],tall_side_m=[.034,.036],tall_height_m=[.138,.142],
            wide_side_m=[.064,.066],wide_height_m=[.064,.066],tall_friction=1.,wide_friction=.5),
        invariants=['Unchanged executor, bounds, initial skill, 20-call schedule, selection and 5% time acceptance rule',
            'Source validation only decides acceptance; source audit and target scores never feed back to proposals or selection',
            'Source artifact frozen before audit and target evaluation; no target training or adaptation',
            'No developer-authored high-grasp candidate or prior calibration feedback injected into proposers',
            'Always execute both paired sides, including rollbacks with identical artifacts; no free cached candidates or aliases',
            'All ambiguous started calls retained and never automatically replayed; partial projections retained',
            'Private exact manifests and raw condition-bearing traces remain outside Git'],
        interpretation='Fixed development strata chosen after calibration. One seed and four pairs per audit/evaluation cannot support population significance or an unbiased benchmark-validity claim.',
        environment_scope='Existing pinned native environment, same host and shared assets; not independent-machine reproduction')
    data['plan_hash']=digest(data);study.mkdir(parents=True,exist_ok=False)
    write_json(study/'private_conditions.json',manifest);write_json(study/'plan.json',data)
    return data


def verify(study):
    p=json.loads((study/'plan.json').read_text());m=json.loads((study/'private_conditions.json').read_text())
    if p['plan_hash']!=digest({k:v for k,v in p.items() if k!='plan_hash'}) or p['execution_inputs']!=inputs():
        raise ValueError('Learning plan or execution inputs changed')
    if digest(m)!=p['manifest_sha256']:raise ValueError('Learning split manifest changed')
    validate_manifests(m)
    return p,m


def seal_native(directory,attempt,expected):
    records=sorted(directory.glob('*_native.json'))
    if len(records)!=expected:raise ValueError('Unexpected native call count at stage seal')
    files={}
    for path in records:
        raw=json.loads(path.read_text());files[str(path)]=file_digest(path)
        for name,h in {**raw['evidence_files'],raw['binding_path']:raw['binding_sha256']}.items():
            if file_digest(name)!=h:raise ValueError('Native evidence changed before sealing')
            files[name]=h
    write_json(attempt/'native_evidence_manifest.json',dict(files=files,physical_calls=len(records)))


def validate_raw(raw,body,condition,episode_id):
    if (raw['backend']!='physx' or raw['body']!=body or raw['condition']!=condition or
        raw['scenario']!=episode_id or raw['infra_failure'] is not None or
        raw['candidate_50hz'] is None or raw['candidate_200hz'] is None or raw['native_50hz'] is None or
        not calibration.check_readback(condition,raw['readback']) or not raw['solver_readback']['settings_verified']):
        raise ValueError('Native result/condition identity or scene readback mismatch')
    for name,h in raw['evidence_files'].items():
        if file_digest(name)!=h:raise ValueError('Returned native evidence changed')


class GeometryRunner:
    def __init__(self,study,body,directory):
        self.study,self.body,self.directory=study,body,directory
        self.directory.mkdir(parents=True,exist_ok=True)

    def run(self,*,skill,condition,phase,candidate_index,attempt_index):
        p,m=verify(self.study)
        if condition not in m[condition['split']]:raise ValueError('Condition outside frozen development manifest')
        if shutil.disk_usage(self.directory).free<2*1024**3:raise RuntimeError('DISK_LIMIT')
        episode_id=uuid.uuid4().hex;raw_dir=self.directory/episode_id
        request=dict(skill=skill.model_dump(),condition=condition,phase=phase,candidate_index=candidate_index,attempt_index=attempt_index)
        binding=dict(episode_id=episode_id,body=self.body,plan_hash=p['plan_hash'],request=request,request_hash=digest(request))
        write_json(self.directory/(episode_id+'_binding.json'),binding)
        job=dict(name=episode_id,condition=condition,skill=skill.model_dump(),variant='budgeted_candidate',repeat_of=None)
        raw=calibration.native_case(raw_dir,self.body,job,p)
        validate_raw(raw,self.body,condition,episode_id)
        raw.update(binding_path=str(self.directory/(episode_id+'_binding.json')),
            binding_sha256=file_digest(self.directory/(episode_id+'_binding.json')))
        write_json(self.directory/(episode_id+'_native.json'),raw)
        score=raw[p['primary_score']]
        if score is None:raise RuntimeError('Missing primary score')
        result=EpisodeResult(episode_id=episode_id,condition_id=condition['condition_id'],split=condition['split'],phase=phase,
            candidate_index=candidate_index,attempt_index=attempt_index,skill_hash=skill.semantic_hash,backend='physx',
            task_success=score['task_success'],constraint_violations=score['constraint_violations'],
            max_lift_m=score['max_lift_m'],completion_time_s=score['completion_time_s'],hold_time_s=score['hold_time_s'],
            termination_reason=score['termination_reason'],simulator_steps=raw['physics_steps'],sim_time_s=raw['observed_sim_time_s'],
            wall_time_s=raw['episode_wall_time_s'],trajectory_path=raw['trajectory_path'],trajectory_sha256=raw['trajectory_sha256'])
        return result


def worker(study,package_id):
    import fcntl
    p,m=verify(study);package=next(x for x in p['packages'] if x['package_id']==package_id)
    output=study/'packages'/package_id;output.mkdir(parents=True,exist_ok=True)
    identity=dict(plan_hash=p['plan_hash'],package=package)
    with (output/'worker.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        from isaaclab_arena.cli.isaaclab_arena_cli import get_isaaclab_arena_cli_parser
        from isaaclab_arena.utils.isaaclab_utils.simulation_app import SimulationAppContext
        with SimulationAppContext(get_isaaclab_arena_cli_parser().parse_args([])):
            initial=SkillSpec.model_validate(p['initial_skill'])
            def source_op(attempt,journals):
                physical=ReplayJournal(journals/'physical',identity);proposals=ReplayJournal(journals/'proposals',identity)
                runner=ReplayRunner(physical,GeometryRunner(study,package['source'],output/'trajectories/source'))
                factory=replay_factory(proposals,proposer_factory(package['learner'],ROOT/'configs/learners/kimi_k3.yaml',output/'model_calls.jsonl'))
                after=learn(initial,20,m['source_train'],m['source_validation'],factory,package['proposal_seed'],runner,attempt)
                write_json(attempt/'frozen_output.json',after);write_json(attempt/'reconstruction.json',reconstruct(attempt))
                seal_native(output/'trajectories/source',attempt,20)
            source=stage(output,'source',identity,source_op)
            after=SkillSpec.model_validate_json((source/'after.json').read_text())
            freeze=dict(before_hash=initial.semantic_hash,after_hash=after.semantic_hash,source_output=str(source),
                source_after_sha256=file_digest(source/'after.json'),selection_sha256=file_digest(source/'selection.json'),
                native_manifest_sha256=file_digest(source/'native_evidence_manifest.json'))
            frozen=output/'artifact_freeze.json'
            if frozen.exists() and json.loads(frozen.read_text())!=freeze:raise ValueError('Frozen source artifact changed')
            if not frozen.exists():atomic_json(frozen,freeze)
            for name,body,split,phase in [('source_audit',package['source'],'source_audit','source_audit'),
                                          ('target_zero',package['target'],'target_test','evaluation')]:
                verify(study)
                def paired_op(attempt,journals):
                    journal=ReplayJournal(journals/'physical',identity)
                    runner=ReplayRunner(journal,GeometryRunner(study,body,output/'trajectories'/name))
                    pairs=paired_evaluate(initial,after,m[split],lambda side:runner,attempt,equivalent=False,phase=phase)
                    rows=[dict(condition_id=c['condition_id'],stratum=c['name'],before=a.model_dump(),after=b.model_dump())
                          for c,(a,b) in zip(m[split],pairs,strict=True)]
                    write_json(attempt/'paired_results.json',rows)
                    write_json(attempt/'summary.json',dict(pairs=len(rows),before_successes=sum(a.task_success for a,b in pairs),
                        after_successes=sum(b.task_success for a,b in pairs),delta_new=sum(int(b.task_success)-int(a.task_success) for a,b in pairs)/len(pairs)))
                    seal_native(output/'trajectories'/name,attempt,8)
                stage(output,name,identity,paired_op)
            atomic_json(output/'status.json',dict(status='PACKAGE_COMPLETE',formal_result_eligible=False,package_id=package_id))


def summarize(study):
    p,m=verify(study);packages=[];unresolved=[];costs=dict(known_complete_physical_calls=0,observed_sim_time_s=0.,episode_wall_time_s=0.)
    for package in p['packages']:
        root=study/'packages'/package['package_id'];entries=sorted((root/'stages').glob('*/journal/physical/[0-9]*.json'))
        complete=root/'status.json';projection={}
        for path in entries:
            record=json.loads(path.read_text())
            if record['status']!='COMPLETE':unresolved.append(str(path));continue
            r=EpisodeResult.model_validate(record['result'])
            if record['request_hash']!=digest(record['request']) or file_digest(r.trajectory_path)!=r.trajectory_sha256:
                raise ValueError('Physical request/trace identity mismatch')
            costs['known_complete_physical_calls']+=1;costs['observed_sim_time_s']+=r.sim_time_s;costs['episode_wall_time_s']+=r.wall_time_s
        for name in ('source','source_audit','target_zero'):
            checkpoint=root/'stages'/name/'complete.json'
            if checkpoint.exists():
                cp=json.loads(checkpoint.read_text());out=Path(cp['output'])
                projection[name]=dict(output=str(out),selection=json.loads((out/'selection.json').read_text()) if name=='source' else json.loads((out/'summary.json').read_text()))
        packages.append(dict(package=package,status=json.loads(complete.read_text())['status'] if complete.exists() else 'INCOMPLETE',
                             complete_calls=sum(json.loads(f.read_text())['status']=='COMPLETE' for f in entries),stages=projection))
    done=not unresolved and costs['known_complete_physical_calls']==p['planned_physical_calls'] and all(x['status']=='PACKAGE_COMPLETE' for x in packages)
    result=dict(status='DEVELOPMENT_LEARNING_EXECUTION_COMPLETE' if done else 'DEVELOPMENT_LEARNING_EXECUTION_INCOMPLETE',
        formal_result_eligible=False,plan_hash=p['plan_hash'],packages=packages,unresolved_calls=unresolved,costs=costs)
    atomic_json(study/'report.json',result);return result


def run(study,gpus,native_python,credential_file=None):
    p,m=verify(study)
    if len(gpus)!=len(p['packages']) or len(set(gpus))!=len(gpus) or os.environ.get('ACCEPT_EULA')!='Y':raise ValueError('Distinct GPUs and accepted EULA required')
    if credential_file:load_local_credential(credential_file)
    else:load_local_credential(ROOT/'.env')
    if any(x['learner']=='bounded_llm_v1' for x in p['packages']) and not os.environ.get('PEBX_LLM_API_KEY'):
        raise ValueError('Kimi credential absent before any physical call')
    active=[]
    for package,gpu in zip(p['packages'],gpus,strict=True):
        log=study/(package['package_id']+'.log');stream=log.open('x')
        env=dict(os.environ,PYTHONPATH=str(ROOT/'src'),HEADLESS='1',CUDA_VISIBLE_DEVICES=str(gpu),
            OMNI_KIT_ACCEPT_EULA='YES',ISAACLAB_ARENA_FORCE_EXIT_ON_COMPLETE='1',PYTHONUNBUFFERED='1')
        process=subprocess.Popen([str(native_python.absolute()),str(Path(__file__).resolve()),'worker','--study',str(study),'--package',package['package_id']],
            env=env,cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT)
        active.append((package['package_id'],process,stream,time.monotonic(),gpu))
    atomic_json(study/'supervisor.json',dict(status='RUNNING',pid=os.getpid(),formal_result_eligible=False,
        workers=[dict(package=n,pid=pr.pid,gpu=g) for n,pr,_,_,g in active]))
    done=[]
    while active:
        for item in list(active):
            name,pr,stream,start,gpu=item;code=pr.poll()
            if code is None:continue
            stream.close();done.append(dict(package=name,returncode=code,gpu=gpu,process_wall_s=time.monotonic()-start));active.remove(item)
        if active:time.sleep(.5)
    result=summarize(study)
    atomic_json(study/'supervisor.json',dict(status=result['status'],workers=done,formal_result_eligible=False))
    return 0 if result['status']=='DEVELOPMENT_LEARNING_EXECUTION_COMPLETE' and all(x['returncode']==0 for x in done) else 2


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('command',choices=['plan','worker','run','summarize']);ap.add_argument('--study',type=Path,required=True)
    ap.add_argument('--package',choices=['random','kimi']);ap.add_argument('--native-python',type=Path);ap.add_argument('--gpus',type=int,nargs='+',default=[0,1]);ap.add_argument('--credential-file',type=Path)
    a=ap.parse_args()
    if a.command=='plan':p=plan(a.study.resolve());print(json.dumps(dict(plan_hash=p['plan_hash'],planned_physical_calls=p['planned_physical_calls'])))
    elif a.command=='worker':worker(a.study.resolve(),a.package)
    elif a.command=='run':raise SystemExit(run(a.study.resolve(),a.gpus,a.native_python,a.credential_file))
    else:print(json.dumps(summarize(a.study.resolve())))
