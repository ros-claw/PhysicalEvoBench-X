"""Independent fail-closed audit of a finished frozen internal pilot.

Does not grant security isolation for untrusted external submissions.
"""
import argparse
from collections import Counter
import json
from pathlib import Path
from physicalevobench_x.core.hashing import digest, file_digest, write_json
from physicalevobench_x.core.schemas import SkillSpec, EpisodeResult
from physicalevobench_x.protocol.learning import reconstruct
from pilot_suite import execution_inputs


def require(condition, message):
    if not condition:
        raise ValueError(message)


def audit(suite, root):
    plan = json.loads((suite/'plan.json').read_text())
    require(plan['track']=='frozen_pilot', 'Development matrix cannot become a formal pilot retrospectively')
    require(plan['test_count']==50 and plan['budgets']==[0,5,20], 'Incomplete formal pilot dimensions')
    require(execution_inputs(root)==plan['execution_inputs'], 'Execution version changed')
    frozen = json.loads(Path(plan['freeze_path']).read_text())
    require(frozen['freeze_hash']==plan['freeze_hash']==digest({k:v for k,v in frozen.items() if k!='freeze_hash'}),
            'Invalid frozen lineage')
    for name, checksum in frozen['files'].items():
        require(file_digest(root/name)==checksum, 'Frozen input changed: '+name)
    for body,checksum in frozen['development_reviews'].items():
        require(file_digest(root/frozen['config']['development_validation_evidence'][body])==checksum,
                'Development range review changed')
    for path, checksum in frozen['gpu_evidence'].items():
        # Freeze's evidence map is keyed by check names; resolve through config.
        evidence_path=root/frozen['config']['gpu_evidence'][path]
        require(file_digest(evidence_path)==checksum, 'GPU attestation changed')
        evidence=json.loads(evidence_path.read_text())
        require(evidence.get('backend')=='physx' and evidence.get('status')=='GPU_VERIFIED'
            and evidence.get('frozen_inputs')==frozen['files'], 'Invalid GPU acceptance')
        for referenced, expected in evidence.get('evidence_files',{}).items():
            require(file_digest(referenced)==expected, 'GPU raw evidence changed')
    expected={(learner,body,seed) for learner in ('random_search_v1','bounded_llm_v1')
              for body in ('franka_panda','franka_robotiq') for seed in range(3)}
    actual={(p['learner'],p['source'],p['run_seed_id']) for p in plan['packages']}
    require(actual==expected and len(plan['packages'])==12, 'Both learners/directions/three seeds are required')
    all_ids, total, packages = set(), Counter(), []
    for info in plan['packages']:
        directory=suite/'packages'/info['package_id']
        summary=json.loads((directory/'summary.json').read_text())
        require(summary['package']==info, 'Package identity mismatch')
        manifest_path=Path(info['conditions_path'])
        require(file_digest(manifest_path)==info['conditions_sha256'], 'Split manifest changed')
        conditions=json.loads(manifest_path.read_text())
        require(all(len(conditions[key])==count for key,count in dict(source_train=2,source_validation=4,
            source_audit=50,target_train=2,target_validation=4,target_test=50).items()), 'Incomplete split counts')
        condition_map={c['condition_id']:c for values in conditions.values() for c in values}
        require(len(condition_map)==len([c for values in conditions.values() for c in values]), 'Overlapping split IDs')
        source_before=SkillSpec.initial()
        selected, physical = {}, []
        for checkpoint_path in directory.glob('stages/*/complete.json'):
            checkpoint=json.loads(checkpoint_path.read_text())
            require(checkpoint['identity']==dict(package=info,execution_inputs_hash=digest(plan['execution_inputs'])),
                    'Stage execution identity mismatch')
            path=Path(checkpoint['output'])
            require(path.resolve().is_relative_to(directory.resolve()), 'Stage path escapes package')
            for evidence, checksum in checkpoint['files'].items():
                require(Path(evidence).resolve().is_relative_to(directory.resolve()), 'Evidence escapes package')
                require(file_digest(evidence)==checksum, 'Stage evidence changed')
            selected[checkpoint_path.parent.name]=path
        require('source' in selected and 'source_audit' in selected, 'Missing complete source or audit')
        rebuilt=reconstruct(selected['source'])
        source_after=SkillSpec.model_validate(rebuilt['skill'])
        require(SkillSpec.model_validate_json((selected['source']/'before.json').read_text())==source_before,
                'Source initial artifact changed')
        require(rebuilt['accepted_update']==summary['source_selection']['accepted_update'], 'Source decision mismatch')
        for path in sorted(directory.glob('stages/*/journal/physical/[0-9]*.json')):
            entry=json.loads(path.read_text())
            require(entry['status']=='COMPLETE', 'Unresolved physical execution')
            request=entry['request']
            result=EpisodeResult.model_validate(entry['result'])
            require(result.backend=='physx', 'Fake backend is ineligible')
            require(entry['request_hash']==digest(request), 'Journal request changed')
            require(request['condition']==condition_map.get(result.condition_id), 'Executed condition differs from private manifest')
            require(result.skill_hash==SkillSpec.model_validate(request['skill']).semantic_hash, 'Executed skill mismatch')
            require(result.phase==request['phase'] and result.candidate_index==request['candidate_index']
                    and result.attempt_index==request['attempt_index'] and result.split==request['condition']['split'],
                    'Physical result identity mismatch')
            require(result.episode_id not in all_ids, 'Duplicate actual execution ID')
            all_ids.add(result.episode_id)
            if not result.infra_failure:
                require(result.trajectory_path and file_digest(result.trajectory_path)==result.trajectory_sha256,
                        'Trajectory missing or altered')
            physical.append((path.parents[2].name,request,result))
        # Selected attempts must account for every actual journaled execution exactly once.
        selected_results=[]
        for path in selected.values():
            rows=path/'episode_results.jsonl'
            if rows.exists():
                selected_results.extend(EpisodeResult.model_validate_json(line) for line in rows.read_text().splitlines())
        require({r.episode_id for r in selected_results}=={r.episode_id for _,_,r in physical}
                and len(selected_results)==len(physical), 'Selected stage evidence does not cover physical journal')
        excluded=set()
        for path in selected.values():
            attempts=path/'pair_attempts.jsonl'
            if attempts.exists():
                for line in attempts.read_text().splitlines():
                    entry=json.loads(line)
                    if not entry['included']:
                        excluded.update(entry['episode_ids'])
        def audit_pairs(name, before, after, split):
            require(name in selected, 'Missing paired stage: '+name)
            valid=[r for stage_name,_,r in physical if stage_name==name and not r.infra_failure and r.episode_id not in excluded]
            same=before.semantic_hash==after.semantic_hash
            expected_hashes=Counter([before.semantic_hash] if same else [before.semantic_hash,after.semantic_hash])
            for condition in conditions[split]:
                require(Counter(r.skill_hash for r in valid if r.condition_id==condition['condition_id'])==expected_hashes,
                        'Paired executions do not match frozen skills')
            n=len(conditions[split])
            require(len(valid)==n*(1 if same else 2),'Extra paired executions')
            b=sum(r.task_success for r in valid if r.skill_hash==before.semantic_hash)
            a=b if same else sum(r.task_success for r in valid if r.skill_hash==after.semantic_hash)
            expected=dict(pairs=n,before_successes=b,after_successes=a,delta_new=(a-b)/n,evaluation_aliased=same)
            actual=json.loads((selected[name]/'summary.json').read_text())
            require(actual==expected,'Paired summary arithmetic mismatch')
            attempts=[json.loads(line) for line in (selected[name]/'pair_attempts.jsonl').read_text().splitlines()]
            require(sum(row['attempt_index']==1 for row in attempts)<=2,'Paired retry limit exceeded')
            return expected
        require(audit_pairs('source_audit',source_before,source_after,'source_audit')==summary['source_audit'],
                'Source audit summary mismatch')
        expected_stage_names={'source','source_audit'}
        expected_aliases=[]
        expected_alias_count=50*int(source_before.semantic_hash==source_after.semantic_hash)
        for budget in (0,5,20):
            before_name=f'target_{budget}_before'
            expected_stage_names.add(before_name)
            if source_before.semantic_hash==source_after.semantic_hash:
                after_name=before_name
                expected_aliases.append((f'target_{budget}_after',before_name,budget))
            else:
                after_name=f'target_{budget}_after'
                expected_stage_names.add(after_name)
            target_skills=[]
            for name,input_skill in ((before_name,source_before),(after_name,source_after)):
                require(name in selected, 'Missing target adaptation')
                path=selected[name]
                require(SkillSpec.model_validate_json((path/'before.json').read_text())==input_skill,
                        'Target inherited an incorrect artifact')
                target_skills.append(SkillSpec.model_validate_json((path/'after.json').read_text()))
                if budget:
                    reconstruct(path)
                else:
                    require(target_skills[-1]==input_skill, 'Zero-budget artifact changed')
            evaluation_name=f'evaluation_{budget}'
            expected_stage_names.add(evaluation_name)
            require(evaluation_name in selected,'Missing target evaluation')
            pairs=audit_pairs(evaluation_name,*target_skills,'target_test')
            cell={**pairs,'budget':budget,'adaptation_aliased':source_before.semantic_hash==source_after.semantic_hash}
            require(cell==next(c for c in summary['cells'] if c['budget']==budget),'Reported target cell differs from actual tests')
            expected_alias_count+=50*int(pairs['evaluation_aliased'])
        require(set(selected)==expected_stage_names, 'Unexpected or missing stages')
        aliases=json.loads((directory/'aliases.json').read_text())
        require([(a['request'],a['alias_of'],a['aliased_episode_requests']) for a in aliases]==expected_aliases,
                'Target alias accounting mismatch')
        expected_alias_count+=sum(item[2] for item in expected_aliases)
        for path in directory.glob('model_calls/*.jsonl'):
            calls=[json.loads(line) for line in path.read_text().splitlines()]
            maximum=10 if path.stem=='source' or path.stem.startswith('target_20_') else 4 if path.stem.startswith('target_5_') else 0
            require(info['learner']=='bounded_llm_v1' and path.stem in selected and len(calls)<=maximum,
                    'Unplanned or excessive model requests')
            for call in calls:
                require(bool(call.get('requested_at_utc')),'Missing model request timestamp')
                require(call['rng_seed']==(info['source_proposal_seed'] if path.stem=='source' else info['target_proposal_seed']),
                        'Model proposal seed/context mismatch')
                require(call['model']=='k3' and call['temperature']==1 and call['reasoning_effort']=='low',
                        'Inconsistent model configuration')
                require(not call['valid'] or call.get('response_model')=='k3','Unexpected response model')
                usage=call.get('usage') or {}
                require(usage.get('prompt_tokens',0)<=6000 and usage.get('completion_tokens',0)<=800,
                        'Model token cap exceeded')
        costs=summary['costs']
        require(costs['logical_episode_requests']==470,'Wrong logical allocation')
        require(costs['physical_episode_executions']==len(physical), 'Actual cost mismatch')
        require(costs['aliased_episode_requests']==expected_alias_count,'Incorrect alias count')
        excluded_valid=sum(not r.infra_failure and r.episode_id in excluded for _,_,r in physical)
        require(costs['excluded_valid_pair_episode_executions']==excluded_valid,'Excluded paired cost mismatch')
        require(costs['logical_episode_requests']==sum(not r.infra_failure for _,_,r in physical)-excluded_valid
                +costs['aliased_episode_requests'], 'Alias/request accounting mismatch')
        require(abs(costs['sim_time_s']-sum(r.sim_time_s for _,_,r in physical))<1e-6,'Simulation cost mismatch')
        require(costs['budget_charged_episodes']==sum(r.phase in ('exploration','validation') and not r.infra_failure
                for _,_,r in physical),'Practice budget mismatch')
        for key in ('logical_episode_requests','physical_episode_executions','aliased_episode_requests','budget_charged_episodes'):
            total[key]+=costs[key]
        packages.append(info['package_id'])
    return dict(status='FROZEN_INTERNAL_PILOT_AUDIT_PASSED',formal_result_eligible=True,
        scope='Trusted internal learners; process allowlist, no malicious-code isolation claim',
        freeze_hash=plan['freeze_hash'],completed_packages=packages,costs=dict(total))


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--suite',type=Path,required=True)
    p.add_argument('--root',type=Path,default=Path.cwd())
    a=p.parse_args()
    try:
        result=audit(a.suite.resolve(),a.root.resolve())
    except (ValueError,OSError,KeyError) as exc:
        result=dict(status='AUDIT_FAILED',formal_result_eligible=False,reason=str(exc))
    write_json(a.suite/'independent_audit.json',result)
    print(json.dumps(result))
    raise SystemExit(0 if result['formal_result_eligible'] else 2)
