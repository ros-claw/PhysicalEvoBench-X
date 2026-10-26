"""CPU-only observation fixtures; not physical experiments."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).parents[1]/'tools'))
from replay_pose_candidate import replay_frames


def test_early_end_is_censored_instead_of_imputed_failure(observation):
    initial=observation(t=0.,height=.1)
    frames=[observation(t=i*.02,height=.2,tcp_height=.3) for i in range(1,56)]
    assert replay_frames(initial,frames,[(-1.,1.)]) is None
    frames.append(observation(t=1.12,height=.2,tcp_height=.3))
    assert replay_frames(initial,frames,[(-1.,1.)])['task_success']


def test_recorded_measured_joint_failure_has_priority(observation):
    initial=observation(t=0.,height=.1)
    frames=[observation(t=i*.02,height=.2,tcp_height=.3) for i in range(1,57)]
    frames[-1]=frames[-1].model_copy(update={'joint_positions':(2.,)})
    result=replay_frames(initial,frames,[(-1.,1.)])
    assert not result['task_success'] and result['termination_reason']=='JOINT_OR_WORKSPACE_LIMIT'
