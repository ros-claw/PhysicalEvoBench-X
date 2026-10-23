"""Common source/target algorithm. Each invocation owns a fresh proposer and ledger."""
from pathlib import Path
from ..core.budget import BudgetLedger
from ..core.hashing import write_json, append_json
from ..core.schemas import SkillSpec, EpisodeResult
from ..core.selection import select, accept


SCHEDULE = {0: (0, 0, 0), 5: (1, 1, 2), 20: (2, 4, 5)}


def learn(initial, budget, train, validation, proposer_factory, seed, runner, output):
    if budget not in SCHEDULE:
        raise ValueError('Only 0/5/20 supported')
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    write_json(output/'before.json', initial)
    ntrain, nval, nproposals = SCHEDULE[budget]
    if len(train) != ntrain or len(validation) != nval:
        raise ValueError('Wrong condition counts')
    if budget:
        train_split = train[0].get('split')
        if train_split not in ('source_train', 'target_train'):
            raise ValueError('Training conditions must come from a training split')
        expected_validation = train_split.replace('_train', '_validation')
        if any(c.get('split') != train_split for c in train) or any(c.get('split') != expected_validation for c in validation):
            raise ValueError('Training/validation split mismatch')
    ids = [c['condition_id'] for c in train+validation]
    if len(ids) != len(set(ids)):
        raise ValueError('Overlapping train/validation conditions')
    ledger = BudgetLedger((nproposals+1)*ntrain if budget else 0, 2*nval)
    write_json(output/'costs.json', ledger.snapshot())
    if budget == 0:
        write_json(output/'after.json', initial)
        write_json(output/'selection.json', dict(selected_index=0, accepted_update=False, reason='ZERO_BUDGET'))
        return initial
    proposer = proposer_factory(seed) # fresh RNG and model context, including each target budget
    skills, observations, history = [initial], [], []

    def execute(skill, conditions, phase, index):
        results = []
        for condition in conditions:
            ledger.require_room(phase)
            for attempt in range(2):
                r = runner.run(skill=skill, condition=condition, phase=phase,
                               candidate_index=index, attempt_index=attempt)
                if (r.condition_id != condition['condition_id'] or r.split != condition['split'] or r.skill_hash != skill.semantic_hash
                    or r.phase != phase or r.candidate_index != index or r.attempt_index != attempt):
                    write_json(output/'protocol_error.json',dict(reason='RESULT_IDENTITY_MISMATCH',result=r.model_dump()))
                    invalid=r.model_copy(update={'infra_failure':'RESULT_IDENTITY_MISMATCH'})
                    ledger.record(invalid)
                    append_json(output/'episode_results.jsonl',invalid)
                    write_json(output/'costs.json',ledger.snapshot())
                    raise ValueError('Runner returned mismatched identity')
                ledger.record(r)
                append_json(output/'episode_results.jsonl', r)
                write_json(output/'costs.json', ledger.snapshot())
                if not r.infra_failure:
                    results.append(r)
                    break
                if attempt == 1:
                    raise RuntimeError('INCOMPLETE: second infrastructure attempt failed')
                ledger.retry()
            else:
                raise RuntimeError('INCOMPLETE')
        return results

    for index in range(nproposals+1):
        if index:
            incumbent = skills[select(observations)]
            request = dict(incumbent=incumbent.model_dump(), history=list(history))
            append_json(output/'proposal_requests.jsonl', request)
            try:
                candidate = SkillSpec.model_validate(proposer.propose(incumbent, list(history)))
                if candidate.controller_family != initial.controller_family:
                    raise ValueError('Learner cannot change the fixed controller family')
                proposal_error = None
            except (ValueError, TimeoutError) as exc:
                candidate, proposal_error = incumbent, type(exc).__name__
            skills.append(candidate)
            append_json(output/'proposal_responses.jsonl', dict(skill=candidate.model_dump(), error=proposal_error,
                details=proposer.proposals[-1] if getattr(proposer, 'proposals', None) else None))
        # This log is written BEFORE any physical episode; supports deterministic reconstruction.
        append_json(output/'candidates.jsonl', dict(candidate_index=index, skill=skills[index].model_dump()))
        results = execute(skills[index], train, 'exploration', index)
        observations.append(results)
        history.append(dict(skill=skills[index].model_dump(), feedback=[r.public_feedback() for r in results]))
    selected = select(observations)
    before_results = execute(initial, validation, 'validation', 0)
    selected_results = execute(skills[selected], validation, 'validation', selected)
    accepted, reason = accept(initial, skills[selected], before_results, selected_results)
    after = skills[selected] if accepted else initial
    write_json(output/'selection.json', dict(selected_index=selected, accepted_update=accepted, reason=reason,
        validation_before=[r.episode_id for r in before_results],
        validation_candidate=[r.episode_id for r in selected_results]))
    write_json(output/'after.json', after)
    write_json(output/'costs.json', ledger.snapshot())
    return after


