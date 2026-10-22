"""Trusted world reader. Outputs detached immutable public values only."""
import numpy as np
from ..core.schemas import ObservationFrame, Pose
from ..control.geometry import compose, relative, multiply


def array(value):
    if hasattr(value, 'torch'):
        value = value.torch
    if not hasattr(value, 'detach'):
        import warp as wp
        value = wp.to_torch(value)
    return value.detach().cpu().numpy().copy()


def pose(value):
    v = array(value)[0]
    return Pose(position_m=tuple(v[:3]),quaternion_xyzw=tuple(v[3:]))


class StateReader:
    def __init__(self, embodiment, axis_mapping_xyzw, size_m=(.045,.045,.065),
                 workspace_min_m=(.15,-.35,-.1), workspace_max_m=(.85,.35,.65)):
        self.embodiment = embodiment
        self.axis_mapping = axis_mapping_xyzw
        self.size_m = size_m
        self.workspace_min_m, self.workspace_max_m = workspace_min_m, workspace_max_m

    def read(self, env, episode_id):
        if env.num_envs != 1:
            raise ValueError('v0.1 requires num_envs=1')
        world = env.arena_world
        robot = env.scene['robot']
        body_name = 'panda_hand' if self.embodiment == 'franka_panda' else 'base_link'
        body = pose(world.get_body_pose_w('robot', body_name))
        midpoint = (array(world.get_frame_position_w('ee_frame','tool_leftfinger'))[0]
                  + array(world.get_frame_position_w('ee_frame','tool_rightfinger'))[0])/2
        tcp = Pose(position_m=tuple(midpoint),
                   quaternion_xyzw=tuple(multiply(body.quaternion_xyzw, self.axis_mapping)))
        self.control_w = compose(body, Pose(position_m=(0.,0.,.107),quaternion_xyzw=(0.,0.,0.,1.))) if self.embodiment == 'franka_panda' else body
        self.root_w = pose(world.get_pose_w('robot'))
        self.control_to_tcp = relative(self.control_w, tcp)
        gripper = env.arena_env.embodiment.get_gripper() if hasattr(env,'arena_env') else self.gripper
        return ObservationFrame(schema_version='physicalevobench_x.observation.v1',
            episode_id=episode_id, sim_time_s=float(env.episode_length_buf[0].item())*env.step_dt,
            joint_positions=tuple(array(robot.data.joint_pos)[0]),
            joint_velocities=tuple(array(robot.data.joint_vel)[0]), tcp_pose_w=tcp,
            object_pose_w=pose(world.get_pose_w('pebx_object')),
            object_linear_velocity_w=tuple(array(world.get_root_linear_velocity_w('pebx_object'))[0]),
            object_angular_velocity_w=tuple(array(world.get_root_angular_velocity_w('pebx_object'))[0]),
            object_size_m=self.size_m,gripper_opening_width_m=float(gripper.get_opening_width_m(world)[0].item()),
            workspace_min_m=self.workspace_min_m,workspace_max_m=self.workspace_max_m)
