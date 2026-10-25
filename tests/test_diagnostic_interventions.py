"""CPU-only fixtures for diagnostic design and trace interpretation."""
from pathlib import Path
import sys

import pytest
from physicalevobench_x.core.schemas import SkillSpec

sys.path.insert(0,str(Path(__file__).parents[1]/'tools'))
from diagnostic_metrics import measure_rows
from diagnose_transfer import variants, condition_fingerprint


def source_skills():
    initial=SkillSpec.initial()
    data=initial.model_dump()
    data['parameters'].update(grasp_height_fraction=.58,pregrasp_clearance_m=.08,
                              settle_time_s=.2,lift_amax_mps2=.6)
    return initial,SkillSpec.model_validate(data)


def test_interventions_change_exactly_one_field_and_include_executed_null():
    initial,kimi=source_skills()
    values=variants(initial,kimi,initial)
    assert len(values)==12
    assert values['initial_repeat'].semantic_hash==initial.semantic_hash
    for name,skill in values.items():
        if name.startswith('initial_with_'):
            baseline=initial
        elif name.startswith('kimi_revert_'):
            baseline=kimi
        else:continue
        changed=[k for k,v in skill.parameters.model_dump().items() if v!=getattr(baseline.parameters,k)]
        assert len(changed)==1 and name.endswith(changed[0])
        assert skill.controller_family==initial.controller_family


def test_physical_overlap_check_ignores_opaque_ids_and_reset_seed():
    one=dict(condition_id='one',split='dev',reset_seed=1,mass_kg=.2)
    two={**one,'condition_id':'two','split':'target_test','reset_seed':2}
    assert condition_fingerprint(one)==condition_fingerprint(two)
    assert condition_fingerprint(one)!=condition_fingerprint({**two,'mass_kg':.3})


def test_elevated_spin_metrics_exclude_pre_lift_motion_and_include_terminal(observation):
    initial=observation(t=0,height=.1).model_dump()
    pre=observation(t=.5,height=.1).model_dump()
    pre['object_angular_velocity_w']=[0.,0.,100.]
    lifted=observation(t=1.,height=.2).model_dump()
    lifted['object_angular_velocity_w']=[0.,0.,.6]
    terminal={**lifted,'sim_time_s':2.}
    rows=[dict(observation=pre,stage='LIFT'),dict(observation=lifted,stage='HOLD')]
    measured=measure_rows(rows,dict(initial=initial,terminal=dict(observation=terminal)))
    assert measured['elevated_samples']==2
    assert measured['elevated_angular_over_limit_fraction']==1.
    assert measured['elevated_angular_max_radps']==pytest.approx(.6)
    assert measured['lift_reference_peak_speed_mps'] is None


def test_reference_and_measured_speeds_have_distinct_units(observation):
    initial=observation(t=0,height=.1).model_dump()
    rows=[]
    for t,ref,actual in [(1.,.2,.2),(2.,.3,.28)]:
        obs=observation(t=t,height=.2,tcp_height=actual).model_dump()
        rows.append(dict(observation=obs,stage='LIFT',
                         canonical_command=dict(tcp_pose_w=dict(position_m=[.5,0.,ref]))))
    result=measure_rows(rows,dict(initial=initial,terminal=dict(observation=rows[-1]['observation'])))
    assert result['lift_reference_peak_speed_mps']==pytest.approx(.1)
    assert result['lift_measured_tcp_peak_speed_mps']==pytest.approx(.08)
    assert result['lift_reference_tracking_peak_error_m']==pytest.approx(.02)
