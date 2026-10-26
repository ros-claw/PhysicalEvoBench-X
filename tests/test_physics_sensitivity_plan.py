"""Prevent coupled-factor and observation-rate confounds before GPU execution."""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import pytest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('sensitivity',ROOT/'tools/validate_pose_physics_v3.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


def test_profiles_preserve_control_and_observation_rates():
    baseline=module.PROFILES['baseline']
    expected={'half_physics_step':{'physics_dt_s','decimation'},
              'double_position_iterations':{'position_iterations'},
              'double_velocity_iterations':{'velocity_iterations'}}
    for name,p in module.PROFILES.items():
        stride=module.observer_stride(p)
        assert p['physics_dt_s']*stride==.005
        assert p['physics_dt_s']*p['decimation']==.02
        if name!='baseline':assert {k for k in p if p[k]!=baseline[k]}==expected[name]


@pytest.mark.parametrize('step,decimation',[(.003,7),(.01,2),(.005,8)])
def test_reject_observation_or_control_clock_confounds(step,decimation):
    with pytest.raises(ValueError):module.observer_stride(dict(physics_dt_s=step,decimation=decimation))


def test_profile_updates_both_robot_scopes_and_object():
    scopes=[SimpleNamespace(solver_position_iteration_count=1,solver_velocity_iteration_count=1) for _ in range(3)]
    arena=SimpleNamespace(embodiment=SimpleNamespace(scene_config=SimpleNamespace(robot=SimpleNamespace(
        spawn=SimpleNamespace(rigid_props=scopes[0],articulation_props=scopes[1])))),
        scene=SimpleNamespace(assets={'pebx_object':SimpleNamespace(object_cfg=SimpleNamespace(spawn=SimpleNamespace(rigid_props=scopes[2])))}))
    module.apply_profile(arena,module.PROFILES['double_velocity_iterations'])
    assert all((s.solver_position_iteration_count,s.solver_velocity_iteration_count)==(64,8) for s in scopes)
    cfg=SimpleNamespace(sim=SimpleNamespace(dt=.1),decimation=1)
    assert arena.env_cfg_callback(cfg) is cfg
    assert cfg.sim.dt*cfg.decimation==.02


def test_plan_covers_all_profiles_and_keeps_probes_out_of_task_counts(tmp_path,monkeypatch):
    from physicalevobench_x.core.conditions import generate
    from physicalevobench_x.core.schemas import SkillSpec
    root=tmp_path/'repo';previous=root/'runs/pose-native-matched-v2-20261026';previous.mkdir(parents=True)
    config=root/'configs/measurement/pose_path_candidate_v1.yaml';config.parent.mkdir(parents=True)
    config.write_bytes((ROOT/'configs/measurement/pose_path_candidate_v1.yaml').read_bytes())
    source=tmp_path/'source';source.mkdir()
    case=source/'case.json';condition=generate(42,dict(dev=1))['dev'][0]
    case.write_text(json.dumps(dict(job=dict(condition=condition,variant='selected'),result=dict(skill_hash=SkillSpec.initial().semantic_hash))))
    source_plan=dict(variants={'selected':SkillSpec.initial().model_dump()});source_plan['plan_hash']=module.digest(source_plan)
    (source/'plan.json').write_text(json.dumps(source_plan))
    old_plan=dict(source_disagreement=dict(path=str(case),sha256=module.file_digest(case)));old_plan['plan_hash']=module.digest(old_plan)
    (previous/'plan.json').write_text(json.dumps(old_plan))
    (previous/'report.json').write_text(json.dumps(dict(status='NATIVE_CANDIDATE_DIAGNOSTICS_PASSED')))
    monkeypatch.setattr(module,'ROOT',root);monkeypatch.setattr(module,'inputs',lambda:{'unit_test':'not-physical-evidence'})
    monkeypatch.setattr(module.subprocess,'check_output',lambda *a,**k:'unit-test-commit\n')
    plan=module.plan(tmp_path/'planned',source)
    jobs=[(body,j) for body,rows in plan['jobs'].items() for j in rows]
    assert len(jobs)==plan['planned_calls']==44
    assert sum(j['scenario']=='configuration_probe' for _,j in jobs)==plan['planned_configuration_probes']==8
    assert sum(j['scenario']!='configuration_probe' for _,j in jobs)==plan['planned_full_horizon_calls']==36
    assert len({(body,j['name']) for body,j in jobs})==44
    assert all(j['settle_mode']=='native_zero_relative' for _,j in jobs)
    assert all(j['expected_candidate_success'] is None for _,j in jobs if j['scenario']=='configuration_probe')
    case.write_text(case.read_text()+' ')
    with pytest.raises(ValueError,match='provenance'):module.plan(tmp_path/'tampered',source)
