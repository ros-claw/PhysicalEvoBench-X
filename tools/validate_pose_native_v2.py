"""Post-hoc matched-settle diagnostic v2; retains the failed v1 study unchanged."""
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
from physicalevobench_x.core.conditions import generate
from physicalevobench_x.core.hashing import digest,file_digest,append_json,write_json
from physicalevobench_x.core.schemas import SkillSpec
from physicalevobench_x.measurement.pose_window import load_pose_window_config,PoseWindowJudge
from physicalevobench_x.measurement.comparison import FullHorizonComparison
from pilot_suite import execution_inputs
from pilot_support import ReplayJournal,atomic_json


def inputs():
    result=execution_inputs(ROOT)
    result[str(Path(__file__).relative_to(ROOT))]=file_digest(__file__)
    return result


def plan(output,source_study):
    cfg=load_pose_window_config(ROOT/'configs/measurement/pose_path_candidate_v1.yaml')
    previous=ROOT/'runs/pose-native-v1-20261026'
    prior_report=json.loads((previous/'report.json').read_text())
    if prior_report['status']!='NATIVE_CANDIDATE_DIAGNOSTICS_FAILED':raise ValueError('Retained v1 failure required')
    previous_plan=json.loads((previous/'plan.json').read_text())
    source=previous_plan['source_disagreement'];case=json.loads(Path(source['path']).read_text())
    source_plan=json.loads((source_study/'plan.json').read_text())
    skill=source_plan['variants'][case['job']['variant']]
    jobs={'franka_robotiq':[dict(name=name,condition=case['job']['condition'],skill=skill,
        expected_candidate_success=True,expected_native_success=native,settle_mode=mode)
        for name,native,mode in [('matched_original_settle',False,'native_zero_relative'),
                                ('fixed_tcp_settle',True,'fixed_tcp_reference')]]}
    data=dict(study='pose_window_matched_settle_diagnostic_v2',formal_result_eligible=False,
        scope='Post-hoc diagnostic of a selected development case; not generalization or learner results',
        horizon_s=15.,control_hz=50,physics_observer_hz=200,max_positive_completion_difference_s=.025,
        jobs=jobs,planned_calls=2,candidate_config=asdict(cfg),source_disagreement=source,
        prior_study=dict(report=str(previous/'report.json'),sha256=file_digest(previous/'report.json')),
        manipulation='Only initial 0.5 s arm action differs between the two new jobs; both use the original builder seed and unchanged physics/judges.',
        execution_inputs=inputs(),repo_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        environment_scope='Shared existing pinned native installation and cached assets; not an independent installation')
    data['plan_hash']=digest(data);output.mkdir(parents=True,exist_ok=False);write_json(output/'plan.json',data)
    return data


def verify(output):
    data=json.loads((output/'plan.json').read_text())
    if (data['plan_hash']!=digest({k:v for k,v in data.items() if k!='plan_hash'})
        or data['execution_inputs']!=inputs()):raise ValueError('Native diagnostic plan/input changed')
    source=data['source_disagreement']
    if file_digest(source['path'])!=source['sha256']:raise ValueError('Source development case changed')
    prior=data['prior_study']
    if file_digest(prior['report'])!=prior['sha256']:raise ValueError('Prior failed study changed')
    return data


