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
                if (r.condition_id != condition['condition_id'] or r.skill_hash != skill.semantic_hash
                    or r.phase != phase or r.candidate_index != index or r.attempt_index != attempt):
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
    candidates = [SkillSpec.model_validate(json.loads(line)['skill'])
                  for line in (path/'candidates.jsonl').read_text().splitlines()]
    records = [EpisodeResult.model_validate_json(line) for line in (path/'episode_results.jsonl').read_text().splitlines()]
    valid = [r for r in records if not r.infra_failure]
    groups = [[r for r in valid if r.phase == 'exploration' and r.candidate_index == i] for i in range(len(candidates))]
    if len(candidates) not in (3, 6) or any(len(g) != (1 if len(candidates)==3 else 2) for g in groups):
        raise ValueError('Incomplete exploration log')
    selected = select(groups)
    vals = [r for r in valid if r.phase == 'validation']
    n = 1 if len(candidates)==3 else 4
    if len(vals) != 2*n:
        raise ValueError('Incomplete validation log')
    for i, group in enumerate(groups):
        if any(r.skill_hash != candidates[i].semantic_hash for r in group):
            raise ValueError('Candidate hash mismatch')
    if any(r.skill_hash != candidates[0].semantic_hash for r in vals[:n]) or any(r.skill_hash != candidates[selected].semantic_hash for r in vals[n:]):
        raise ValueError('Validation hash mismatch')
    accepted, reason = accept(candidates[0], candidates[selected], vals[:n], vals[n:])
    result = candidates[selected] if accepted else candidates[0]
    expected = SkillSpec.model_validate_json((path/'after.json').read_text())
    if result.semantic_hash != expected.semantic_hash:
        raise ValueError('Reconstruction mismatch')
    return dict(skill=result.model_dump(), selected_index=selected, accepted_update=accepted, reason=reason)