def reconstruct(path):
    import json
    path = Path(path)
    before = SkillSpec.model_validate_json((path/'before.json').read_text())
    expected = SkillSpec.model_validate_json((path/'after.json').read_text())
    costs = json.loads((path/'costs.json').read_text())
    if not (path/'candidates.jsonl').exists():
        if costs['budget_charged_episodes'] != 0 or before != expected:
            raise ValueError('Invalid zero-budget reconstruction')
        return dict(skill=before.model_dump(),selected_index=0,accepted_update=False,reason='ZERO_BUDGET')
    candidate_rows = [json.loads(line) for line in (path/'candidates.jsonl').read_text().splitlines()]
    if [r['candidate_index'] for r in candidate_rows] != list(range(len(candidate_rows))):
        raise ValueError('Invalid candidate index sequence')
    candidates = [SkillSpec.model_validate(row['skill']) for row in candidate_rows]
    if candidates[0] != before:
        raise ValueError('Original before artifact mismatch')
    if any(c.controller_family != before.controller_family for c in candidates):
        raise ValueError('Candidate changed fixed controller')
    records = [EpisodeResult.model_validate_json(line) for line in (path/'episode_results.jsonl').read_text().splitlines()]
    valid = [r for r in records if not r.infra_failure]
    groups = [[r for r in valid if r.phase == 'exploration' and r.candidate_index == i] for i in range(len(candidates))]
    if len(candidates) not in (3, 6) or any(len(g) != (1 if len(candidates)==3 else 2) for g in groups):
        raise ValueError('Incomplete exploration log')
    train_ids = [r.condition_id for r in groups[0]]
    if len(set(train_ids)) != len(train_ids) or any([r.condition_id for r in group] != train_ids for group in groups):
        raise ValueError('Exploration condition pairing mismatch')
    selected = select(groups)
    vals = [r for r in valid if r.phase == 'validation']
    n = 1 if len(candidates)==3 else 4
    if len(vals) != 2*n:
        raise ValueError('Incomplete validation log')
    validation_ids = [r.condition_id for r in vals[:n]]
    if (len(set(validation_ids)) != n or [r.condition_id for r in vals[n:]] != validation_ids
        or set(train_ids) & set(validation_ids)):
        raise ValueError('Validation condition pairing/overlap mismatch')
    if (len({r.episode_id for r in records}) != len(records)
        or len(valid) != (5 if n==1 else 20)
        or costs['physical_episode_executions'] != len(records)
        or costs['budget_charged_episodes'] != len(valid)
        or costs['infra_retries'] > 2
        or abs(costs['sim_time_s']-sum(r.sim_time_s for r in records)) > 1e-6):
        raise ValueError('Execution/cost ledger mismatch')
    for i, group in enumerate(groups):
        if any(r.skill_hash != candidates[i].semantic_hash for r in group):
            raise ValueError('Candidate hash mismatch')
    if any(r.skill_hash != candidates[0].semantic_hash for r in vals[:n]) or any(r.skill_hash != candidates[selected].semantic_hash for r in vals[n:]):
        raise ValueError('Validation hash mismatch')
    accepted, reason = accept(candidates[0], candidates[selected], vals[:n], vals[n:])
    result = candidates[selected] if accepted else candidates[0]
    if result.semantic_hash != expected.semantic_hash:
        raise ValueError('Reconstruction mismatch')
    return dict(skill=result.model_dump(), selected_index=selected, accepted_update=accepted, reason=reason)
