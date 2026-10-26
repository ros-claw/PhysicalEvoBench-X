"""Offline audit: frozen artifacts, genuine training, held-out isolation and every native trace."""
import argparse
import json
from pathlib import Path
import sys
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'));sys.path.insert(0,str(ROOT/'scripts'))
from learn_geometry_v1 import verify,validate_raw
from physicalevobench_x.core.hashing import digest,file_digest,write_json,canonical
from physicalevobench_x.core.schemas import SkillSpec,EpisodeResult,bounds_for
from physicalevobench_x.learners.bounded_llm import PROMPT
from physicalevobench_x.protocol.learning import learn,reconstruct
from physicalevobench_x.learners.random_search import RandomSearch
from physicalevobench_x.measurement.pose_window import load_pose_window_config
from pilot_support import ReplayRunner,replay_factory
from audit_pose_native import replay
from audit_pose_physics_v3 import configuration_matches,trace_clock_summary,motion_summary
from audit_distribution_v1 import compare_traces


class ReadOnlyJournal:
    """Never append STARTED during an audit, including missing/corrupt replay records."""
    def __init__(self,directory,identity):
        self.directory,self.index=directory,0
        if json.loads((directory/'identity.json').read_text())!=identity:raise ValueError('Journal identity mismatch')
    def call(self,request,execute,*,physical=False):
        path=self.directory/f'{self.index:05d}.json';self.index+=1
        record=json.loads(path.read_text())
        if (record['status']!='COMPLETE' or digest(record['request'])!=digest(request) or record['request_hash']!=digest(request)
            or record['physical'] is not physical):raise ValueError('Read-only replay request mismatch')
        if physical:
            r=record['result']
            if file_digest(r['trajectory_path'])!=r['trajectory_sha256']:raise ValueError('Replay trace changed')
        return record['result']


class NoExecution:
    def run(self,**kwargs):raise RuntimeError('Offline audit must never execute physical calls')
    def propose(self,*args):raise RuntimeError('Offline audit must never call a model')


