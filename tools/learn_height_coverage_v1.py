"""Post-hoc height coverage baseline on fresh conditions; frozen core learner protocol."""
import argparse
import json
import os
from pathlib import Path
import random
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'));sys.path.insert(0,str(ROOT/'scripts'))
import learn_geometry_v1 as base
from physicalevobench_x.core.schemas import SkillSpec,BOUNDS
from physicalevobench_x.core.hashing import digest,file_digest,write_json
from pilot_support import atomic_json

DESIGN='evidence/learning/height_coverage_design_v1.json'


def grid():
    lo,hi=BOUNDS['grasp_height_fraction']
    return [lo+(hi-lo)*i/4 for i in range(5)]


class HeightGrid:
    learner_id='height_grid_v1'
    def __init__(self,seed):
        self.index=0;self.rng=self;self.proposals=[]
    def getstate(self):return self.index
    def setstate(self,state):
        if type(state) is not int or not 0<=state<=5:raise ValueError('Bad coverage cursor')
        self.index=state
    def propose(self,incumbent,history):
        if self.index>=5:raise ValueError('Height coverage exhausted')
        data=SkillSpec.initial().model_dump();height=grid()[self.index]
        data['parameters']['grasp_height_fraction']=height
        result=SkillSpec.model_validate(data)
        self.proposals.append(dict(strategy=self.learner_id,grid_index=self.index,height=height,
                                   changed_fields=['grasp_height_fraction']))
        self.index+=1;return result


def generate_conditions():
    manifests={}
    for split,count in base.COUNTS.items():
        rng=random.Random(int(digest(dict(study='geometry-height-coverage-v1',seed=2026102605,split=split)),16));rows=[]
        for i in range(count):
            family='tall_narrow' if i%2==0 else 'wide'
            side=rng.uniform(.034,.036) if family=='tall_narrow' else rng.uniform(.064,.066)
            height=rng.uniform(.138,.142) if family=='tall_narrow' else rng.uniform(.064,.066)
            c=dict(name=family,size_m=[side,side,height],mass_kg=rng.uniform(.18,.22),
                friction=1. if family=='tall_narrow' else .5,offset_xy_m=[0.,0.],yaw_rad=0.,
                reset_seed=rng.randrange(2**31),split=split)
            c['condition_id']=digest(dict(revision='DEVELOPMENT_GEOMETRY_LEARNING_V1',condition=c))[:24];rows.append(c)
        manifests[split]=rows
    base.validate_manifests(manifests)
    previous={base.scene_fingerprint(c) for rows in base.generate_conditions().values() for c in rows}
    if any(base.scene_fingerprint(c) in previous for rows in manifests.values() for c in rows):raise ValueError('Reused primary learning scene')
    return manifests


def plan(study):
    m=generate_conditions();design=json.loads((ROOT/DESIGN).read_text())
    p=dict(study='geometry_height_coverage_source_learning_v1',task_revision='DEVELOPMENT_GEOMETRY_LEARNING_V1',
        formal_result_eligible=False,scope='Explicit post-hoc source-coverage diagnostic, one new learning package and fresh held-out conditions',
        packages=[dict(package_id='height',learner='height_grid_v1',source='franka_panda',target='franka_robotiq',proposal_seed=0)],
        split_counts=base.COUNTS,manifest_sha256=digest(m),initial_skill=SkillSpec.initial().model_dump(),
        source_budget=20,target_adaptation_budget=0,planned_physical_calls=36,physical_calls_per_package=36,
        primary_score='candidate_50hz',diagnostic_scores=['candidate_200hz','native_50hz'],physics=dict(base.calibration.PROFILES['baseline']),
        execution_inputs=base.inputs(),extension_inputs={'tools/learn_height_coverage_v1.py':file_digest(__file__),DESIGN:file_digest(ROOT/DESIGN)},
        repo_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        generator_seed=2026102605,height_grid=grid(),primary_source_design=design,
        interpretation='Method selected after two primary source rollbacks; fresh condition seed and complete before/after comparisons. Not an unbiased method comparison or population inference.',
        environment_scope='Existing pinned native runtime on same host, GPU 0; shared assets, no independent-machine claim')
    p['plan_hash']=digest(p);study.mkdir(parents=True,exist_ok=False)
    write_json(study/'private_conditions.json',m);write_json(study/'plan.json',p);return p


def verify(study):
    p,m=base.verify(study)
    if p['study']!='geometry_height_coverage_source_learning_v1':raise ValueError('Unexpected coverage study')
    for name,h in p['extension_inputs'].items():
        if file_digest(ROOT/name)!=h:raise ValueError('Coverage extension input changed')
    if m!=generate_conditions() or p['height_grid']!=grid():raise ValueError('Coverage data/grid changed')
    return p,m


OriginalRunner=base.GeometryRunner
class CheckedRunner(OriginalRunner):
    def run(self,**kwargs):verify(self.study);return super().run(**kwargs)


def worker(study):
    verify(study)
    def factory(learner,config,log_path):
        if learner!='height_grid_v1':raise ValueError('Coverage worker cannot instantiate another learner')
        return HeightGrid
    # Explicit process-local dependency injection; frozen files and other workers unchanged.
    base.proposer_factory=factory;base.GeometryRunner=CheckedRunner
    base.worker(study,'height')


def run(study,gpu,native_python):
    verify(study)
    if os.environ.get('ACCEPT_EULA')!='Y':raise ValueError('Accepted EULA required')
    env=dict(os.environ,PYTHONPATH=str(ROOT/'src'),HEADLESS='1',CUDA_VISIBLE_DEVICES=str(gpu),
        OMNI_KIT_ACCEPT_EULA='YES',ISAACLAB_ARENA_FORCE_EXIT_ON_COMPLETE='1',PYTHONUNBUFFERED='1')
    env.pop('PEBX_LLM_API_KEY',None)
    with (study/'height.log').open('x') as log:
        started=time.monotonic();pr=subprocess.Popen([str(native_python.absolute()),str(Path(__file__).resolve()),'worker','--study',str(study)],
            cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT)
        atomic_json(study/'supervisor.json',dict(status='RUNNING',pid=os.getpid(),formal_result_eligible=False,
            workers=[dict(package='height',pid=pr.pid,gpu=gpu)]))
        code=pr.wait()
    result=base.summarize(study)
    atomic_json(study/'supervisor.json',dict(status=result['status'],formal_result_eligible=False,
        workers=[dict(package='height',returncode=code,gpu=gpu,process_wall_s=time.monotonic()-started)]))
    return 0 if code==0 and result['status']=='DEVELOPMENT_LEARNING_EXECUTION_COMPLETE' else 2


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('command',choices=['plan','worker','run','summarize']);ap.add_argument('--study',type=Path,required=True)
    ap.add_argument('--native-python',type=Path);ap.add_argument('--gpu',type=int,default=0);a=ap.parse_args()
    if a.command=='plan':p=plan(a.study.resolve());print(json.dumps(dict(plan_hash=p['plan_hash'],planned_physical_calls=36)))
    elif a.command=='worker':worker(a.study.resolve())
    elif a.command=='run':raise SystemExit(run(a.study.resolve(),a.gpu,a.native_python))
    else:verify(a.study.resolve());print(json.dumps(base.summarize(a.study.resolve())))