def native_case(directory,body,job,data):
    import math
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
    arena=StableLiftEnvironment().build(StableLiftEnvironmentCfg(embodiment=body,axis_mapping_xyzw=axis,
        mass_kg=c['mass_kg'],offset_xy_m=tuple(c['offset_xy_m']),yaw_rad=c['yaw_rad']))
    comparison=FullHorizonComparison(load_pose_window_config(ROOT/'configs/measurement/pose_path_candidate_v1.yaml'))
    arena.task.judge=comparison
    env,_=ArenaEnvBuilder(arena,ArenaEnvBuilderCfg(num_envs=1,solve_relations=False,resolve_on_reset=False,seed=c['reset_seed'],mimic=False,
        recorder_dataset_export_dir_path=str(directory/'arena'),recorder_dataset_filename='measurement')).make_registered_and_return_cfg()
    base=env.unwrapped;base.pebx_task=arena.task;base.configure_episode_limit(1)
    reader=arena.task.reader;observer=PoseWindowJudge(comparison.config)
    observer_ready=False;physics_samples=0;max_lift=0.;observed_speed_peak=0.;release_opening_peak=0.
    initial=None;applied=False;trigger_time=None;forces_active=False
    try:
        with torch.inference_mode():
            env.reset(seed=c['reset_seed']);arena.task.ready=False;arena.task.last_tick=None
            arena.task.last_episode_step=-1;arena.task.terminal_evidence=None
            cube=base.scene['pebx_object'];limits=array(base.scene['robot'].data.joint_pos_limits)[0]
            if base._physics_handles_decimation:raise RuntimeError('Individually observable PhysX steps required')
            if abs(base.physics_dt-.005)>1e-12 or abs(base.step_dt-.02)>1e-12:raise ValueError('Unexpected time steps')
            first_physics_step=base.sim.get_physics_step_count();original_update=base.scene.update
            def observe_update(*args,**kwargs):
                nonlocal observer_ready,physics_samples,max_lift,observed_speed_peak,release_opening_peak
                returned=original_update(*args,**kwargs)
                t=(base.sim.get_physics_step_count()-first_physics_step)*base.physics_dt
                obs=reader.read(base,job['name']).model_copy(update={'sim_time_s':t})
                if t>=.5-1e-12:
                    if not observer_ready:observer.reset(obs);observer_ready=True
                    else:
                        q=obs.object_pose_w.quaternion_xyzw
                        radius=sum(abs(rotate(q,np.eye(3)[i])[2])*obs.object_size_m[i]/2 for i in range(3))
                        observer.update(obs,static_support_clear=obs.object_pose_w.position_m[2]-radius>.01,
                            hard_failures=robot_hard_failures(obs,limits))
                    max_lift=max(max_lift,obs.object_pose_w.position_m[2]-observer.z0)
                    if (observer.last_window_speeds and obs.object_pose_w.position_m[2]-observer.z0>=.08
                        and (job['name']!='oscillate' or (trigger_time is not None and t>=trigger_time+1.))):
                        observed_speed_peak=max(observed_speed_peak,observer.last_window_speeds[0])
                    if applied and job['name']=='release':release_opening_peak=max(release_opening_peak,obs.gripper_opening_width_m)
                physics_samples+=1
                append_json(directory/'physics_trace.jsonl',dict(observation=obs.model_dump()))
                return returned
            base.scene.update=observe_update
            reference=reader.read(base,job['name']).tcp_pose_w
            executor=GraspLiftExecutor();adapter=EmbodimentAdapter(body)
            for _ in range(780):
                obs=reader.read(base,job['name'])
                if obs.sim_time_s>=.5-1e-12 and initial is None:
                    initial=obs;executor.reset(SkillSpec.model_validate(job['skill']),obs)
                command=CanonicalCommand(tcp_pose_w=reference,gripper=Gripper.OPEN)
                if initial is not None and job['name']!='toss':
                    command=executor.step(obs)
                    lift=obs.object_pose_w.position_m[2]-initial.object_pose_w.position_m[2]
                    if job['name']=='release' and lift>data['release_trigger_lift_m']:applied=True
                    if job['name']=='release' and applied:command=command.model_copy(update={'gripper':Gripper.OPEN})
                    if job['name']=='oscillate':
                        if trigger_time is None and lift>=data['oscillation']['trigger_lift_m']:
                            trigger_time=obs.sim_time_s;applied=True
                        if applied:
                            p=list(command.tcp_pose_w.position_m)
                            p[0]+=data['oscillation']['amplitude_m']*math.sin(2*math.pi*data['oscillation']['frequency_hz']*(obs.sim_time_s-trigger_time))
                            command=command.model_copy(update={'tcp_pose_w':command.tcp_pose_w.model_copy(update={'position_m':tuple(p)})})
                if job['name']=='toss' and initial is not None and not applied:
                    force=torch.tensor([[[0.,0.,data['toss_force_N']]]],device=base.device)
                    cube.permanent_wrench_composer.add_forces_and_torques(force,torch.zeros_like(force),is_global=True)
                    applied=forces_active=True
                action=adapter.encode(command,reader.root_w,reader.control_w,reader.control_to_tcp)
                if initial is None and job['settle_mode']=='native_zero_relative':
                    action=np.zeros(7);action[-1]=1. if body=='franka_panda' else 0.
                append_json(directory/'control_trace.jsonl',dict(observation=obs.model_dump(),command=command.model_dump(),native_action=action.tolist(),applied=applied))
                _,_,terminated,truncated,_=env.step(torch.as_tensor(action,device=base.device,dtype=torch.float32)[None,:])
                if forces_active:cube.permanent_wrench_composer.reset();forces_active=False
                if bool(terminated.any() or truncated.any()):break
            if arena.task.terminal_evidence is None:raise RuntimeError('Missing pre-reset diagnostic terminal')
            terminal=arena.task.terminal_evidence
            # Preserve final 50 Hz terminal state, which precedes Arena auto-reset.
            append_json(directory/'control_trace.jsonl',dict(observation=terminal['observation'],terminal=True))
            expected=job['expected_candidate_success']
            a,b=comparison.candidate.terminal,observer.terminal
            stimulus_ok=(job['name'] in ('matched_original_settle','fixed_tcp_settle') or
                         (applied and max_lift>=.08 and (job['name']!='oscillate' or observed_speed_peak>.03)
                          and (job['name']!='release' or release_opening_peak>=.06)))
            agreement=bool(a is not None and b is not None and a['task_success']==b['task_success'])
            timing_ok=bool(agreement and (not a['task_success'] or
                abs(a['completion_time_s']-b['completion_time_s'])<=data['max_positive_completion_difference_s']+1e-12))
            legacy=comparison.legacy.terminal
            legacy_ok=(job['expected_native_success'] is None or
                       (legacy is not None and legacy['task_success']==job['expected_native_success']))
            result=dict(backend='physx',body=body,scenario=job['name'],formal_result_eligible=False,
                candidate_50hz=a,candidate_200hz=b,native_50hz=comparison.legacy.terminal,
                expected_candidate_success=expected,stimulus_confirmed=stimulus_ok,rate_agreement=agreement,
                positive_timing_agreement=timing_ok,physics_samples=physics_samples,
                max_lift_m=max_lift,max_observed_elevated_path_speed_mps=observed_speed_peak,
                release_opening_peak_m=release_opening_peak,legacy_expectation_matched=legacy_ok,
                passed=bool(stimulus_ok and agreement and timing_ok and legacy_ok and a['task_success']==expected),
                terminal=terminal,physics_dt_s=base.physics_dt,control_dt_s=base.step_dt,
                effective_joint_limits=limits.tolist())
    finally:
        env.close();teardown_simulation_app()
    result['episode_wall_time_s']=time.monotonic()-started
    result['observed_sim_time_s']=physics_samples*.005
    result['evidence_files']={str(p):file_digest(p) for p in directory.glob('*trace.jsonl')}
    result.update(trajectory_path=str(directory/'control_trace.jsonl'),
                  trajectory_sha256=file_digest(directory/'control_trace.jsonl'),trajectory_format='jsonl',infra_failure=None)
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
                if path.exists() and json.loads(path.read_text())!=result:raise ValueError('Diagnostic result changed')
                if not path.exists():atomic_json(path,result)
                atomic_json(directory/'status.json',dict(completed=index+1,planned=len(data['jobs'][body]),formal_result_eligible=False))


