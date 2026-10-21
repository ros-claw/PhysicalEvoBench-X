import math
import numpy as np
import pytest
from physicalevobench_x.control.geometry import compose, invert, relative, angle
from physicalevobench_x.control.adapter import EmbodimentAdapter
from physicalevobench_x.control.trajectory import trapezoid_distance
from physicalevobench_x.control.grasp_lift_executor import GraspLiftExecutor
from physicalevobench_x.core.schemas import Pose, CanonicalCommand, Gripper, SkillSpec
from physicalevobench_x.sim.judge import StableLiftJudge


def test_transform_roundtrip_and_rotated_offset():
    root = Pose(position_m=(1.,2.,3.), quaternion_xyzw=(0.,0.,math.sin(math.pi/4),math.cos(math.pi/4)))
    offset = Pose(position_m=(.1,0.,0.), quaternion_xyzw=(0.,0.,0.,1.))
    result = compose(root, offset)
    assert np.allclose(result.position_m, (1.,2.1,3.))
    assert np.allclose(relative(root,result).position_m, offset.position_m)
    assert np.allclose(compose(root,invert(root)).position_m, (0.,0.,0.))
    assert angle(root.quaternion_xyzw, tuple(-x for x in root.quaternion_xyzw)) == pytest.approx(0.)


@pytest.mark.parametrize('body,open_value,close_value', [('franka_panda',1.,-1.),('franka_robotiq',0.,1.)])
def test_native_encoding_root_frame_scale_and_gripper(body, open_value, close_value):
    root = Pose(position_m=(1.,0.,0.), quaternion_xyzw=(0.,0.,math.sqrt(.5),math.sqrt(.5)))
    current = compose(root, Pose(position_m=(.5,0.,.1),quaternion_xyzw=(0.,0.,0.,1.)))
    offset = Pose(position_m=(.1,0.,0.), quaternion_xyzw=(0.,0.,0.,1.))
    tcp = compose(current, offset)
    desired = tcp.model_copy(update={'position_m':tuple(np.asarray(tcp.position_m)+(0.,.01,0.))})
    adapter = EmbodimentAdapter(body)
    for gripper, value in [(Gripper.OPEN,open_value),(Gripper.CLOSE,close_value)]:
        encoded = adapter.encode(CanonicalCommand(tcp_pose_w=desired,gripper=gripper),root,current,offset)
        assert encoded[-1] == value
        assert encoded[:3] == pytest.approx((.02,0.,0.), abs=1e-12)


def test_trajectory_speed_acceleration_and_stop():
    ts = np.arange(0,5,.001)
    xs = np.array([trapezoid_distance(t,.12,.1,.3)[0] for t in ts])
    vs = np.diff(xs)/.001
    assert vs.max() <= .1+1e-8
    assert np.abs(np.diff(vs)/.001).max() <= .3+1e-7
    assert xs[-1] == pytest.approx(.12)


def test_hold_requires_full_second_and_reset(observation):
    judge = StableLiftJudge()
    judge.reset(observation())
    for i in range(50):
        assert judge.update(observation(t=1+i*.02,height=.2,tcp_height=.3)) is None
    assert judge.update(observation(t=2.,height=.2,tcp_height=.3))['task_success']
    judge.reset(observation(t=5.))
    assert judge.update(observation(t=5.02,height=.2,tcp_height=.3)) is None


@pytest.mark.parametrize('interruption', ['throw','slip','support','hard'])
def test_non_grasp_success_exclusions(observation, interruption):
    judge = StableLiftJudge()
    judge.reset(observation())
    for i in range(40):
        judge.update(observation(t=1+i*.02,height=.2,tcp_height=.3))
    if interruption == 'throw':
        result = judge.update(observation(t=1.8,height=.2,tcp_height=.3,velocity=(0.,0.,1.)))
    elif interruption == 'slip':
        result = judge.update(observation(t=1.8,height=.2,tcp_height=.4))
    elif interruption == 'support':
        result = judge.update(observation(t=1.8,height=.2,tcp_height=.3),static_support_clear=False)
    else:
        result = judge.update(observation(t=2.,height=.2,tcp_height=.3),hard_failures=['JOINT_OR_WORKSPACE_LIMIT'])
        assert not result['task_success']
        return
    assert result is None
    assert judge.update(observation(t=2.,height=.2,tcp_height=.3)) is None


def test_executor_parameters_change_real_command_and_fixed_lift(observation):
    initial = observation(height=.1,tcp_height=.4)
    a, b = GraspLiftExecutor(), GraspLiftExecutor()
    skill = SkillSpec.initial()
    data = skill.model_dump()
    data['parameters']['grasp_height_fraction'] = .75
    data['parameters']['pregrasp_clearance_m'] = .12
    a.reset(skill,initial)
    b.reset(SkillSpec.model_validate(data),initial)
    assert a.grasp[2] != b.grasp[2]
    assert a.pre[2] != b.pre[2]
    a.stage = 'SETTLE'
    a.stage_start = 0.
    a.step(observation(t=1.,tcp_height=.2))
    assert a.stage == 'LIFT'
    assert a.goal[2] == pytest.approx(.32)
    for i in range(100):
        a.step(observation(t=1.02+i*.02,tcp_height=.2+i*.001))
    assert a.goal[2] == pytest.approx(.32)
