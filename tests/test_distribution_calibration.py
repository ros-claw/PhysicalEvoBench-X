"""Catch false geometry/material certification before spending physical calls."""
import importlib.util
import json
from pathlib import Path
import numpy as np
import pytest

@pytest.fixture
def calibration(monkeypatch):
    root=Path(__file__).resolve().parents[1];monkeypatch.syspath_prepend(str(root/'tools'))
    spec=importlib.util.spec_from_file_location('calibration',root/'tools/calibrate_distribution_v1.py')
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m


def readback(c):
    x,y,z=c['size_m'];m=c['mass_kg']
    return dict(geometry_sizes_m=[[x,y,z]],mass_kg=[m],
        inertia_kg_m2=np.diag([m*(y*y+z*z)/12,m*(x*x+z*z)/12,m*(x*x+y*y)/12]).tolist(),
        material=[[[c['friction'],c['friction'],0.]]],reset_position_m=[.5,0.,z/2+.002])

@pytest.mark.parametrize('field,value',[('geometry_sizes_m',[]),('geometry_sizes_m',[[.045,.045,.065]]),
    ('mass_kg',[.65]),('material',[[[1.,.2,0.]]]),('reset_position_m',[.5,0.,.0345]),
    ('inertia_kg_m2',np.zeros((3,3)).tolist())])
def test_wrong_scene_readbacks_rejected(calibration,field,value):
    c=calibration.conditions()[1];r=readback(c)
    assert calibration.check_readback(c,r)
    r[field]=value;assert not calibration.check_readback(c,r)


def test_plan_retains_baseline_and_balanced_repeats(calibration,tmp_path):
    p=calibration.plan(tmp_path/'study')
    assert p['planned_calls']==30 and p['formal_result_eligible'] is False
    assert p['skills']['initial']==calibration.SkillSpec.initial().model_dump()
    for body,jobs in p['jobs'].items():
        assert len(jobs)==15 and len({j['name'] for j in jobs})==15
        for j in jobs:
            if j['repeat_of']:
                old=next(x for x in jobs if x['name']==j['repeat_of'])
                assert old['condition']==j['condition'] and old['skill']==j['skill']
    path=tmp_path/'study/plan.json';changed=json.loads(path.read_text());changed['jobs']['franka_panda'].pop()
    path.write_text(json.dumps(changed))
    with pytest.raises(ValueError,match='changed'):calibration.verify(tmp_path/'study')


def test_repeat_comparison_excludes_only_identity_and_catches_action_drift(monkeypatch,tmp_path):
    root=Path(__file__).resolve().parents[1];monkeypatch.syspath_prepend(str(root/'tools'))
    from audit_distribution_v1 import compare_traces
    a=tmp_path/'a';b=tmp_path/'b'
    row=dict(observation=dict(episode_id='first',sim_time_s=1.,object_size_m=[.035,.035,.14]),native_action=[0.,1.])
    a.write_text(json.dumps(row)+'\n');row['observation']['episode_id']='repeat';b.write_text(json.dumps(row)+'\n')
    assert compare_traces(a,b,actions=True)['exactly_equal']
    row['native_action'][0]=.01;b.write_text(json.dumps(row)+'\n')
    assert not compare_traces(a,b,actions=True)['exactly_equal']
    assert compare_traces(a,b,actions=False)['exactly_equal']
    b.write_text('')
    assert compare_traces(a,b,actions=True)['mismatched_rows']==1
