"""Protect coverage bounds and crash-safe grid cursor restoration."""
import copy
from pathlib import Path
import pytest


def module(monkeypatch):
    root=Path(__file__).resolve().parents[1];monkeypatch.syspath_prepend(str(root/'tools'));monkeypatch.syspath_prepend(str(root/'scripts'))
    import learn_height_coverage_v1
    return learn_height_coverage_v1


def test_coverage_cannot_inherit_changed_nonheight_parameters(monkeypatch):
    m=module(monkeypatch);incumbent=m.SkillSpec.initial().model_dump();incumbent['parameters']['pregrasp_clearance_m']=.12
    proposer=m.HeightGrid(0);skills=[proposer.propose(m.SkillSpec.model_validate(incumbent),[]) for _ in range(5)]
    initial=m.SkillSpec.initial().model_dump()
    assert [s.parameters.grasp_height_fraction for s in skills]==pytest.approx([.45,.525,.6,.675,.75])
    for skill in skills:
        value=skill.model_dump();value['parameters']['grasp_height_fraction']=initial['parameters']['grasp_height_fraction'];assert value==initial
    with pytest.raises(ValueError,match='exhausted'):proposer.propose(m.SkillSpec.initial(),[])


def test_replayed_proposals_restore_grid_cursor_before_next_new_proposal(monkeypatch,tmp_path):
    m=module(monkeypatch)
    from pilot_support import ReplayJournal,replay_factory
    initial=m.SkillSpec.initial();identity={'scope':'unit-test-proposals-only'}
    first=replay_factory(ReplayJournal(tmp_path,identity),m.HeightGrid)(0)
    assert first.propose(initial,[]).parameters.grasp_height_fraction==pytest.approx(.45)
    assert first.propose(initial,[]).parameters.grasp_height_fraction==pytest.approx(.525)
    resumed=replay_factory(ReplayJournal(tmp_path,identity),m.HeightGrid)(0)
    resumed.propose(initial,[]);resumed.propose(initial,[])
    assert resumed.propose(initial,[]).parameters.grasp_height_fraction==pytest.approx(.6)


def test_new_coverage_scenes_are_independent_of_primary_learning_and_calibration(monkeypatch):
    m=module(monkeypatch);new=m.generate_conditions();old=m.base.generate_conditions()
    assert sum(map(len,new.values()))==14
    assert not ({m.base.scene_fingerprint(c) for rows in new.values() for c in rows}&{m.base.scene_fingerprint(c) for rows in old.values() for c in rows})
