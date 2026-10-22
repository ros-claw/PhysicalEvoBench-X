"""External typed factory for the pinned Arena API; development scene only."""
from dataclasses import dataclass
import isaaclab.sim as sim_utils
from isaaclab_arena.assets.object import Object
from isaaclab_arena.assets.object_type import ObjectType
from isaaclab_arena.assets.object_library import GroundPlane, DomeLight
from isaaclab_arena.assets.register import register_environment
from isaaclab_arena.environments.arena_environment_factory import ArenaEnvironmentCfg, ArenaEnvironmentFactory
from isaaclab_arena.environments.isaaclab_arena_environment import IsaacLabArenaEnvironment
from isaaclab_arena.environments.isaaclab_arena_manager_based_env_cfg import set_control_rate_50hz
from isaaclab_arena.recording.episode_recorder_manager import EpisodeRecorderTermCfg
from isaaclab_arena.scene.scene import Scene
from isaaclab_arena.utils.pose import Pose
from .state_reader import StateReader
from .stable_lift_task import StableLiftTask, terminal_record


@dataclass
class StableLiftEnvironmentCfg(ArenaEnvironmentCfg):
    embodiment: str = 'franka_panda'
    # Explicit development mappings, require axis/motion calibration before freeze.
    axis_mapping_xyzw: tuple = (0.,0.,0.,1.)
    mass_kg: float = .2
    offset_xy_m: tuple = (0.,0.)
    yaw_rad: float = 0.


@register_environment
class StableLiftEnvironment(ArenaEnvironmentFactory[StableLiftEnvironmentCfg]):
    name = 'PEBX-StableLift-v0'

    def build(self, cfg):
        import math
        names={'franka_panda':'franka_ik','franka_robotiq':'droid_differential_ik'}
        embodiment=self.asset_registry.get_asset_by_name(names[cfg.embodiment])(enable_cameras=False)
        # Explicit common ready arm pose, not Arena's high reaching pose.
        arm = [0., -.569, 0., -2.810, 0., 3.037, .741]
        fingers = [.04, .04] if cfg.embodiment == 'franka_panda' else [0.]*6
        embodiment.set_initial_joint_pose(arm + fingers)
        # One common contact solver budget for both configurations, frozen before learning.
        embodiment.scene_config.robot.spawn.rigid_props.solver_position_iteration_count = 64
        embodiment.scene_config.robot.spawn.rigid_props.solver_velocity_iteration_count = 4
        embodiment.scene_config.robot.spawn.collision_props = sim_utils.CollisionPropertiesCfg(
            contact_offset=.002, rest_offset=0.)
        if cfg.embodiment == 'franka_panda':
            hand = embodiment.scene_config.robot.actuators['panda_hand']
            hand.joint_effort_limit = 40.
            hand.stiffness = 500.
            hand.damping = 40.
        size=(.045,.045,.065)
        obj=Object(name='pebx_object',object_type=ObjectType.RIGID,
            initial_pose=Pose(position_xyz=(.5+cfg.offset_xy_m[0],cfg.offset_xy_m[1],size[2]/2+.002),
                rotation_xyzw=(0.,0.,math.sin(cfg.yaw_rad/2),math.cos(cfg.yaw_rad/2))),
            spawner_cfg=sim_utils.CuboidCfg(size=size,
                rigid_props=sim_utils.RigidBodyPropertiesCfg(disable_gravity=False,
                    solver_position_iteration_count=64,solver_velocity_iteration_count=4),
                collision_props=sim_utils.CollisionPropertiesCfg(contact_offset=.002,rest_offset=0.),
                mass_props=sim_utils.MassPropertiesCfg(mass=cfg.mass_kg),
                physics_material=sim_utils.RigidBodyMaterialCfg(static_friction=1.,dynamic_friction=1.,restitution=0.)))
        table=Object(name='pebx_table',object_type=ObjectType.RIGID,
            initial_pose=Pose(position_xyz=(.5,0.,-.025)),
            spawner_cfg=sim_utils.CuboidCfg(size=(.5,.6,.05),
                rigid_props=sim_utils.RigidBodyPropertiesCfg(kinematic_enabled=True),
                collision_props=sim_utils.CollisionPropertiesCfg()))
        # Placement solver is disabled by the caller: analytical geometry has no USD helper.
        reader=StateReader(cfg.embodiment,cfg.axis_mapping_xyzw)
        reader.gripper=embodiment.get_gripper()
        task=StableLiftTask(reader)
        return IsaacLabArenaEnvironment(name=self.name,embodiment=embodiment,
            scene=Scene(assets=[obj,table,GroundPlane(initial_pose=Pose(position_xyz=(0.,0.,-1.5))),DomeLight()]),
            task=task,env_cfg_callback=set_control_rate_50hz,
            episode_recorder_terms={'pebx_terminal':EpisodeRecorderTermCfg(func=terminal_record,params={})})
