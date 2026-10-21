import pytest
from physicalevobench_x.core.schemas import ObservationFrame, Pose, EpisodeResult


@pytest.fixture
def observation():
    def make(t=0., height=.1, tcp_height=.2, velocity=(0.,0.,0.)):
        return ObservationFrame(schema_version='physicalevobench_x.observation.v1', episode_id='unit',
            sim_time_s=t, joint_positions=(0.,), joint_velocities=(0.,),
            tcp_pose_w=Pose(position_m=(.5,0.,tcp_height), quaternion_xyzw=(0.,0.,0.,1.)),
            object_pose_w=Pose(position_m=(.5,0.,height), quaternion_xyzw=(0.,0.,0.,1.)),
            object_linear_velocity_w=velocity, object_angular_velocity_w=(0.,0.,0.),
            object_size_m=(.045,.045,.065), gripper_opening_width_m=.08,
            workspace_min_m=(-1.,-1.,-1.), workspace_max_m=(1.,1.,1.))
    return make


class FakeRunner:
    """Protocol-only test double. Never exported into benchmark performance."""
    def __init__(self, failures=()):
        self.requests = []
        self.failures = set(failures)

    def run(self, *, skill, condition, phase, candidate_index, attempt_index):
        self.requests.append((condition['condition_id'], skill.semantic_hash, phase, candidate_index, attempt_index))
        i = len(self.requests)
        return EpisodeResult(episode_id=f'fake-{i}', condition_id=condition['condition_id'],
            split=condition['split'], phase=phase, candidate_index=candidate_index,
            skill_hash=skill.semantic_hash, backend='fake', task_success=False,
            max_lift_m=.01, completion_time_s=15., hold_time_s=0., termination_reason='FAKE',
            infra_failure='SIM_START_FAILURE' if i in self.failures else None,
            attempt_index=attempt_index, simulator_steps=1, sim_time_s=.02, wall_time_s=.01)


@pytest.fixture
def runner():
    return FakeRunner()
