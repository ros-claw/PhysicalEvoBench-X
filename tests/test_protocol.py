import json
import pytest
from physicalevobench_x.core.schemas import SkillSpec
from physicalevobench_x.core.conditions import generate
from physicalevobench_x.protocol.learning import learn, reconstruct
from physicalevobench_x.protocol.evaluation import evaluate
from physicalevobench_x.learners.random_search import RandomSearch
from physicalevobench_x.core.selection import accept, select
from physicalevobench_x.learners.bounded_llm import BoundedLLM
from physicalevobench_x.reporting.validation import validate_run
from conftest import FakeRunner


@pytest.mark.parametrize('budget,ntrain,nval,ncandidates', [(5,1,1,3),(20,2,4,6)])
def test_budget_exact_reconstruct_tie_and_private_history(tmp_path, runner, budget,ntrain,nval,ncandidates):
    conditions = generate(1, dict(source_train=ntrain, source_validation=nval))
    contexts = []
    class Spy(RandomSearch):
        def propose(self, incumbent, history):
            contexts.append(history.copy())
            assert 'mass_kg' not in str(history)
            assert 'condition_id' not in str(history)
            assert len(history) < ncandidates
            return super().propose(incumbent,history)
    out = tmp_path/'source'
    result = learn(SkillSpec.initial(),budget,conditions['source_train'],conditions['source_validation'],Spy,3,runner,out)
    assert len(runner.requests) == budget
    assert result == SkillSpec.initial() # all outcomes tied: retain initial, not new experience
    costs = json.loads((out/'costs.json').read_text())
    assert costs['charged'] == {'exploration':ncandidates*ntrain, 'validation':nval*2}
    assert not reconstruct(out)['accepted_update']
    assert len(contexts) == ncandidates-1
    with pytest.raises(FileExistsError):
        learn(result,budget,conditions['source_train'],conditions['source_validation'],Spy,3,runner,out)


def test_budget_zero_never_constructs_proposer(tmp_path, runner):
    def forbidden(seed):
        raise AssertionError('b=0 must never call proposer')
    initial = SkillSpec.initial()
    assert learn(initial,0,[],[],forbidden,1,runner,tmp_path/'zero') == initial
    assert runner.requests == []


def test_retry_same_condition_candidate_and_ledger(tmp_path):
    c = generate(3,dict(target_train=1,target_validation=1))
    runner = FakeRunner(failures=[1])
    learn(SkillSpec.initial(),5,c['target_train'],c['target_validation'],RandomSearch,7,runner,tmp_path/'run')
    assert runner.requests[0][:4] == runner.requests[1][:4]
    assert len(runner.requests) == 6
    costs = json.loads((tmp_path/'run/costs.json').read_text())
    assert costs['budget_charged_episodes'] == 5
    assert costs['physical_episode_executions'] == 6
    assert costs['sim_time_s'] == pytest.approx(.12)


def test_infra_retry_limit_aborts_incomplete(tmp_path):
    c = generate(3,dict(target_train=1,target_validation=1))
    with pytest.raises(RuntimeError, match='INCOMPLETE'):
        learn(SkillSpec.initial(),5,c['target_train'],c['target_validation'],RandomSearch,7,
              FakeRunner(failures=[1,2]),tmp_path/'run')
    assert not (tmp_path/'run/after.json').exists()


def test_budgets_create_fresh_learner_and_evaluation_frozen(tmp_path, runner):
    c = generate(3,dict(target_train=2,target_validation=4,target_test=3))
    created = []
    def factory(seed):
        proposer = RandomSearch(seed)
        created.append(proposer)
        return proposer
    for b in (5,20):
        learn(SkillSpec.initial(),b,c['target_train'][:1 if b==5 else 2],
            c['target_validation'][:1 if b==5 else 4],factory,7,runner,tmp_path/str(b))
    assert created[0] is not created[1]
    assert created[0].proposals[0] == created[1].proposals[0]
    counts = [len(p.proposals) for p in created]
    evaluate(SkillSpec.initial(), c['target_test'],runner,tmp_path/'eval.jsonl')
    assert counts == [len(p.proposals) for p in created]


def test_llm_two_requests_fallback_and_no_secret_logging(tmp_path, monkeypatch):
    calls=[]
    def invalid(payload):
        calls.append(payload)
        return {'choices':[{'message':{'content':'{"code":"evil"}'}}]}
    monkeypatch.setenv('PEBX_LLM_API_KEY','do-not-log-this')
    proposer=BoundedLLM(2,endpoint='http://localhost/test',model='test',log_path=tmp_path/'calls.jsonl',transport=invalid)
    assert proposer.propose(SkillSpec.initial(),[]) == SkillSpec.initial()
    assert len(calls) == 2
    assert 'do-not-log-this' not in (tmp_path/'calls.jsonl').read_text()


def test_physical_validation_refuses_missing_evidence(tmp_path):
    with pytest.raises(ValueError,match='Missing evidence'):
        validate_run(tmp_path)


