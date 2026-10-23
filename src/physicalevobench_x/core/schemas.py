from typing import Literal
from enum import Enum
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from .hashing import digest


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True, allow_inf_nan=False)


LEGACY_BOUNDS = {
    'grasp_height_fraction': (0.25, 0.75),
    'pregrasp_clearance_m': (0.04, 0.12),
    'settle_time_s': (0.10, 0.80),
    'lift_vmax_mps': (0.03, 0.20),
    'lift_amax_mps2': (0.10, 0.80),
}

BOUNDS = {
    'grasp_height_fraction': (.45, .75),
    'pregrasp_clearance_m': (.07, .12),
    'settle_time_s': (.10, .50),
    'lift_vmax_mps': (.03, .10),
    'lift_amax_mps2': (.10, .80),
}


def bounds_for(skill):
    return LEGACY_BOUNDS if skill.controller_family == 'grasp_lift_state_v1' else BOUNDS


def skill_schema(schema):
    schema['allOf'] = [{'if': {'properties': {'controller_family': {'const': 'grasp_lift_state_v2'}}},
        'then': {'properties': {'parameters': {'properties': {
            name: {'minimum': lo, 'maximum': hi} for name, (lo, hi) in BOUNDS.items()}}}}}]


class Parameters(StrictModel):
    grasp_height_fraction: float = Field(ge=.25, le=.75, strict=True)
    pregrasp_clearance_m: float = Field(ge=.04, le=.12, strict=True)
    settle_time_s: float = Field(ge=.10, le=.80, strict=True)
    lift_vmax_mps: float = Field(ge=.03, le=.20, strict=True)
    lift_amax_mps2: float = Field(ge=.10, le=.80, strict=True)


class Requirements(StrictModel):
    end_effector: Literal['parallel_jaw']
    action_interface: Literal['cartesian_pose_and_binary_gripper']


class SkillSpec(StrictModel):
    model_config = ConfigDict(json_schema_extra=skill_schema)
    schema_version: Literal['physicalevobench_x.skillspec.v1']
    controller_family: Literal['grasp_lift_state_v1', 'grasp_lift_state_v2']
    parameters: Parameters
    requirements: Requirements

    @model_validator(mode='after')
    def versioned_bounds(self):
        for name, (lo, hi) in bounds_for(self).items():
            if not lo <= getattr(self.parameters, name) <= hi:
                raise ValueError('Parameter outside controller version bounds: '+name)
        return self

    @property
    def semantic_hash(self):
        return digest(self)

    @classmethod
    def initial(cls):
        return cls(schema_version='physicalevobench_x.skillspec.v1',
                   controller_family='grasp_lift_state_v2',
                   parameters=Parameters(grasp_height_fraction=.5, pregrasp_clearance_m=.07,
                                         settle_time_s=.3, lift_vmax_mps=.1, lift_amax_mps2=.3),
                   requirements=Requirements(end_effector='parallel_jaw',
                       action_interface='cartesian_pose_and_binary_gripper'))


Vec3 = tuple[float, float, float]
Quat = tuple[float, float, float, float]


class Pose(StrictModel):
    position_m: Vec3
    quaternion_xyzw: Quat

    @field_validator('quaternion_xyzw')
    @classmethod
    def unit_quaternion(cls, v):
        if abs(sum(x*x for x in v) - 1) > 1e-6:
            raise ValueError('Quaternion must be unit length, xyzw')
        return v


class Gripper(str, Enum):
    OPEN = 'OPEN'
    CLOSE = 'CLOSE'


class CanonicalCommand(StrictModel):
    tcp_pose_w: Pose
    gripper: Gripper


class ObservationFrame(StrictModel):
    schema_version: Literal['physicalevobench_x.observation.v1']
    episode_id: str
    sim_time_s: float = Field(ge=0)
    joint_positions: tuple[float, ...]
    joint_velocities: tuple[float, ...]
    tcp_pose_w: Pose
    object_pose_w: Pose
    object_linear_velocity_w: Vec3
    object_angular_velocity_w: Vec3
    object_size_m: Vec3
    gripper_opening_width_m: float = Field(ge=0)
    workspace_min_m: Vec3
    workspace_max_m: Vec3


    @model_validator(mode='after')
    def coherent_geometry(self):
        if len(self.joint_positions) != len(self.joint_velocities):
            raise ValueError('Joint positions/velocities must have matching lengths')
        if any(size <= 0 for size in self.object_size_m):
            raise ValueError('Known object dimensions must be positive')
        if any(lo >= hi for lo,hi in zip(self.workspace_min_m,self.workspace_max_m)):
            raise ValueError('Workspace lower bounds must be below upper bounds')
        return self


class EpisodeResult(StrictModel):
    episode_id: str
    condition_id: str
    split: str
    phase: Literal['exploration', 'validation', 'evaluation', 'source_audit', 'calibration']
    candidate_index: int = Field(ge=0)
    skill_hash: str = Field(pattern=r'^[0-9a-f]{64}$')
    backend: Literal['fake', 'physx']
    task_success: bool
    constraint_violations: tuple[str, ...] = ()
    max_lift_m: float = Field(ge=0)
    completion_time_s: float = Field(ge=0, le=15)
    hold_time_s: float = Field(ge=0)
    termination_reason: str
    infra_failure: str | None = None
    attempt_index: int = Field(ge=0, le=1)
    simulator_steps: int = Field(ge=0)
    sim_time_s: float = Field(ge=0)
    wall_time_s: float = Field(ge=0)
    trajectory_path: str | None = None
    trajectory_sha256: str | None = Field(default=None, pattern=r'^[0-9a-f]{64}$')

    def public_feedback(self):
        return self.model_dump(include={'task_success', 'constraint_violations', 'max_lift_m',
            'completion_time_s', 'hold_time_s', 'termination_reason'})
