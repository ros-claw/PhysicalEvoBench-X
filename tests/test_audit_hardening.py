import json
import pytest
from physicalevobench_x.core.schemas import SkillSpec
from physicalevobench_x.core.conditions import generate
from physicalevobench_x.core.hashing import write_json
from physicalevobench_x.protocol.learning import learn, reconstruct
from physicalevobench_x.protocol.paired import paired_evaluate
from physicalevobench_x.learners.random_search import RandomSearch
from conftest import FakeRunner


def test_reconstruct_checks_original_before_and_paired_conditions(tmp_path):
    c=generate(1,dict(target_train=1,target_validation=1))
    out=tmp_path/'learning'
    learn(SkillSpec.initial(),5,c['target_train'],c['target_validation'],RandomSearch,2,FakeRunner(),out)
    write_json(out/'before.json',RandomSearch(9).propose(SkillSpec.initial(),[]))
    with pytest.raises(ValueError,match='before'):
        reconstruct(out)
    write_json(out/'before.json',SkillSpec.initial())
    records=[json.loads(line) for line in (out/'episode_results.jsonl').read_text().splitlines()]
    records[1]['condition_id']='incorrect-condition'
    (out/'episode_results.jsonl').write_text('\n'.join(json.dumps(r) for r in records)+'\n')
    with pytest.raises(ValueError,match='condition'):
        reconstruct(out)


def test_pair_retry_cap_is_global_and_failed_attempt_costs_survive(tmp_path):
    runner=FakeRunner(failures=[1,3,5])
    conditions=generate(1,dict(target_test=3))['target_test']
    with pytest.raises(RuntimeError,match='retry limit'):
        paired_evaluate(SkillSpec.initial(),SkillSpec.initial(),conditions,
            lambda side:runner,tmp_path/'pairs',equivalent=True)
    assert len(runner.requests)==5
    costs=json.loads((tmp_path/'pairs/costs.json').read_text())
    assert costs['physical_episode_executions']==5
    assert costs['infra_retries']==2
    assert costs['sim_time_s']==pytest.approx(.1)
    assert json.loads((tmp_path/'pairs/status.json').read_text())['status']=='INCOMPLETE'


def test_audit_phase_must_match_held_out_split(tmp_path):
    with pytest.raises(ValueError,match='phase'):
        paired_evaluate(SkillSpec.initial(),SkillSpec.initial(),generate(1,dict(target_test=1))['target_test'],
            lambda side:FakeRunner(),tmp_path/'bad',phase='source_audit')


def test_zero_budget_reconstruction_is_supported(tmp_path):
    out=tmp_path/'zero'
    learn(SkillSpec.initial(),0,[],[],RandomSearch,1,FakeRunner(),out)
    rebuilt=reconstruct(out)
    assert not rebuilt['accepted_update']
    assert rebuilt['reason']=='ZERO_BUDGET'
