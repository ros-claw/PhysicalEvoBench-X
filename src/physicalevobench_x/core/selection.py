from statistics import median


def rank(results, index):
    if not results or any(r.infra_failure for r in results):
        raise ValueError('Selection requires complete valid observations')
    return (-sum(bool(r.constraint_violations) for r in results),
            sum(r.task_success for r in results),
            round(sum(min(r.max_lift_m/.08, 1) for r in results)/len(results), 6),
            -round(sum(r.completion_time_s if r.task_success else 15 for r in results)/len(results), 6),
            -index)


def select(candidates):
    return max(range(len(candidates)), key=lambda i: rank(candidates[i], i))


def accept(before_skill, candidate_skill, before, candidate):
    if before_skill.semantic_hash == candidate_skill.semantic_hash:
        return False, 'NO_BEHAVIOR_CHANGE'
    if len(before) != len(candidate) or [r.condition_id for r in before] != [r.condition_id for r in candidate]:
        raise ValueError('Validation must be paired')
    if any(r.infra_failure for r in before + candidate):
        raise ValueError('Invalid validation')
    if sum(bool(r.constraint_violations) for r in candidate) > sum(bool(r.constraint_violations) for r in before):
        return False, 'CONSTRAINT_REGRESSION'
    s0, s1 = sum(r.task_success for r in before), sum(r.task_success for r in candidate)
    if s1 > s0:
        return True, 'success'
    failures0 = {r.condition_id for r in before if not r.task_success}
    failures1 = {r.condition_id for r in candidate if not r.task_success}
    if s0 == s1 and s0 > 0 and failures0 == failures1:
        t0 = median(r.completion_time_s for r in before if r.task_success)
        t1 = median(r.completion_time_s for r in candidate if r.task_success)
        if t0 > 0 and t1 <= .95*t0:
            return True, 'time'
    return False, 'ROLLBACK'
