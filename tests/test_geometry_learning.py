"""Protect split independence and prevent non-native results from entering learning."""
import copy
import importlib.util
from pathlib import Path
import pytest

@pytest.fixture
def experiment(monkeypatch):
    root=Path(__file__).resolve().parents[1];monkeypatch.syspath_prepend(str(root/'tools'))
    spec=importlib.util.spec_from_file_location('geometry_learning',root/'tools/learn_geometry_v1.py')
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m


def test_no_scene_reuse_even_with_different_ids_and_reset_seeds(experiment):
    m=experiment.generate_conditions();all_rows=[c for rows in m.values() for c in rows]
    assert len(all_rows)==14
    assert len({experiment.scene_fingerprint(c) for c in all_rows})==14
    previous=experiment.scene_fingerprint(m['source_train'][0])
    # Recomputing IDs cannot make duplicate physical scenes valid across splits.
    c=m['target_test'][0]
    for key in ('size_m','mass_kg','friction','offset_xy_m','yaw_rad'):c[key]=copy.deepcopy(m['source_train'][0][key])
    c['condition_id']=experiment.digest(dict(revision='DEVELOPMENT_GEOMETRY_LEARNING_V1',condition={k:v for k,v in c.items() if k!='condition_id'}))[:24]
    assert experiment.scene_fingerprint(c)==previous
    with pytest.raises(ValueError,match='Overlapping'):experiment.validate_manifests(m)


def test_tampered_heldout_manifest_is_rejected_before_native_call(experiment,tmp_path):
    study=tmp_path/'study';p=experiment.plan(study)
    assert p['planned_physical_calls']==72 and p['source_budget']==20 and p['target_adaptation_budget']==0
    assert p['initial_skill']==experiment.SkillSpec.initial().model_dump()
    m=experiment.generate_conditions();m['target_test'][0]['mass_kg']+=.001
    experiment.write_json(study/'private_conditions.json',m)
    with pytest.raises(ValueError,match='manifest changed'):experiment.verify(study)


@pytest.mark.parametrize('field,value',[('backend','fake'),('body','wrong'),('scenario','wrong'),('condition',{})])
def test_wrong_native_identity_rejected(experiment,field,value):
    c=experiment.generate_conditions()['source_train'][0]
    raw=dict(backend='physx',body='franka_panda',scenario='episode',condition=c,infra_failure=None,
        candidate_50hz={},candidate_200hz={},native_50hz={})
    raw[field]=value
    with pytest.raises(ValueError,match='identity'):experiment.validate_raw(raw,'franka_panda',c,'episode')


def test_offline_journal_normalizes_json_and_never_appends_missing_calls(experiment,tmp_path,monkeypatch):
    root=Path(__file__).resolve().parents[1];monkeypatch.syspath_prepend(str(root/'tools'))
    from audit_geometry_learning_v1 import ReadOnlyJournal
    identity=dict(plan_hash='unit-test-only')
    experiment.write_json(tmp_path/'identity.json',identity)
    request=dict(history=[dict(constraint_violations=())])
    experiment.write_json(tmp_path/'00000.json',dict(status='COMPLETE',physical=False,
        request=request,request_hash=experiment.digest(request),result=dict(skill='unit-test-only')))
    before={p.name:p.read_bytes() for p in tmp_path.iterdir()}
    journal=ReadOnlyJournal(tmp_path,identity)
    assert journal.call(request,lambda:pytest.fail('audit executed a proposal'))==dict(skill='unit-test-only')
    with pytest.raises(FileNotFoundError):journal.call({},lambda:pytest.fail('audit executed a missing call'))
    assert before=={p.name:p.read_bytes() for p in tmp_path.iterdir()}


def test_public_export_rejects_nested_exact_conditions_but_allows_scalar_results(monkeypatch):
    root=Path(__file__).resolve().parents[1];monkeypatch.syspath_prepend(str(root/'tools'))
    from report_geometry_learning_v1 import check_public
    check_public(dict(cases=[dict(condition_id='id',task_success=False,max_lift_m=0.)]))
    with pytest.raises(ValueError,match='private condition'):
        check_public(dict(projection=[dict(condition_id='id',reset_seed=123,size_m=[.035,.035,.14])]))


def test_pair_preparation_ignores_identity_and_later_skill_effects_but_detects_initial_state_drift(monkeypatch,tmp_path):
    import json
    root=Path(__file__).resolve().parents[1];monkeypatch.syspath_prepend(str(root/'tools'))
    from audit_geometry_learning_v1 import compare_preparation
    a=tmp_path/'before';b=tmp_path/'after'
    def rows(identity,end_value,start_value=1.):
        return [dict(observation=dict(episode_id=identity,sim_time_s=t,position=start_value if t<=.5 else end_value),native_action=[0.] if t<.5 else [end_value]) for t in [0.,.02,.5,.52]]
    a.write_text(''.join(json.dumps(r)+'\n' for r in rows('a',1.)))
    b.write_text(''.join(json.dumps(r)+'\n' for r in rows('b',2.)))
    assert compare_preparation(a,b,actions=True)['exactly_equal']
    b.write_text(''.join(json.dumps(r)+'\n' for r in rows('b',2.,start_value=1.001)))
    result=compare_preparation(a,b,actions=True)
    assert not result['exactly_equal']
    assert result['max_abs_numeric_differences']['.observation.position']==pytest.approx(.001)
