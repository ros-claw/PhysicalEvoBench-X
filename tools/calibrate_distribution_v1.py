"""Development-only geometry/material screening; frozen skills, no learning or selection."""
import argparse
from dataclasses import asdict
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
sys.path.insert(0,str(ROOT/'tools'))
from physicalevobench_x.core.hashing import digest,file_digest,append_json,write_json
from physicalevobench_x.core.schemas import SkillSpec
from physicalevobench_x.measurement.pose_window import load_pose_window_config,PoseWindowJudge
from physicalevobench_x.measurement.comparison import FullHorizonComparison
from pilot_suite import execution_inputs
from pilot_support import ReplayJournal,atomic_json
from validate_pose_physics_v3 import PROFILES,solver_readback


def inputs():
    result=execution_inputs(ROOT)
    for name in ('calibrate_distribution_v1.py','validate_pose_physics_v3.py'):
        result['tools/'+name]=file_digest(ROOT/'tools'/name)
    return result


def conditions():
    return [dict(name=name,size_m=size,mass_kg=mass,friction=mu,reset_seed=2026102603,
                 offset_xy_m=[0.,0.],yaw_rad=0.)
        for name,size,mass,mu in [
            ('nominal',[.045,.045,.065],.2,1.),
            ('tall_narrow',[.035,.035,.14],.2,1.),
            ('wide',[.065,.065,.065],.2,.5),
            ('heavy_low_friction',[.045,.045,.065],.65,.2)]]


def skills():
    initial=SkillSpec.initial().model_dump()
    variants={name:json.loads(json.dumps(initial)) for name in ('initial','high_grasp','slow_lift')}
    variants['high_grasp']['parameters']['grasp_height_fraction']=.7
    variants['slow_lift']['parameters'].update(lift_vmax_mps=.03,lift_amax_mps2=.1)
    return {k:SkillSpec.model_validate(v).model_dump() for k,v in variants.items()}


def plan(output):
    variants=skills();jobs={}
    for body in ('franka_panda','franka_robotiq'):
        jobs[body]=[]
        for index,c in enumerate(conditions()):
            names=list(variants);names=names[index%3:]+names[:index%3]
            for name in names:
                jobs[body].append(dict(name=c['name']+'__'+name,condition=c,variant=name,skill=variants[name],repeat_of=None))
        for name in variants:
            jobs[body].append(dict(name='tall_narrow_repeat__'+name,condition=conditions()[1],variant=name,
                                  skill=variants[name],repeat_of='tall_narrow__'+name))
    data=dict(study='distribution_calibration_v1',task_revision='DEVELOPMENT_GEOMETRY_MATERIAL_V1',
        formal_result_eligible=False,scope='Predeclared fixed development screening; no learner, held-out test or population claim',
        jobs=jobs,planned_calls=30,conditions=conditions(),skills=variants,
        candidate_config=asdict(load_pose_window_config(ROOT/'configs/measurement/pose_path_candidate_v1.yaml')),
        horizon_s=15.,settle_s=.5,physics_dt_s=.005,control_dt_s=.02,
        interpretation='Task success is descriptive, never an execution acceptance criterion. Tall condition repeats all skills. Other contrasts are single paired trials. Heavy/low-friction is a joint stressor, not a causal decomposition.',
        physics=dict(PROFILES['baseline']),execution_inputs=inputs(),
        repo_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        environment_scope='Existing pinned native environment and shared assets on the same host',
        acceptance=['Live mass, inertia, material, USD local geometry and reset position match declared conditions before actions',
            '50/200 Hz full-horizon observation or retained measured safety stop, offline three-judge replay',
            'Every planned call retained including failures, no hidden physical retries',
            'Compare repeated tall-condition public observations and actions exactly, excluding episode_id'])
    data['plan_hash']=digest(data);output.mkdir(parents=True,exist_ok=False);write_json(output/'plan.json',data)
    return data