def audit_model_calls(root,package,source):
    path=root/'model_calls.jsonl';calls=[json.loads(l) for l in path.read_text().splitlines()] if path.exists() else []
    proposals=[json.loads(f.read_text()) for f in sorted((root/'stages/source/journal/proposals').glob('[0-9]*.json'))]
    if len(proposals)!=5:raise ValueError('Source proposer budget mismatch')
    if package['learner']=='random_search_v1' and calls:raise ValueError('Random baseline made model calls')
    candidates=[json.loads(l)['skill'] for l in (source/'candidates.jsonl').read_text().splitlines()]
    episodes=[EpisodeResult.model_validate_json(l) for l in (source/'episode_results.jsonl').read_text().splitlines()]
    histories=[];expected_requests=[]
    for i in range(6):
        if i:
            # Read-only source replay separately verifies the incumbent selection.
            request=proposals[i-1]['request'];expected_requests.append(request)
            if digest(request['history'])!=digest(histories):raise ValueError('Proposer received feedback outside prior source exploration')
        rows=[r for r in episodes if r.phase=='exploration' and r.candidate_index==i]
        histories.append(dict(skill=candidates[i],feedback=[r.public_feedback() for r in rows]))
    prompt_match=[]
    for call in calls:
        messages=call['prompt']
        if len(messages) not in (2,3) or messages[0]['role']!='system' or messages[1]['role']!='user':
            raise ValueError('Unexpected LLM message structure')
        content=json.loads(messages[1]['content'])
        matching=[]
        for index,request in enumerate(expected_requests):
            h=request['history'];given=content['history']
            suffix=(given==h[-len(given):]) if given else True
            if content['incumbent']==request['incumbent'] and suffix:matching.append(index)
        if not matching or set(content)!= {'incumbent','history','schema'}:raise ValueError('LLM feedback leakage or unrecognized context')
        initial=SkillSpec.initial();schema=SkillSpec.model_json_schema()
        schema['properties']['controller_family']={'const':initial.controller_family}
        if (messages[0]['content']!=PROMPT+canonical(bounds_for(initial)) or content['schema']!=schema or
            (len(messages)==3 and messages[2]!=dict(role='user',content='Previous output invalid. Return complete JSON matching schema.'))):
            raise ValueError('Unrecognized model system/schema/repair instructions')
        if (call['prompt_hash']!=digest(messages) or call['input_estimated_upper_bound']!=len(canonical(messages).encode()) or
            sum(len(message['content'].encode()) for message in messages)>6000):
            raise ValueError('LLM prompt integrity/budget mismatch')
        if call['model']!='k3' or call['temperature']!=1 or call['reasoning_effort']!='low':raise ValueError('Model configuration changed')
        if call['response_model'] not in ('k3',None):raise ValueError('Unexpected response model alias')
        if call['valid']:
            skill=SkillSpec.model_validate_json(call['response_text'])
            if skill.controller_family!='grasp_lift_state_v2':raise ValueError('Model changed controller')
        prompt_match.append(matching)
    if len(calls)>10:raise ValueError('Model call budget exceeded')
    if package['learner']=='bounded_llm_v1':
        cursor=0
        for i,proposal in enumerate(proposals):
            details=proposal['result']['details'];used=[]
            for attempt in range(2):
                if cursor>=len(calls):raise ValueError('Missing billed/attempted model call')
                call=calls[cursor]
                if i not in prompt_match[cursor] or call['attempt']!=attempt:raise ValueError('Model call belongs to wrong source proposal')
                used.append(call);cursor+=1
                if call['valid']:break
            if used[-1]['valid']:
                if details!=used[-1] or digest(proposal['result']['skill'])!=digest(json.loads(used[-1]['response_text'])):
                    raise ValueError('Source skill differs from actual valid model response')
            elif (len(used)!=2 or not details.get('fallback') or
                  digest(proposal['result']['skill'])!=digest(proposal['request']['incumbent'])):
                raise ValueError('Unrecorded model fallback')
        if cursor!=len(calls):raise ValueError('Unassigned or duplicate model calls')
    return dict(actual_requests=len(calls),valid_outputs=sum(c['valid'] for c in calls),
        error_requests=sum(c['error'] is not None for c in calls),usage_missing_requests=sum(c.get('usage') is None for c in calls),request_wall_time_s=sum(c['wall_time_s'] for c in calls),
        usage={key:sum((c.get('usage') or {}).get(key,0) for c in calls) for key in ('prompt_tokens','completion_tokens','total_tokens')},
        response_models=sorted({c['response_model'] for c in calls if c['response_model']}),
        prompt_source_only_verified=True,source_history_matching_indices=prompt_match,
        model_log_sha256=file_digest(path) if path.exists() else None,
        immutable_model_revision_available=False)


