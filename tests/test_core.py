import json
import math
import pytest
from pydantic import ValidationError
from physicalevobench_x.core.schemas import SkillSpec, BOUNDS
from physicalevobench_x.core.hashing import digest
from physicalevobench_x.core.conditions import generate
from physicalevobench_x.core.aliasing import adaptation_identity
from physicalevobench_x.learners.random_search import RandomSearch


@pytest.mark.parametrize('field', list(BOUNDS))
@pytest.mark.parametrize('bad', [float('nan'), float('inf'), -1., 100., '0.5', True])
def test_reject_invalid_parameters(field, bad):
    data = SkillSpec.initial().model_dump()
    data['parameters'][field] = bad
    with pytest.raises(ValidationError):
        SkillSpec.model_validate(data)


def test_complete_exact_schema():
    data = SkillSpec.initial().model_dump()
    assert SkillSpec.model_validate_json(json.dumps(data)) == SkillSpec.initial()
    data['parameters']['code'] = 'import os'
    with pytest.raises(ValidationError):
        SkillSpec.model_validate(data)
    del data['parameters']['code']
    del data['requirements']
    with pytest.raises(ValidationError):
        SkillSpec.model_validate(data)
    assert digest({'b':2,'a':1}) == digest({'a':1,'b':2})


def test_conditions_replay_and_disjoint():
    manifests = generate(11, dict(source_train=2, source_validation=4, target_test=50))
    assert manifests == generate(11, dict(source_train=2, source_validation=4, target_test=50))
    ids = [c['condition_id'] for v in manifests.values() for c in v]
    assert len(set(ids)) == len(ids)
    assert manifests['target_test'] == generate(11, dict(target_test=50))['target_test']


def test_random_replay_and_independent_dimensions():
    a, b = RandomSearch(1), RandomSearch(1)
    initial = SkillSpec.initial()
    for _ in range(200):
        assert a.propose(initial, []) == b.propose(initial, [])
    raw = list(a.proposals[0]['raw_normalized'].values())
    assert len(set(raw)) == 5


def test_alias_context_and_seed_are_part_of_identity():
    kw = dict(run_seed_id=1, embodiment='franka_robotiq', controller_hash='a', adapter_hash='b',
        proposer_config={'model':'x'}, public_context={}, rng_seed=20, budget=5,
        train_conditions_hash='c', validation_conditions_hash='d')
    identity = adaptation_identity(SkillSpec.initial(), **kw)
    assert identity == adaptation_identity(SkillSpec.initial(), **kw)
    for key, value in [('run_seed_id',2),('budget',20),('public_context',{'hint':True}),('rng_seed',21)]:
        assert identity != adaptation_identity(SkillSpec.initial(), **(kw | {key:value}))