def summarize(study):
    data=verify(study);results=[];unresolved=[]
    for body,jobs in data['jobs'].items():
        journal=[json.loads(p.read_text()) for p in sorted((study/body/'journal').glob('[0-9]*.json'))]
        for index,entry in enumerate(journal):
            if entry['status']!='COMPLETE':unresolved.append(dict(body=body,index=index));continue
            if (index>=len(jobs) or entry['request']!=dict(body=body,job=jobs[index])
                or entry['request_hash']!=digest(entry['request'])):raise ValueError('Diagnostic journal mismatch')
            result=entry['result']
            if result['backend']!='physx':raise ValueError('Native validation rejects fake results')
            for path,checksum in result['evidence_files'].items():
                if file_digest(path)!=checksum:raise ValueError('Native trace changed')
            results.append(result)
    complete=len(results)==data['planned_calls'] and not unresolved
    result=dict(status=('NATIVE_CANDIDATE_DIAGNOSTICS_PASSED' if all(r['passed'] for r in results) else
        'NATIVE_CANDIDATE_DIAGNOSTICS_FAILED') if complete else 'NATIVE_CANDIDATE_DIAGNOSTICS_INCOMPLETE',
        formal_result_eligible=False,plan_hash=data['plan_hash'],completed_cases=len(results),planned_cases=data['planned_calls'],
        results=results,unresolved_calls=unresolved,
        costs=dict(known_physical_calls=len(results),episode_wall_time_s=sum(r['episode_wall_time_s'] for r in results),
            observed_sim_time_s=sum(r['observed_sim_time_s'] for r in results)),
        limitations=['Fixed native measurement controls, not learner performance or generalization evidence.',
            'Known completed work only; any unresolved call has unknown additional cost.',data['environment_scope']])
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
    return 0 if report['status']=='NATIVE_CANDIDATE_DIAGNOSTICS_PASSED' and all(r['returncode']==0 for r in done) else 2


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('command',choices=['plan','worker','run','summarize']);p.add_argument('--study',type=Path,required=True)
    p.add_argument('--source-study',type=Path);p.add_argument('--body',choices=['franka_panda','franka_robotiq'])
    p.add_argument('--native-python',type=Path);p.add_argument('--gpus',type=int,nargs='+',default=[0]);args=p.parse_args()
    if args.command=='plan':print(json.dumps(plan(args.study.resolve(),args.source_study.resolve())))
    elif args.command=='worker':worker(args.study.resolve(),args.body)
    elif args.command=='run':raise SystemExit(run(args.study.resolve(),args.gpus,args.native_python))
    else:print(json.dumps(summarize(args.study.resolve())))
