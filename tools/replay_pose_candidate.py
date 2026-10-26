"""Shadow replay of independent development traces; never rescores the pilot."""
import argparse
from collections import Counter
from dataclasses import asdict
import json
from pathlib import Path
import sys
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from physicalevobench_x.core.hashing import digest,file_digest,write_json
from physicalevobench_x.core.schemas import ObservationFrame,EpisodeResult,SkillSpec
from physicalevobench_x.control.geometry import rotate
from physicalevobench_x.measurement.pose_window import PoseWindowJudge,load_pose_window_config
from physicalevobench_x.sim.judge import robot_hard_failures
from pilot_suite import execution_inputs


def replay_frames(initial,frames,joint_limits,config=None):
    judge=PoseWindowJudge() if config is None else PoseWindowJudge(config)
    judge.reset(initial)
    for obs in frames:
        if obs.sim_time_s<initial.sim_time_s:continue
        axes=[rotate(obs.object_pose_w.quaternion_xyzw,np.eye(3)[i]) for i in range(3)]
        radius=sum(abs(axes[i][2])*obs.object_size_m[i]/2 for i in range(3))
        result=judge.update(obs,static_support_clear=obs.object_pose_w.position_m[2]-radius>.01,
            hard_failures=robot_hard_failures(obs,joint_limits))
        if result is not None:return result
    return None


def replay(study,original_root,output):
    config=load_pose_window_config(ROOT/'configs/measurement/pose_path_candidate_v1.yaml')
    plan=json.loads((study/'plan.json').read_text())
    if plan['plan_hash']!=digest({k:v for k,v in plan.items() if k!='plan_hash'}):
        raise ValueError('Source diagnostic plan changed')
    if execution_inputs(original_root)!=plan['execution_inputs']:
        raise ValueError('Original source inputs no longer match the diagnostic')
    review=original_root/'evidence/diagnostics/parameter_interventions_v1b/completion_review.json'
    reviewed=json.loads(review.read_text())
    if file_digest(study/'report.json')!=reviewed['files']['report.json']:
        raise ValueError('Completed source report changed')
    if json.loads((study/'report.json').read_text())['status']!='DEVELOPMENT_DIAGNOSTIC_COMPLETE':
        raise ValueError('Only a completed development study is eligible for this replay')
    if file_digest(study/'plan.json')!=reviewed['files']['plan.json']:
        raise ValueError('Source plan not matched to archived completion review')
    cases,provenance=[],{}
    for body,jobs in plan['jobs'].items():
        paths=sorted((study/body/'cases').glob('*.json'))
        if len(paths)!=len(jobs):raise ValueError('Incomplete development cases')
        for index,path in enumerate(paths):
            cell=json.loads(path.read_text());job=cell['job'];r=EpisodeResult.model_validate(cell['result'])
            if (job!=jobs[index] or r.backend!='physx' or r.infra_failure or
                r.skill_hash!=SkillSpec.model_validate(plan['variants'][job['variant']]).semantic_hash):
                raise ValueError('Development case identity mismatch')
            for name,checksum in cell['trace_measurement']['evidence_files'].items():
                if file_digest(name)!=checksum:raise ValueError('Development trace evidence changed')
                provenance[name]=checksum
            provenance[str(path)]=file_digest(path)
            trajectory=Path(r.trajectory_path)
            if file_digest(trajectory)!=r.trajectory_sha256:raise ValueError('Trajectory changed')
            meta=json.loads(trajectory.with_suffix('.json').read_text())
            trace=trajectory.with_name(r.episode_id+'_trace.jsonl')
            frames=[ObservationFrame.model_validate(json.loads(l)['observation']) for l in trace.read_text().splitlines()]
            terminal=ObservationFrame.model_validate(meta['terminal']['observation'])
            if not frames or terminal.sim_time_s>frames[-1].sim_time_s:frames.append(terminal)
            candidate=replay_frames(ObservationFrame.model_validate(meta['initial']),frames,
                                    meta['effective_robot']['joint_position_limits'],config)
            status=('CENSORED_AT_RECORDED_END' if candidate is None else
                    'SUCCESS_OBSERVED' if candidate['task_success'] else 'FAILURE_OBSERVED')
            cases.append(dict(body=body,variant=job['variant'],condition_index=plan['conditions'].index(job['condition']),
                recorded_native_success=r.task_success,recorded_native_reason=r.termination_reason,
                recorded_end_execution_s=r.completion_time_s,candidate_observation=status,candidate_terminal=candidate))
    if len(cases)!=plan['planned_valid_calls']:raise ValueError('Replay coverage mismatch')
    groups=[]
    for body in plan['jobs']:
        for variant in plan['variants']:
            rows=[c for c in cases if c['body']==body and c['variant']==variant]
            groups.append(dict(body=body,variant=variant,recorded_cases=len(rows),
                native_successes=sum(c['recorded_native_success'] for c in rows),
                candidate_observations=dict(Counter(c['candidate_observation'] for c in rows))))
    result=dict(status='DEVELOPMENT_SHADOW_REPLAY_COMPLETE',formal_result_eligible=False,
        scope='Offline replay of predeclared development records only; not new physical executions or revised pilot scores',
        source_plan_hash=plan['plan_hash'],source_review_sha256=file_digest(review),
        candidate_config=asdict(config),
        candidate_inputs={str(p.relative_to(ROOT)):file_digest(p) for p in
            [ROOT/'src/physicalevobench_x/measurement/pose_window.py',Path(__file__).resolve(),
             ROOT/'configs/measurement/pose_path_candidate_v1.yaml']},
        recorded_cases=len(cases),groups=groups,cases=cases,source_evidence_files=provenance,
        limitations=['Censored records are not counted as failures or imputed successes.',
            'Candidate termination can change episode duration; full-length physical validation remains necessary.',
            'A changed measurement is not a learner improvement; old pilot outcomes remain unchanged.'])
    output.mkdir(parents=True,exist_ok=False)
    write_json(output/'report.json',result)
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--study',type=Path,required=True)
    p.add_argument('--original-root',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    result=replay(args.study.resolve(),args.original_root.resolve(),args.output.resolve())
    print(json.dumps({'status':result['status'],'recorded_cases':result['recorded_cases'],
                      'observations':dict(Counter(c['candidate_observation'] for c in result['cases']))}))