def verify(study):
    data=json.loads((study/'plan.json').read_text())
    if data['plan_hash']!=digest({k:v for k,v in data.items() if k!='plan_hash'}) or data['execution_inputs']!=inputs():
        raise ValueError('Calibration plan or execution inputs changed')
    return data


def configure_object(arena,c):
    # Replace the complete asset before builder creation, including its reset event.
    # No edits to upstream code, the frozen factory, control or default judge.
    import isaaclab.sim as sim_utils
    from isaaclab_arena.assets.object import Object
    from isaaclab_arena.assets.object_type import ObjectType
    from isaaclab_arena.utils.pose import Pose
    arena.scene.assets['pebx_object']=Object(name='pebx_object',object_type=ObjectType.RIGID,
        initial_pose=Pose(position_xyz=(.5,0.,c['size_m'][2]/2+.002)),
        spawner_cfg=sim_utils.CuboidCfg(size=tuple(c['size_m']),
            rigid_props=sim_utils.RigidBodyPropertiesCfg(disable_gravity=False,
                solver_position_iteration_count=64,solver_velocity_iteration_count=4),
            collision_props=sim_utils.CollisionPropertiesCfg(contact_offset=.002,rest_offset=0.),
            mass_props=sim_utils.MassPropertiesCfg(mass=c['mass_kg']),
            physics_material=sim_utils.RigidBodyMaterialCfg(static_friction=c['friction'],
                dynamic_friction=c['friction'],restitution=0.)))
    arena.task.reader.size_m=tuple(c['size_m'])


def check_readback(c,r):
    import numpy as np
    size=np.asarray(c['size_m']);m=c['mass_kg']
    inertia=np.diag(m*np.array([size[1]**2+size[2]**2,size[0]**2+size[2]**2,size[0]**2+size[1]**2])/12)
    return bool(r['geometry_sizes_m'] and np.allclose(r['geometry_sizes_m'],size,atol=1e-7,rtol=0)
        and np.allclose(r['mass_kg'],m,atol=1e-6,rtol=0)
        and np.allclose(r['inertia_kg_m2'],inertia,atol=1e-8,rtol=1e-5)
        and np.asarray(r['material']).size>0
        and np.allclose(np.asarray(r['material'])[...,:3],[c['friction'],c['friction'],0.],atol=1e-6,rtol=0)
        and np.allclose(r['reset_position_m'],[.5,0.,size[2]/2+.002],atol=1e-5,rtol=0))


def object_readback(base,c):
    import numpy as np
    import warp as wp
    from isaaclab.sim.utils import get_current_stage
    from pxr import UsdGeom
    from physicalevobench_x.sim.state_reader import array
    cube=base.scene['pebx_object'];wp.synchronize()
    mass=array(cube.root_view.get_masses()).reshape(-1).tolist();wp.synchronize()
    inertia=array(cube.root_view.get_inertias()).reshape(3,3).tolist();wp.synchronize()
    material=array(cube.root_view.get_material_properties()).tolist();wp.synchronize()
    geometry=[]
    for prim in get_current_stage().Traverse():
        if 'pebx_object' in str(prim.GetPath()) and prim.IsA(UsdGeom.Cube):
            bound=UsdGeom.BBoxCache(0,[UsdGeom.Tokens.default_]).ComputeRelativeBound(prim,
                get_current_stage().GetPrimAtPath('/World/envs/env_0/pebx_object'))
            geometry.append(dict(path=str(prim.GetPath()),size_m=list(bound.ComputeAlignedRange().GetSize())))
    r=dict(mass_kg=mass,inertia_kg_m2=inertia,material=material,geometry=geometry,
        geometry_sizes_m=[g['size_m'] for g in geometry],
        reset_position_m=array(cube.data.root_pos_w)[0].tolist(),
        note='Material coefficients are object backend values; combined contact friction is not inferred.')
    r['verified']=check_readback(c,r)
    return r


