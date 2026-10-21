from ..core.hashing import append_json


def evaluate(skill, conditions, runner, output):
    """Frozen artifact, fresh executor per episode; no proposer argument exists."""
    if any(c.get('split') not in ('target_test','source_audit') for c in conditions):
        raise ValueError('Evaluation requires held-out conditions')
    records = []
    seen = set()
    for condition in conditions:
        if condition['condition_id'] in seen:
            raise ValueError('Duplicate test condition')
        seen.add(condition['condition_id'])
        r = runner.run(skill=skill, condition=condition, phase='evaluation', candidate_index=0, attempt_index=0)
        if r.skill_hash != skill.semantic_hash or r.condition_id != condition['condition_id']:
            raise ValueError('Evaluation identity mismatch')
        append_json(output, r)
        records.append(r)
        if r.infra_failure:
            raise RuntimeError('INCOMPLETE: paired orchestration required for evaluation retries')
    return records