def audit(study,output,replay_root):
    p,m=verify(study);report=json.loads((study/'report.json').read_text())
    if report['status']!='DEVELOPMENT_LEARNING_EXECUTION_COMPLETE' or report['plan_hash']!=p['plan_hash'] or report['unresolved_calls']:
        raise ValueError('Incomplete learning execution')
    if replay_root.exists() or output.exists():raise ValueError('Retain previous audit output/projection')
    replay_root.mkdir(parents=True)
    config=load_pose_window_config(ROOT/'configs/measurement/pose_path_candidate_v1.yaml')
    packages=[];cases=[];evidence={};costs=dict(known_complete_physical_calls=0,observed_sim_time_s=0.,episode_wall_time_s=0.)
    for package in p['packages']:
        root=study/'packages'/package['package_id'];identity=dict(plan_hash=p['plan_hash'],package=package)
        completed={};stage_results={};stage_paths={}
        for name,body,expected in [('source',package['source'],20),('source_audit',package['source'],8),('target_zero',package['target'],8)]:
            base=root/'stages'/name;cp_path=base/'complete.json';checkpoint=json.loads(cp_path.read_text())
            if checkpoint['identity']!=identity:raise ValueError('Stage checkpoint identity mismatch')
            for path,h in checkpoint['files'].items():
                if file_digest(path)!=h:raise ValueError('Stage projection or physical evidence changed')
                evidence[path]=h
            attempt=Path(checkpoint['output']);stage_paths[name]=attempt
            seal=json.loads((attempt/'native_evidence_manifest.json').read_text())
            if seal['physical_calls']!=expected:raise ValueError('Native sealed stage count mismatch')
            for path,h in seal['files'].items():
                if file_digest(path)!=h:raise ValueError('Sealed native evidence changed')
                evidence[path]=h
            journal=base/'journal/physical';readonly=ReadOnlyJournal(journal,identity)
            records=sorted(journal.glob('[0-9]*.json'))
            if len(records)!=expected:raise ValueError('Unexpected physical journal coverage')
            projected=[EpisodeResult.model_validate_json(l) for l in (attempt/'episode_results.jsonl').read_text().splitlines()]
            stage_results[name]=[]
            for index,path in enumerate(records):
                rec=json.loads(path.read_text());request=rec['request'];cached=readonly.call(request,None,physical=True)
                r=EpisodeResult.model_validate(cached)
                if r!=projected[index] or r.backend!='physx' or r.infra_failure is not None or r.attempt_index!=0:
                    raise ValueError('Projection/native journal mismatch or unexpected retry')
                if request['condition'] not in m[r.split] or request['condition']['condition_id']!=r.condition_id:
                    raise ValueError('Physical call used an undeclared condition')
                if (request['phase']!=r.phase or request['candidate_index']!=r.candidate_index or request['attempt_index']!=r.attempt_index
                    or SkillSpec.model_validate(request['skill']).semantic_hash!=r.skill_hash):raise ValueError('Physical request/result identity mismatch')
                raw_dir=root/'trajectories'/name/r.episode_id
                raw_path=raw_dir.parent/(r.episode_id+'_native.json');raw=json.loads(raw_path.read_text())
                binding_path=raw_dir.parent/(r.episode_id+'_binding.json');binding=json.loads(binding_path.read_text())
                if (binding!=dict(episode_id=r.episode_id,body=body,plan_hash=p['plan_hash'],request=request,request_hash=digest(request))
                    or raw['binding_sha256']!=file_digest(binding_path) or raw['binding_path']!=str(binding_path)):
                    raise ValueError('Native request binding mismatch')
                validate_raw(raw,body,request['condition'],r.episode_id)
                if not configuration_matches(raw['solver_readback'],p['physics']):raise ValueError('Solver configuration mismatch')
                control=raw_dir/'control_trace.jsonl';physics=raw_dir/'physics_trace.jsonl'
                cr=[json.loads(l) for l in control.read_text().splitlines()];pr=[json.loads(l) for l in physics.read_text().splitlines()]
                for a,b in zip(cr[1:],pr[3::4],strict=True):
                    aa=dict(a['observation']);bb=dict(b['observation']);aa.pop('episode_id',None);bb.pop('episode_id',None)
                    if aa!=bb:raise ValueError('Shared tick observations differ')
                if any(row['observation']['object_size_m']!=request['condition']['size_m'] for row in cr+pr):
                    raise ValueError('Geometry observation mismatch')
                clock=trace_clock_summary([row['observation']['sim_time_s'] for row in cr],[row['observation']['sim_time_s'] for row in pr],r.sim_time_s,raw['physics_samples'])
                safety=bool(raw['terminal']['result']['constraint_violations'])
                if not clock['clocks_verified'] or not (clock['full_horizon'] or safety):raise ValueError('Unexplained truncation')
                if r.simulator_steps!=raw['physics_steps'] or r.simulator_steps!=raw['physics_samples'] or abs(r.sim_time_s-.005*r.simulator_steps)>1e-9:
                    raise ValueError('Physical clock/cost mismatch')
                outcomes={key:replay(path,config,raw['effective_joint_limits'],native=native)['terminal'] for key,path,native in
                    [('candidate_50hz',control,False),('candidate_200hz',physics,False),('native_50hz',control,True)]}
                if any(outcomes[k]!=raw[k] for k in outcomes):raise ValueError('Native/offline score mismatch')
                score=outcomes[p['primary_score']]
                for key in ('task_success','constraint_violations','max_lift_m','completion_time_s','hold_time_s','termination_reason'):
                    value=getattr(r,key);expected_value=tuple(score[key]) if key=='constraint_violations' else score[key]
                    if value!=expected_value:raise ValueError('Training result not derived from predeclared primary score')
                if r.wall_time_s!=raw['episode_wall_time_s']:raise ValueError('Episode wall cost mismatch')
                if r.episode_id in completed:raise ValueError('Duplicate physical episode ID')
                completed[r.episode_id]=raw_dir;stage_results[name].append(r)
                cases.append(dict(package_id=package['package_id'],stage=name,body=body,episode_id=r.episode_id,condition_id=r.condition_id,
                    stratum=request['condition']['name'],phase=r.phase,candidate_index=r.candidate_index,skill_hash=r.skill_hash,
                    outcomes=outcomes,clocks=clock,safety_stop=safety,macro_motion=motion_summary(cr,pr,'nominal'),
                    executor_stage_counts={v:sum(row.get('executor_stage')==v for row in cr) for v in sorted({row['executor_stage'] for row in cr if 'executor_stage' in row})}))
                costs['known_complete_physical_calls']+=1;costs['observed_sim_time_s']+=r.sim_time_s;costs['episode_wall_time_s']+=r.wall_time_s
                evidence[str(path)]=file_digest(path)
            evidence[str(cp_path)]=file_digest(cp_path)
        source=stage_paths['source'];before=SkillSpec.model_validate_json((source/'before.json').read_text());after=SkillSpec.model_validate_json((source/'after.json').read_text())
        if before.model_dump()!=p['initial_skill']:raise ValueError('Initial skill weakened or changed')
        expected_freeze=dict(before_hash=before.semantic_hash,after_hash=after.semantic_hash,source_output=str(source),
            source_after_sha256=file_digest(source/'after.json'),selection_sha256=file_digest(source/'selection.json'),
            native_manifest_sha256=file_digest(source/'native_evidence_manifest.json'))
        if json.loads((root/'artifact_freeze.json').read_text())!=expected_freeze:raise ValueError('Post-learning artifact freeze mismatch')
        replay_dir=replay_root/package['package_id']
        proposer=RandomSearch if package['learner']=='random_search_v1' else lambda seed:NoExecution()
        # Re-run the unchanged learning algorithm against read-only source journals.
        physical=ReadOnlyJournal(root/'stages/source/journal/physical',identity)
        proposals=ReadOnlyJournal(root/'stages/source/journal/proposals',identity)
        replayed=learn(before,20,m['source_train'],m['source_validation'],replay_factory(proposals,proposer),package['proposal_seed'],
            ReplayRunner(physical,NoExecution()),replay_dir)
        if replayed!=after or reconstruct(source)!=reconstruct(replay_dir):raise ValueError('Source learning reconstruction mismatch')
        if physical.index!=20 or proposals.index!=5:raise ValueError('Source replay budget mismatch')
        paired_summary={};null_repeats=[]
        for name,split,phase in [('source_audit','source_audit','source_audit'),('target_zero','target_test','evaluation')]:
            results=stage_results[name];rows=json.loads((stage_paths[name]/'paired_results.json').read_text());summary=json.loads((stage_paths[name]/'summary.json').read_text())
            if len(rows)!=4 or len(results)!=8:raise ValueError('Paired condition coverage mismatch')
            for index,c in enumerate(m[split]):
                a,b=results[2*index:2*index+2]
                if (a.condition_id!=c['condition_id'] or b.condition_id!=c['condition_id'] or a.split!=split or b.split!=split or
                    a.phase!=phase or b.phase!=phase or a.skill_hash!=before.semantic_hash or b.skill_hash!=after.semantic_hash or
                    rows[index]!=dict(condition_id=c['condition_id'],stratum=c['name'],before=a.model_dump(mode='json'),after=b.model_dump(mode='json'))):
                    raise ValueError('Before/after split, artifact or ordering mismatch')
                if before.semantic_hash==after.semantic_hash:
                    null_repeats.append(dict(stage=name,condition_id=c['condition_id'],
                        control=compare_traces(completed[a.episode_id]/'control_trace.jsonl',completed[b.episode_id]/'control_trace.jsonl',actions=True),
                        physics=compare_traces(completed[a.episode_id]/'physics_trace.jsonl',completed[b.episode_id]/'physics_trace.jsonl',actions=False)))
            expected_summary=dict(pairs=4,before_successes=sum(r.task_success for r in results[::2]),after_successes=sum(r.task_success for r in results[1::2]),
                delta_new=sum(int(b.task_success)-int(a.task_success) for a,b in zip(results[::2],results[1::2]))/4)
            if summary!=expected_summary:raise ValueError('Paired summary mismatch')
            strata={family:dict(pairs=sum(c['name']==family for c in m[split]),
                before_successes=sum(a.task_success for c,a in zip(m[split],results[::2]) if c['name']==family),
                after_successes=sum(b.task_success for c,b in zip(m[split],results[1::2]) if c['name']==family)) for family in ('tall_narrow','wide')}
            paired_summary[name]={**summary,'strata':strata,'wins':sum(not a.task_success and b.task_success for a,b in zip(results[::2],results[1::2])),
                'losses':sum(a.task_success and not b.task_success for a,b in zip(results[::2],results[1::2]))}
        model=audit_model_calls(root,package,source)
        packages.append(dict(package=package,source_selection=json.loads((source/'selection.json').read_text()),
            before_skill=before.model_dump(),after_skill=after.model_dump(),artifact_freeze=expected_freeze,source_reconstruction_passed=True,
            source_budget=json.loads((source/'costs.json').read_text()),paired=paired_summary,null_repeats=null_repeats,model_calls=model))
    if costs!=report['costs'] or costs['known_complete_physical_calls']!=72:raise ValueError('Whole-study physical cost mismatch')
    result=dict(status='GEOMETRY_LEARNING_TRACE_AUDIT_PASSED',formal_result_eligible=False,plan_hash=p['plan_hash'],
        private_manifest_canonical_sha256=p['manifest_sha256'],packages=packages,cases=cases,costs=costs,
        source_report_sha256=file_digest(study/'report.json'),evidence_files=evidence,
        score_recomputation_count=3*len(cases),rate_disagreements=sum(c['outcomes']['candidate_50hz']['task_success']!=c['outcomes']['candidate_200hz']['task_success'] for c in cases),
        auditor_sha256=file_digest(__file__),limitations=[p['interpretation'],p['environment_scope'],
            'One direction, two learners and one source-learning seed; no population significance or method superiority inference.',
            'Offline reuse of judges and learner code checks retained-record consistency; not an independent physical oracle.',
            'Source and target exact conditions withheld from learner, not an adversarial filesystem sandbox.',
            'New task explicitly uses experimental candidate 50 Hz score; old default and old results remain unchanged.'])
    write_json(output,result);return result


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--study',type=Path,required=True);ap.add_argument('--output',type=Path,required=True)
    ap.add_argument('--replay-root',type=Path,required=True);a=ap.parse_args();r=audit(a.study.resolve(),a.output.resolve(),a.replay_root.resolve())
    print(json.dumps(dict(status=r['status'],physical_calls=r['costs']['known_complete_physical_calls'],score_recomputation_count=r['score_recomputation_count'])))
