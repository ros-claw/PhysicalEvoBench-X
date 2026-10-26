"""CPU-only counterexamples; no claim of native physics validation."""
import math
import numpy as np
import pytest
from physicalevobench_x.core.schemas import Pose
from physicalevobench_x.measurement.pose_window import PoseWindowJudge,PoseWindowConfig,load_pose_window_config


def frame(observation,t,*,height=.2,x=.5,yaw=0.,sign=1.,native_spin=10.):
    obs=observation(t=t,height=height,tcp_height=.3)
    return obs.model_copy(update={
        'object_pose_w':Pose(position_m=(x,0.,height),quaternion_xyzw=(0.,0.,sign*math.sin(yaw/2),sign*math.cos(yaw/2))),
        'object_angular_velocity_w':(0.,0.,native_spin)})


def test_full_window_and_hold_are_required_and_native_velocity_is_not_used(observation):
    judge=PoseWindowJudge();judge.reset(frame(observation,0.,height=.1))
    for i in range(1,56):
        assert judge.update(frame(observation,i*.02)) is None
    result=judge.update(frame(observation,1.12))
    assert result['task_success'] and result['hold_time_s']==pytest.approx(1.)
    assert judge.last_window_speeds==pytest.approx((0.,0.))


@pytest.mark.parametrize('kind',['translation','rotation'])
def test_observed_oscillation_cannot_cancel_in_the_trailing_window(observation,kind):
    judge=PoseWindowJudge();judge.reset(frame(observation,0.,height=.1))
    pattern=[0.,1.,0.,-1.,0.]
    for i in range(1,91):
        offset=pattern[i%5]
        obs=frame(observation,i*.02,x=.5+.004*offset if kind=='translation' else .5,
                  yaw=.06*offset if kind=='rotation' else 0.,native_spin=0.)
        assert judge.update(obs) is None
    assert judge.max_hold<1.
    assert judge.update(frame(observation,15.))['task_success'] is False


@pytest.mark.parametrize('obstruction',['support','release','hard','workspace'])
def test_false_success_counterexamples(observation,obstruction):
    judge=PoseWindowJudge();judge.reset(frame(observation,0.,height=.1))
    for i in range(1,36):assert judge.update(frame(observation,i*.02)) is None
    if obstruction=='hard':
        result=judge.update(frame(observation,.72),hard_failures=['JOINT_OR_WORKSPACE_LIMIT'])
        assert not result['task_success']
        return
    if obstruction=='workspace':
        assert not judge.update(frame(observation,.72,x=2.))['task_success']
        return
    for i in range(36,101):
        result=judge.update(frame(observation,i*.02,height=.1 if obstruction=='release' else .2),
                            static_support_clear=obstruction!='support')
        assert result is None or not result['task_success']


def test_relative_slip_interrupts_hold_even_with_static_world_object(observation):
    judge=PoseWindowJudge();judge.reset(frame(observation,0.,height=.1))
    for i in range(1,36):assert judge.update(frame(observation,i*.02)) is None
    moved=frame(observation,.72)
    moved=moved.model_copy(update={'tcp_pose_w':Pose(position_m=(.5,0.,.32),quaternion_xyzw=(0.,0.,0.,1.))})
    assert judge.update(moved) is None
    assert judge.hold_start is None


def test_gaps_and_duplicate_clocks_cannot_manufacture_continuous_hold(observation):
    judge=PoseWindowJudge();judge.reset(frame(observation,0.,height=.1))
    for i in range(1,36):judge.update(frame(observation,i*.02))
    assert judge.update(frame(observation,2.)) is None
    assert judge.gap_resets==1 and judge.hold_start is None
    for _ in range(20):assert judge.update(frame(observation,2.,sign=-1.)) is None
    with pytest.raises(ValueError,match='same measurement timestamp'):
        judge.update(frame(observation,2.,x=.51))
    with pytest.raises(ValueError,match='Nonmonotonic'):
        judge.update(frame(observation,1.99))


def test_quaternion_sign_is_not_motion(observation):
    judge=PoseWindowJudge();judge.reset(frame(observation,0.,height=.1))
    result=None
    for i in range(1,60):
        result=judge.update(frame(observation,i*.02,sign=(-1.)**i))
    assert result['task_success']


def test_sampling_rate_comparison_for_the_same_observed_trajectory(observation):
    completions=[]
    for dt in (.02,.005):
        judge=PoseWindowJudge();judge.reset(frame(observation,0.,height=.1))
        for t in np.arange(dt,1.7,dt):
            result=judge.update(frame(observation,float(t),height=.1+.1*min(t/.3,1.)))
            if result:
                assert result['task_success'];completions.append(result['completion_time_s']);break
    assert len(completions)==2 and abs(completions[0]-completions[1])<=.025


def test_reject_invalid_candidate_settings():
    with pytest.raises(ValueError):PoseWindowConfig(window_s=2.)
    with pytest.raises(ValueError):PoseWindowConfig(max_gap_s=0.)


def test_candidate_yaml_values_are_consumed_and_unknown_fields_rejected(tmp_path):
    from pathlib import Path
    import yaml
    data=yaml.safe_load((Path(__file__).parents[1]/'configs/measurement/pose_path_candidate_v1.yaml').read_text())
    data['window_s']=.2
    path=tmp_path/'measurement.yaml';path.write_text(yaml.safe_dump(data))
    assert load_pose_window_config(path).window_s==.2
    data['extra_hidden_default']=True;path.write_text(yaml.safe_dump(data))
    with pytest.raises(ValueError):load_pose_window_config(path)
