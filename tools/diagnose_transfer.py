"""Predeclared paired development interventions; separate from the frozen pilot."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
from physicalevobench_x.core.conditions import generate, validate_condition
from physicalevobench_x.core.hashing import digest, file_digest, write_json
from physicalevobench_x.core.schemas import SkillSpec, EpisodeResult
from physicalevobench_x.protocol.learning import reconstruct
from pilot_suite import execution_inputs
from pilot_support import ReplayJournal, ReplayRunner, atomic_json
from diagnostic_metrics import measure_episode

BODIES = ('franka_panda', 'franka_robotiq')


def read(path):
    return json.loads(Path(path).read_text())


def variants(initial, kimi, random_skill):
    values = dict(initial=initial, kimi_after=kimi, random_after=random_skill)
    for field, value in kimi.parameters.model_dump().items():
        if value == getattr(initial.parameters, field):
            continue
        forward, reverse = initial.model_dump(), kimi.model_dump()
        forward['parameters'][field] = value
        reverse['parameters'][field] = getattr(initial.parameters, field)
        values['initial_with_'+field] = SkillSpec.model_validate(forward)
        values['kimi_revert_'+field] = SkillSpec.model_validate(reverse)
    values['initial_repeat'] = initial
    return values


def condition_fingerprint(condition):
    return digest({k:v for k,v in condition.items() if k not in ('condition_id','split','reset_seed')})


def plan(output, pilot, seed=2026102501, count=6):
    if count < 1:
        raise ValueError('Positive development condition count required')
    pilot_plan = read(pilot/'plan.json')
    if execution_inputs(ROOT) != pilot_plan['execution_inputs']:
        raise ValueError('Original execution inputs changed')
    source_files, skills = {}, {}
    for learner, label in [('bounded_llm_v1','kimi'), ('random_search_v1','random')]:
        package = pilot/'packages'/learner/'franka_robotiq/seed-0'
        checkpoint_path = package/'stages/source/complete.json'
        checkpoint = read(checkpoint_path)
        for path, checksum in checkpoint['files'].items():
            if file_digest(path) != checksum:
                raise ValueError('Source checkpoint changed')
        rebuilt = reconstruct(Path(checkpoint['output']))
        if not rebuilt['accepted_update']:
            raise ValueError('Expected an accepted, unchanged historical source artifact')
        skills[label] = SkillSpec.model_validate(rebuilt['skill'])
        source_files[str(checkpoint_path)] = file_digest(checkpoint_path)
        for name in ('before.json','after.json','selection.json','reconstruction.json'):
            path = Path(checkpoint['output'])/name
            source_files[str(path)] = file_digest(path)
    controls = variants(SkillSpec.initial(), skills['kimi'], skills['random'])
    conditions = generate(seed, dict(dev=count))['dev']
    old_ids, old_resets, old_physics = set(), set(), set()
    for path in {p['conditions_path'] for p in pilot_plan['packages']}:
        for rows in read(path).values():
            for condition in rows:
                old_ids.add(condition['condition_id'])
                old_resets.add(condition['reset_seed'])
                old_physics.add(condition_fingerprint(condition))
    for c in conditions:
        validate_condition(c)
        if c['condition_id'] in old_ids or c['reset_seed'] in old_resets or condition_fingerprint(c) in old_physics:
            raise ValueError('New development condition overlaps the historical pilot')
    jobs = {}
    names = list(controls)
    for body in BODIES:
        jobs[body] = []
        for i, condition in enumerate(conditions):
            # Rotate ordering deterministically. No result-dependent rescheduling.
            shift = (5*i) % len(names)
            order = names[shift:]+names[:shift]
            for name in order:
                jobs[body].append(dict(condition=condition, variant=name, candidate_index=names.index(name)))
    output.mkdir(parents=True, exist_ok=False)
    data = dict(study='development_parameter_interventions_v1', formal_result_eligible=False,
        scope='Post-pilot mechanism diagnosis on independent development conditions; no learning, tuning or original-test reruns',
        seed=seed, conditions=conditions, variants={k:v.model_dump() for k,v in controls.items()}, jobs=jobs,
        planned_valid_calls=sum(map(len,jobs.values())), aliases=0, model_requests=0,
        null_control='initial_repeat is separately executed, never aliased',
        contrasts='Full artifact versus initial; forward single-field changes and reverse single-field restorations. Interactions remain possible.',
        retry_policy='At most one immediate retry per invalid call; at most two infrastructure retries per body; all attempts retained',
        pilot_freeze_hash=pilot_plan['freeze_hash'], pilot_plan_sha256=file_digest(pilot/'plan.json'),
        pilot_plan_path=str(pilot/'plan.json'), historical_source_files=source_files,
        execution_inputs=execution_inputs(ROOT),
        diagnostic_tools={str(p.relative_to(ROOT)):file_digest(p) for p in
                          [ROOT/'tools/diagnose_transfer.py',ROOT/'tools/diagnostic_metrics.py']},
        separation_checked=dict(condition_ids=True, reset_seeds=True, physical_conditions=True),
        repo_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip())
    data['plan_hash'] = digest(data)
    write_json(output/'plan.json', data)
    return data


def verify(study):
    data = read(study/'plan.json')
    if data['plan_hash'] != digest({k:v for k,v in data.items() if k!='plan_hash'}):
        raise ValueError('Diagnostic plan changed')
    if data['execution_inputs'] != execution_inputs(ROOT):
        raise ValueError('Frozen execution inputs changed')
    for path, checksum in {**data['historical_source_files'], **data['diagnostic_tools']}.items():
        path = Path(path) if Path(path).is_absolute() else ROOT/path
        if file_digest(path) != checksum:
            raise ValueError('Diagnostic code/source artifact changed: '+str(path))
    if file_digest(data['pilot_plan_path']) != data['pilot_plan_sha256']:
        raise ValueError('Historical pilot plan changed')
    return data


def worker(study, body):
    import fcntl
    data = verify(study)
    directory = study/body
    directory.mkdir(exist_ok=True)
    with (directory/'worker.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        from isaaclab_arena.cli.isaaclab_arena_cli import get_isaaclab_arena_cli_parser
        from isaaclab_arena.utils.isaaclab_utils.simulation_app import SimulationAppContext
        with SimulationAppContext(get_isaaclab_arena_cli_parser().parse_args([])):
            from physicalevobench_x.sim.runner import PhysXRunner
            runner = ReplayRunner(ReplayJournal(directory/'journal', dict(plan_hash=data['plan_hash'],body=body)),
                                  PhysXRunner(body, directory/'trajectories'))
            retries, selected = 0, []
            started = time.monotonic()
            for index, job in enumerate(data['jobs'][body]):
                verify(study)
                skill = SkillSpec.model_validate(data['variants'][job['variant']])
                for attempt in range(2):
                    result = runner.run(skill=skill, condition=job['condition'], phase='calibration',
                                        candidate_index=job['candidate_index'], attempt_index=attempt)
                    if (result.condition_id != job['condition']['condition_id'] or result.skill_hash != skill.semantic_hash
                        or result.split != 'dev' or result.backend != 'physx' or result.phase != 'calibration'
                        or result.candidate_index != job['candidate_index'] or result.attempt_index != attempt):
                        raise ValueError('Diagnostic physical result identity mismatch')
                    if not result.infra_failure:
                        break
                    if attempt or retries >= 2:
                        raise RuntimeError('Infrastructure retry cap reached; study incomplete')
                    retries += 1
                path = directory/'cases'/f'{index:04d}.json'
                cell = dict(job=job,result=result.model_dump())
                if path.exists():
                    old=read(path)
                    if old['job']!=job or old['result']!=result.model_dump():
                        raise ValueError('Selected case changed')
                else:
                    atomic_json(path,{**cell,'trace_measurement':measure_episode(result.model_dump())})
                selected.append(result)
                atomic_json(directory/'status.json',dict(status='RUNNING',completed=len(selected),
                    planned=len(data['jobs'][body]),infra_retries=retries,formal_result_eligible=False))
            atomic_json(directory/'status.json',dict(status='COMPLETE',completed=len(selected),
                planned=len(data['jobs'][body]),infra_retries=retries,
                current_worker_wall_s=time.monotonic()-started,formal_result_eligible=False))


def summarize(study):
    data = verify(study)
    points, costs, unresolved, contrasts, seen = [], [], [], [], set()
    valid_calls=0
    for body in BODIES:
        directory=study/body
        entries=[read(p) for p in sorted((directory/'journal').glob('[0-9]*.json'))]
        unresolved.extend(dict(body=body,index=i) for i,e in enumerate(entries) if e['status']!='COMPLETE')
        actual=[EpisodeResult.model_validate(e['result']) for e in entries if e['status']=='COMPLETE']
        if len({r.episode_id for r in actual})!=len(actual):
            raise ValueError('Duplicate physical execution in diagnostic journal')
        if seen & {r.episode_id for r in actual}:raise ValueError('Execution reused across bodies')
        seen.update(r.episode_id for r in actual)
        valid_calls += sum(not r.infra_failure for r in actual)
        actual_map={r.episode_id:r for r in actual}
        for entry in entries:
            if entry['status']!='COMPLETE':continue
            req, result=entry['request'],entry['result']
            if (entry['request_hash']!=digest(req) or req['condition'] not in data['conditions']
                or result['skill_hash']!=SkillSpec.model_validate(req['skill']).semantic_hash
                or result['condition_id']!=req['condition']['condition_id'] or result['backend']!='physx'
                or (result['phase'],result['candidate_index'],result['attempt_index'],result['split']) !=
                   (req['phase'],req['candidate_index'],req['attempt_index'],req['condition']['split'])):
                raise ValueError('Diagnostic journal identity mismatch')
        costs.append(dict(body=body,physical_calls=len(actual),infra_failures=sum(bool(r.infra_failure) for r in actual),
            sim_time_s=sum(r.sim_time_s for r in actual),episode_wall_s=sum(r.wall_time_s for r in actual)))
        cases=[]
        for path in sorted((directory/'cases').glob('*.json')):
            cell=read(path)
            index=int(path.stem)
            if cell['job']!=data['jobs'][body][index]:raise ValueError('Diagnostic job changed')
            result=EpisodeResult.model_validate(cell['result'])
            if result!=actual_map.get(result.episode_id) or result.infra_failure:
                raise ValueError('Selected result does not match a valid actual journal execution')
            if (result.skill_hash!=SkillSpec.model_validate(data['variants'][cell['job']['variant']]).semantic_hash
                or result.condition_id!=cell['job']['condition']['condition_id']
                or cell['trace_measurement']['episode_id']!=result.episode_id):
                raise ValueError('Selected variant/condition mismatch')
            cases.append(cell)
        if len({c['result']['episode_id'] for c in cases})!=len(cases):
            raise ValueError('A physical execution was reused for distinct diagnostic cases')
        for name in data['variants']:
            selected=[c for c in cases if c['job']['variant']==name]
            for c in selected:
                result=c['result']
                if file_digest(result['trajectory_path'])!=result['trajectory_sha256']:
                    raise ValueError('Diagnostic trajectory changed')
                for path, checksum in c['trace_measurement']['evidence_files'].items():
                    if file_digest(path)!=checksum:raise ValueError('Trace evidence changed')
            points.append(dict(body=body,variant=name,completed=len(selected),planned=len(data['conditions']),
                successes=sum(c['result']['task_success'] for c in selected),
                failures=[c['trace_measurement'] for c in selected if not c['result']['task_success']]))
        comparisons=[('initial','kimi_after'),('initial','random_after'),('initial','initial_repeat')]
        comparisons += [('initial',v) for v in data['variants'] if v.startswith('initial_with_')]
        comparisons += [('kimi_after',v) for v in data['variants'] if v.startswith('kimi_revert_')]
        for before_name,after_name in comparisons:
            before={c['job']['condition']['condition_id']:c for c in cases if c['job']['variant']==before_name}
            after={c['job']['condition']['condition_id']:c for c in cases if c['job']['variant']==after_name}
            common=sorted(before.keys() & after.keys())
            deltas=[int(after[c]['result']['task_success'])-int(before[c]['result']['task_success']) for c in common]
            contrasts.append(dict(body=body,before=before_name,after=after_name,matched_conditions=len(common),
                planned_conditions=len(data['conditions']),success_delta=sum(deltas)/len(deltas) if deltas else None,
                gained_successes=sum(d==1 for d in deltas),lost_successes=sum(d==-1 for d in deltas),
                null_control=after_name=='initial_repeat'))
    complete=(all(p['completed']==p['planned'] for p in points) and not unresolved
              and valid_calls==data['planned_valid_calls'])
    report=dict(status='DEVELOPMENT_DIAGNOSTIC_COMPLETE' if complete else 'DEVELOPMENT_DIAGNOSTIC_INCOMPLETE',
        formal_result_eligible=False,scope=data['scope'],plan_hash=data['plan_hash'],points=points,costs=costs,contrasts=contrasts,
        unresolved_calls=unresolved,limitations=['Six paired development conditions; exploratory mechanism evidence, not population-level significance.',
            'Fixed artifacts and controlled parameter changes, not learned improvements.',
            'Single-field effects depend on reference configuration; parameter interactions remain possible.'])
    atomic_json(study/'report.json',report)
    return report


def run(study, gpus):
    verify(study)
    if len(gpus)!=2 or len(set(gpus))!=2 or os.environ.get('ACCEPT_EULA')!='Y':
        raise ValueError('Two distinct GPUs and accepted EULA required')
    if any((study/(body+'.log')).exists() for body in BODIES):
        raise ValueError('Supervisor logs already exist; reconcile and resume individual workers explicitly')
    active=[]
    for body,gpu in zip(BODIES,gpus):
        log=(study/(body+'.log')).open('x')
        env=dict(os.environ,CUDA_VISIBLE_DEVICES=str(gpu),HEADLESS='1',OMNI_KIT_ACCEPT_EULA='YES',
                 ISAACLAB_ARENA_FORCE_EXIT_ON_COMPLETE='1',PYTHONUNBUFFERED='1')
        process=subprocess.Popen([str(ROOT/'third_party/IsaacLab-Arena/.venv/bin/python'),str(Path(__file__).resolve()),
            'worker','--study',str(study),'--body',body],cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT)
        active.append((body,process,log,time.monotonic()))
    atomic_json(study/'supervisor.json',dict(status='RUNNING',pid=os.getpid(),
        workers=[dict(body=b,pid=p.pid,gpu=g) for (b,p,_,_),g in zip(active,gpus)],formal_result_eligible=False))
    codes=[]
    pending=list(active)
    while pending:
        for item in list(pending):
            body,process,log,started=item
            code=process.poll()
            if code is None:continue
            codes.append(dict(body=body,returncode=code,process_wall_s=time.monotonic()-started))
            log.close()
            pending.remove(item)
        if pending:time.sleep(.5)
    try:
        report=summarize(study)
    except Exception as exc:
        atomic_json(study/'supervisor.json',dict(status='STOPPED_WITH_ERROR',workers=codes,
            error_type=type(exc).__name__,error=str(exc),formal_result_eligible=False))
        raise
    atomic_json(study/'supervisor.json',dict(status=report['status'],workers=codes,formal_result_eligible=False))
    return 0 if report['status']=='DEVELOPMENT_DIAGNOSTIC_COMPLETE' and all(c['returncode']==0 for c in codes) else 2


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('command',choices=['plan','worker','run','summarize'])
    p.add_argument('--study',type=Path,required=True)
    p.add_argument('--pilot',type=Path,default=ROOT/'runs/complete-v2-20261023/pilot')
    p.add_argument('--body',choices=BODIES)
    p.add_argument('--gpus',type=int,nargs=2,default=[0,1])
    args=p.parse_args()
    if args.command=='plan':
        result=plan(args.study.resolve(),args.pilot.resolve())
        print(json.dumps(dict(plan_hash=result['plan_hash'],planned_valid_calls=result['planned_valid_calls'])))
    elif args.command=='worker':worker(args.study.resolve(),args.body)
    elif args.command=='run':raise SystemExit(run(args.study.resolve(),args.gpus))
    else:print(json.dumps(summarize(args.study.resolve())))
