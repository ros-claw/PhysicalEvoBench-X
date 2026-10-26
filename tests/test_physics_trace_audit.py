"""Keep scope/clamping verification and post-termination stimulus evidence honest."""
import importlib.util
import math
from pathlib import Path
import pytest


@pytest.fixture
def auditor(monkeypatch):
    root=Path(__file__).resolve().parents[1]
    monkeypatch.syspath_prepend(str(root/'tools'))
    spec=importlib.util.spec_from_file_location('physics_audit',root/'tools/audit_pose_physics_v3.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def test_solver_readback_rejects_wrong_scope_and_scene_clamp(auditor):
    profile=dict(physics_dt_s=.005,position_iterations=128,velocity_iterations=4)
    settings=dict(physics_dt_s=.005,control_dt_s=.02,articulations=[dict(position=128,velocity=4)],
        dynamic_bodies=[dict(position=128,velocity=4)],scenes=[dict(min_position=1,max_position=255,min_velocity=0,max_velocity=255)])
    assert auditor.configuration_matches(settings,profile)
    settings['dynamic_bodies'][0]['position']=64
    assert not auditor.configuration_matches(settings,profile)
    settings['dynamic_bodies'][0]['position']=128;settings['scenes'][0]['max_position']=64
    assert not auditor.configuration_matches(settings,profile)


def test_stimulus_audit_includes_late_motion_after_early_stable_segment(auditor,observation):
    rows=[]
    for step in range(1,601):
        t=step*.005;o=observation(t=t,height=.1 if t<=.5 else .2).model_dump()
        if t>1.8:o['object_pose_w']['position_m']=(.5+.008*math.sin(2*math.pi*4*(t-1.8)),0.,.2)
        rows.append(dict(observation=o))
    control=[dict(observation=dict(sim_time_s=.5),applied=True)]
    result=auditor.motion_summary(control,rows,'oscillate')
    assert result['stimulus_confirmed_from_uncensored_pose_trace']
    assert result['observed_elevated_window_speed_peak_mps']>.03
    assert result['elevated_samples_above_speed_limit']>0