def native_case(directory,body,job,data):
    import numpy as np
    import torch
    from isaaclab_arena.environments.arena_env_builder import ArenaEnvBuilder
    from isaaclab_arena.environments.arena_env_builder_cfg import ArenaEnvBuilderCfg
    from isaaclab_arena.utils.isaaclab_utils.simulation_app import teardown_simulation_app
    from physicalevobench_x.sim.arena_factory import StableLiftEnvironment,StableLiftEnvironmentCfg
    from physicalevobench_x.sim.state_reader import array
    from physicalevobench_x.sim.judge import robot_hard_failures
    from physicalevobench_x.control.geometry import rotate
    from physicalevobench_x.control.adapter import EmbodimentAdapter
    from physicalevobench_x.control.grasp_lift_executor import GraspLiftExecutor
    from physicalevobench_x.core.schemas import CanonicalCommand,Gripper
    started=time.monotonic();directory.mkdir(parents=True,exist_ok=False)
    c=job['condition'];axis=(0.,0.,0.,1.) if body=='franka_panda' else (0.,2**-.5,0.,2**-.5)
    arena=StableLiftEnvironment().build(StableLiftEnvironmentCfg(embodiment=body,axis_mapping_xyzw=axis,mass_kg=c['mass_kg']))
    configure_object(arena,c)
    comparison=FullHorizonComparison(load_pose_window_config(ROOT/'configs/measurement/pose_path_candidate_v1.yaml'))
    arena.task.judge=comparison
    env,_=ArenaEnvBuilder(arena,ArenaEnvBuilderCfg(num_envs=1,solve_relations=False,resolve_on_reset=False,seed=c['reset_seed'],mimic=False,
        recorder_dataset_export_dir_path=str(directory/'arena'),recorder_dataset_filename='calibration')).make_registered_and_return_cfg()
    base=env.unwrapped;base.pebx_task=arena.task;base.configure_episode_limit(1)
    reader=arena.task.reader;observer=PoseWindowJudge(comparison.config)
    initial=None;observer_ready=False;physics_samples=0
    try:
        with torch.inference_mode():
            env.reset(seed=c['reset_seed']);arena.task.ready=False;arena.task.last_tick=None
            arena.task.last_episode_step=-1;arena.task.terminal_evidence=None
            limits=array(base.scene['robot'].data.joint_pos_limits)[0]
            settings=solver_readback(base,data['physics']);readback=object_readback(base,c)
            write_json(directory/'readback.json',dict(solver=settings,object=readback))
            if not readback['verified'] or not settings['settings_verified']:raise ValueError('Live scene readback mismatch; no skill actions executed')
            if base._physics_handles_decimation or abs(base.physics_dt-.005)>1e-12 or abs(base.step_dt-.02)>1e-12:
                raise ValueError('Unexpected physics scheduling')
            first_step=base.sim.get_physics_step_count();original_update=base.scene.update
            def observe_update(*args,**kwargs):
                nonlocal observer_ready,physics_samples
                returned=original_update(*args,**kwargs)
                t=(base.sim.get_physics_step_count()-first_step)*base.physics_dt
                obs=reader.read(base,job['name']).model_copy(update={'sim_time_s':t})
                if t>=.5-1e-12:
                    if not observer_ready:observer.reset(obs);observer_ready=True
                    q=obs.object_pose_w.quaternion_xyzw
                    radius=sum(abs(rotate(q,np.eye(3)[i])[2])*obs.object_size_m[i]/2 for i in range(3))
                    observer.update(obs,static_support_clear=obs.object_pose_w.position_m[2]-radius>.01,
                        hard_failures=robot_hard_failures(obs,limits))
                physics_samples+=1;append_json(directory/'physics_trace.jsonl',dict(observation=obs.model_dump()))
                return returned
            base.scene.update=observe_update
            reference=reader.read(base,job['name']).tcp_pose_w
            executor=GraspLiftExecutor();adapter=EmbodimentAdapter(body)
            for _ in range(780):
                obs=reader.read(base,job['name'])
                if obs.sim_time_s>=.5-1e-12 and initial is None:
                    initial=obs;executor.reset(SkillSpec.model_validate(job['skill']),obs)
                command=executor.step(obs) if initial is not None else CanonicalCommand(tcp_pose_w=reference,gripper=Gripper.OPEN)
                action=adapter.encode(command,reader.root_w,reader.control_w,reader.control_to_tcp)
                if initial is None:
                    action=np.zeros(7);action[-1]=1. if body=='franka_panda' else 0.
                append_json(directory/'control_trace.jsonl',dict(observation=obs.model_dump(),command=command.model_dump(),
                    native_action=action.tolist(),executor_stage=executor.stage if initial is not None else 'PREPARE'))
                _,_,terminated,truncated,_=env.step(torch.as_tensor(action,device=base.device,dtype=torch.float32)[None,:])
                if bool(terminated.any() or truncated.any()):break
            if arena.task.terminal_evidence is None:raise RuntimeError('Missing pre-reset diagnostic terminal')
            terminal=arena.task.terminal_evidence
            append_json(directory/'control_trace.jsonl',dict(observation=terminal['observation'],terminal=True))
            a,b=comparison.candidate.terminal,observer.terminal
            steps=base.sim.get_physics_step_count()-first_step
            result=dict(backend='physx',body=body,scenario=job['name'],condition=c,variant=job['variant'],
                formal_result_eligible=False,candidate_50hz=a,candidate_200hz=b,native_50hz=comparison.legacy.terminal,
                rate_agreement=bool(a is not None and b is not None and a['task_success']==b['task_success']),
                terminal=terminal,physics_samples=physics_samples,physics_steps=steps,observed_sim_time_s=steps*.005,
                effective_joint_limits=limits.tolist(),readback=readback,solver_readback=settings,
                episode_wall_time_s=time.monotonic()-started)
    finally:
        env.close();teardown_simulation_app()
    result['evidence_files']={str(p):file_digest(p) for p in list(directory.glob('*trace.jsonl'))+[directory/'readback.json']}
    result.update(trajectory_path=str(directory/'control_trace.jsonl'),trajectory_sha256=file_digest(directory/'control_trace.jsonl'),
        trajectory_format='jsonl',infra_failure=None)
    return result