def test_paired_retry_reruns_both_sides_keeps_attempts(tmp_path):
    from physicalevobench_x.protocol.paired import paired_evaluate
    left, right = FakeRunner(), FakeRunner(failures=[1])
    pairs = paired_evaluate(SkillSpec.initial(),SkillSpec.initial(),
        generate(1,dict(target_test=2))['target_test'],lambda side:left if side=='before' else right,
        tmp_path/'pairs')
    assert len(left.requests) == len(right.requests) == 3
    assert len(pairs) == 2
    attempts=[json.loads(l) for l in (tmp_path/'pairs/pair_attempts.jsonl').read_text().splitlines()]
    assert [a['included'] for a in attempts] == [False,True,True]


def test_source_rollback_aliases_whole_target_adaptation(tmp_path):
    from physicalevobench_x.protocol.orchestration import transfer
    runners=[]
    def factory(role):
        runner=FakeRunner()
        runners.append(runner)
        return runner
    c=generate(1,dict(source_train=2,source_validation=4,target_train=2,target_validation=4,target_test=3))
    summaries=transfer(SkillSpec.initial(),conditions=c,budgets=[0,5,20],proposer_factory=RandomSearch,
        runner_factory=factory,seed=dict(run_seed_id=0,source_proposal=5,target_proposal=6),
        identity_context=dict(embodiment='franka_robotiq',controller_hash='a',adapter_hash='b',
                              proposer_config={'learner':'random_search_v1'},public_context={}),output=tmp_path/'transfer')
    assert all(s['delta_new']==0 and s['adaptation_aliased'] for s in summaries)
    assert sum(len(r.requests) for r in runners) == 20+5+20+3*3
    assert len(json.loads((tmp_path/'transfer/aliases.json').read_text()))==3


def test_acceptance_requires_success_or_paired_five_percent_time(tmp_path, runner):
    initial=SkillSpec.initial()
    changed=RandomSearch(9).propose(initial,[])
    cond=generate(1,dict(source_validation=4))['source_validation']
    baseline=[runner.run(skill=initial,condition=c,phase='validation',candidate_index=0,attempt_index=0) for c in cond]
    before=[r.model_copy(update={'task_success':True,'completion_time_s':10.}) for r in baseline]
    tied=[r.model_copy(update={'skill_hash':changed.semantic_hash,'task_success':True,'completion_time_s':9.6}) for r in baseline]
    assert accept(initial,changed,before,tied)==(False,'ROLLBACK')
    improved=[r.model_copy(update={'completion_time_s':9.5}) for r in tied]
    assert accept(initial,changed,before,improved)==(True,'time')
    unsafe=[r.model_copy(update={'constraint_violations':('JOINT_OR_WORKSPACE_LIMIT',)}) for r in improved]
    assert accept(initial,changed,before,unsafe)==(False,'CONSTRAINT_REGRESSION')
    assert accept(initial,initial,before,improved)==(False,'NO_BEHAVIOR_CHANGE')


def test_reconstruction_detects_changed_artifact(tmp_path, runner):
    from physicalevobench_x.core.hashing import write_json
    c=generate(1,dict(source_train=2,source_validation=4))
    learn(SkillSpec.initial(),20,c['source_train'],c['source_validation'],RandomSearch,3,runner,tmp_path/'source')
    write_json(tmp_path/'source/after.json',RandomSearch(9).propose(SkillSpec.initial(),[]))
    with pytest.raises(ValueError,match='Reconstruction mismatch'):
        reconstruct(tmp_path/'source')


def test_llm_valid_response_single_call(tmp_path):
    calls=[]
    def valid(payload):
        calls.append(payload)
        return {'choices':[{'message':{'content':SkillSpec.initial().model_dump_json()}}],
                'usage':{'prompt_tokens':500,'completion_tokens':120}}
    proposer=BoundedLLM(3,endpoint='http://localhost/test',model='test',log_path=tmp_path/'calls.jsonl',transport=valid)
    assert proposer.propose(SkillSpec.initial(),[])==SkillSpec.initial()
    assert len(calls)==1


def test_fake_and_placeholder_reports_rejected(tmp_path):
    from physicalevobench_x.core.hashing import write_json
    for name in ('run_manifest.json','dependency_snapshot.json','costs.json','aliases.json','embodiment_diff.json'):
        write_json(tmp_path/name,{})
    (tmp_path/'protocol_snapshot.yaml').write_text('version: test\n')
    write_json(tmp_path/'run_manifest.json',dict(task_definition_hash='generated_at_freeze'))
    with pytest.raises(ValueError,match='placeholder'):
        validate_run(tmp_path)
    manifest={k:'a'*64 for k in ('task_definition_hash','split_manifest_hash','controller_hash','adapter_hash','freeze_hash')}
    manifest['backend']='fake'
    write_json(tmp_path/'run_manifest.json',manifest)
    with pytest.raises(ValueError,match='fake'):
        validate_run(tmp_path)


def test_test_split_cannot_become_training_feedback(tmp_path,runner):
    c=generate(1,dict(target_test=1,target_validation=1))
    with pytest.raises(ValueError,match='training split'):
        learn(SkillSpec.initial(),5,c['target_test'],c['target_validation'],RandomSearch,1,runner,tmp_path/'bad')
    assert runner.requests==[]
