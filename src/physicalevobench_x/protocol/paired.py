"""Pair-level evaluation retries preserve both original sides and all costs."""
from ..core.hashing import append_json, write_json


def paired_evaluate(before, after, conditions, runner_factory, output, *, equivalent=False, phase='evaluation'):
    if equivalent and before.semantic_hash != after.semantic_hash:
        raise ValueError('Cannot alias different execution semantics')
    if not conditions or len({c['condition_id'] for c in conditions}) != len(conditions):
        raise ValueError('Expected nonempty unique paired conditions')
    if any(c.get('split') not in ('target_test','source_audit') for c in conditions):
        raise ValueError('Paired evaluation requires held-out conditions')
    expected_split='source_audit' if phase=='source_audit' else 'target_test' if phase=='evaluation' else None
    if expected_split is None or any(c['split']!=expected_split for c in conditions):
        raise ValueError('Paired evaluation phase/split mismatch')
    from pathlib import Path
    output = Path(output)
    output.mkdir(parents=True,exist_ok=False)
    results, aliases, executions = [], [], []
    excluded=set()
    retries, logical = 0, 0
    def save_costs():
        write_json(output/'costs.json',dict(logical_episode_requests=logical,
            physical_episode_executions=len(executions),aliased_episode_requests=len(aliases),
            budget_charged_episodes=0,infra_retries=retries,
            excluded_pair_episode_executions=len(excluded),
            excluded_valid_pair_episode_executions=sum(r.episode_id in excluded and not r.infra_failure for r in executions),
            sim_time_s=sum(r.sim_time_s for r in executions),wall_time_s=sum(r.wall_time_s for r in executions)))
    runners = [runner_factory('before'),runner_factory('after')] if not equivalent else [runner_factory('before')]
    for condition in conditions:
        logical += 2
        for attempt in range(2):
            pair = [runners[0].run(skill=before,condition=condition,phase=phase,candidate_index=0,attempt_index=attempt)]
            if not equivalent:
                pair.append(runners[1].run(skill=after,condition=condition,phase=phase,candidate_index=0,attempt_index=attempt))
            for r in pair:
                append_json(output/'episode_results.jsonl',r)
                executions.append(r)
            save_costs()
            for r, skill in zip(pair,[before] if equivalent else [before,after]):
                if (r.condition_id!=condition['condition_id'] or r.split!=condition['split'] or r.skill_hash!=skill.semantic_hash
                    or r.phase!=phase or r.attempt_index!=attempt or r.candidate_index!=0):
                    write_json(output/'status.json',dict(status='INCOMPLETE',reason='RESULT_IDENTITY_MISMATCH'))
                    raise ValueError('Paired runner returned mismatched identity')
            valid = all(not r.infra_failure for r in pair)
            append_json(output/'pair_attempts.jsonl',dict(condition_id=condition['condition_id'],attempt_index=attempt,
                episode_ids=[r.episode_id for r in pair],included=valid))
            if not valid:
                excluded.update(r.episode_id for r in pair)
                save_costs()
            if valid:
                if equivalent:
                    aliases.append(dict(condition_id=condition['condition_id'],alias_of=pair[0].episode_id,
                                        reason='IDENTICAL_EXECUTION_AND_INFORMATION'))
                    pair.append(pair[0])
                results.append(pair)
                save_costs()
                break
            if attempt == 1:
                write_json(output/'status.json',dict(status='INCOMPLETE',failed_condition=condition['condition_id']))
                raise RuntimeError('INCOMPLETE: paired evaluation retry failed')
            if retries >= 2:
                write_json(output/'status.json',dict(status='INCOMPLETE',failed_condition=condition['condition_id']))
                raise RuntimeError('INCOMPLETE: paired evaluation retry limit reached')
            retries += 1
            save_costs()
    write_json(output/'aliases.json',aliases)
    write_json(output/'status.json',dict(status='COMPLETE',valid_pairs=len(results)))
    return results
