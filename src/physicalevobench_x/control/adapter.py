import numpy as np
from .geometry import compose, invert, relative, multiply, inverse, rotvec
from ..core.schemas import Gripper


class EmbodimentAdapter:
    """Convert desired world TCP pose into root-frame relative control action.

    control_to_tcp is measured from current pad midpoint and calibrated axes at
    every tick, including changing Robotiq geometry. Panda's native action offset
    is already included in current_control_w; never add it again here.
    """
    def __init__(self, embodiment, scale=.5, max_translation_m=.02, max_rotation_rad=.15):
        if embodiment not in ('franka_panda', 'franka_robotiq'):
            raise ValueError(embodiment)
        if scale <= 0:
            raise ValueError('scale must be positive')
        self.embodiment, self.scale = embodiment, scale
        self.max_translation_m, self.max_rotation_rad = max_translation_m, max_rotation_rad

    def encode(self, command, root_w, current_control_w, control_to_tcp):
        desired_w = compose(command.tcp_pose_w, invert(control_to_tcp))
        current = relative(root_w, current_control_w)
        desired = relative(root_w, desired_w)
        dp = np.asarray(desired.position_m) - current.position_m
        dr = rotvec(multiply(desired.quaternion_xyzw, inverse(current.quaternion_xyzw)))
        def limit(vector, bound):
            n = np.linalg.norm(vector)
            return vector * min(1., bound/max(n, 1e-12))
        # This is a pose increment, not a velocity. No second multiplication by dt.
        delta = np.r_[limit(dp, self.max_translation_m), limit(dr, self.max_rotation_rad)] / self.scale
        close = command.gripper == Gripper.CLOSE
        gripper = (-1. if close else 1.) if self.embodiment == 'franka_panda' else (1. if close else 0.)
        return np.r_[delta, gripper]
