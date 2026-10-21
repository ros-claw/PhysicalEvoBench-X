"""Pair-level evaluation retries preserve both original sides and all costs."""
from ..core.hashing import append_json, write_json


def paired_evaluate(before, after, conditions, runner_factory, output, *, equivalent=False, phase='evaluation'):
    if equivalent and before.semantic_hash != after.semantic_hash:
        raise ValueError('Cannot alias different execution semantics')
    if not conditions or len({c['condition_id'] for c in conditions}) != len(conditions):
        raise ValueError('Expected nonempty unique paired conditions')
    if any(c.get('split') not in ('target_test','source_audit') for c in conditions):
        raise ValueError('Paired evaluation requires held-out conditions')
    from pathlib import Path
    output = Path(output)
    output.mkdir(parents=True,exist_ok=False)
    results, aliases = [], []
    runners = [runner_factory('before'),runner_factory('after')] if not equivalent else [runner_factory('before')]
    for condition in conditions:
        for attempt in range(2):
            pair = [runners[0].run(skill=before,condition=condition,phase=phase,candidate_index=0,attempt_index=attempt)]
            if not equivalent:
                pair.append(runners[1].run(skill=after,condition=condition,phase=phase,candidate_index=0,attempt_index=attempt))
            for r in pair:
                append_json(output/'episode_results.jsonl',r)
            valid = all(not r.infra_failure for r in pair)
            append_json(output/'pair_attempts.jsonl',dict(condition_id=condition['condition_id'],attempt_index=attempt,
                episode_ids=[r.episode_id for r in pair],included=valid))
            if valid:
                if equivalent:
                    aliases.append(dict(condition_id=condition['condition_id'],alias_of=pair[0].episode_id,
                                        reason='IDENTICAL_EXECUTION_AND_INFORMATION'))
                    pair.append(pair[0])
                results.append(pair)
                break
            if attempt == 1:
                write_json(output/'status.json',dict(status='INCOMPLETE',failed_condition=condition['condition_id']))
                raise RuntimeError('INCOMPLETE: paired evaluation retry failed')
    write_json(output/'aliases.json',aliases)
    write_json(output/'status.json',dict(status='COMPLETE',valid_pairs=len(results)))
    return results