def worker(study,body):
    import fcntl
    data=verify(study);directory=study/body;directory.mkdir(exist_ok=True)
    with (directory/'worker.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        from isaaclab_arena.cli.isaaclab_arena_cli import get_isaaclab_arena_cli_parser
        from isaaclab_arena.utils.isaaclab_utils.simulation_app import SimulationAppContext
        with SimulationAppContext(get_isaaclab_arena_cli_parser().parse_args([])):
            journal=ReplayJournal(directory/'journal',dict(plan_hash=data['plan_hash'],body=body))
            for index,job in enumerate(data['jobs'][body]):
                verify(study)
                result=journal.call(dict(body=body,job=job),lambda:native_case(directory/job['name'],body,job,data),physical=True)
                path=directory/(job['name']+'.json')
                if path.exists() and json.loads(path.read_text())!=result:raise ValueError('Existing result changed')
                if not path.exists():atomic_json(path,result)
                atomic_json(directory/'status.json',dict(completed=index+1,planned=len(data['jobs'][body]),formal_result_eligible=False))


def summarize(study):
    data=verify(study);results=[];unresolved=[]
    for body,jobs in data['jobs'].items():
        entries=sorted((study/body/'journal').glob('[0-9]*.json'))
        for index,path in enumerate(entries):
            entry=json.loads(path.read_text())
            if entry['status']!='COMPLETE':unresolved.append(dict(body=body,index=index));continue
            if index>=len(jobs) or entry['request']!=dict(body=body,job=jobs[index]) or entry['request_hash']!=digest(entry['request']):
                raise ValueError('Journal request mismatch')
            r=entry['result']
            if r['backend']!='physx' or r['infra_failure'] is not None:raise ValueError('Non-native/infra result')
            for p,h in r['evidence_files'].items():
                if file_digest(p)!=h:raise ValueError('Trace changed')
            results.append(r)
    complete=len(results)==data['planned_calls'] and not unresolved
    result=dict(status='CALIBRATION_EXECUTION_COMPLETE' if complete else 'CALIBRATION_EXECUTION_INCOMPLETE',
        formal_result_eligible=False,plan_hash=data['plan_hash'],planned_cases=data['planned_calls'],completed_cases=len(results),
        results=results,unresolved_calls=unresolved,costs=dict(known_complete_physical_calls=len(results),
        observed_sim_time_s=sum(r['observed_sim_time_s'] for r in results),episode_wall_time_s=sum(r['episode_wall_time_s'] for r in results)))
    atomic_json(study/'report.json',result);return result


def run(study,gpus,native_python):
    data=verify(study)
    if len(gpus)!=len(data['jobs']) or len(set(gpus))!=len(gpus) or os.environ.get('ACCEPT_EULA')!='Y':raise ValueError('One GPU per worker and accepted EULA required')
    if not native_python.exists():raise ValueError('Native interpreter missing')
    logs=[study/(b+'.log') for b in data['jobs']]
    if any(p.exists() for p in logs):raise ValueError('Use explicit worker resume after reconciling old logs')
    active=[]
    for (body,_),gpu,path in zip(data['jobs'].items(),gpus,logs):
        stream=path.open('x');env=dict(os.environ,PYTHONPATH=str(ROOT/'src'),HEADLESS='1',CUDA_VISIBLE_DEVICES=str(gpu),
            OMNI_KIT_ACCEPT_EULA='YES',ISAACLAB_ARENA_FORCE_EXIT_ON_COMPLETE='1',PYTHONUNBUFFERED='1')
        process=subprocess.Popen([str(native_python.absolute()),str(Path(__file__).resolve()),'worker','--study',str(study),'--body',body],
            env=env,cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT)
        active.append((body,process,stream,time.monotonic(),gpu))
    atomic_json(study/'supervisor.json',dict(status='RUNNING',pid=os.getpid(),formal_result_eligible=False,
        workers=[dict(body=b,pid=p.pid,gpu=g) for b,p,_,_,g in active],native_python=str(native_python.absolute())))
    done=[]
    while active:
        for item in list(active):
            body,process,stream,started,gpu=item;code=process.poll()
            if code is None:continue
            stream.close();done.append(dict(body=body,returncode=code,process_wall_s=time.monotonic()-started));active.remove(item)
        if active:time.sleep(.5)
    try:report=summarize(study)
    except Exception as exc:
        atomic_json(study/'supervisor.json',dict(status='STOPPED_WITH_ERROR',error=str(exc),workers=done,formal_result_eligible=False));raise
    atomic_json(study/'supervisor.json',dict(status=report['status'],workers=done,formal_result_eligible=False))
    return 0 if report['status']=='CALIBRATION_EXECUTION_COMPLETE' and all(r['returncode']==0 for r in done) else 2


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('command',choices=['plan','worker','run','summarize']);p.add_argument('--study',type=Path,required=True)
    p.add_argument('--body',choices=['franka_panda','franka_robotiq']);p.add_argument('--native-python',type=Path)
    p.add_argument('--gpus',type=int,nargs='+',default=[0]);a=p.parse_args()
    if a.command=='plan':print(json.dumps(dict(plan_hash=plan(a.study.resolve())['plan_hash'],planned_calls=30)))
    elif a.command=='worker':worker(a.study.resolve(),a.body)
    elif a.command=='run':raise SystemExit(run(a.study.resolve(),a.gpus,a.native_python))
    else:print(json.dumps(dict(status=summarize(a.study.resolve())['status'])))
