import math
import numpy as np
from ..core.schemas import CanonicalCommand, Pose, Gripper
from .geometry import rotate
from .trajectory import segment


class GraspLiftExecutor:
    """Frozen state machine. Only public observations, never evaluator state."""
    def reset(self, skill, initial):
        self.skill = skill
        self.stage = 'APPROACH'
        self.stage_start = self.last_time = initial.sim_time_s
        p = skill.parameters
        local = (0., 0., (p.grasp_height_fraction-.5)*initial.object_size_m[2])
        self.grasp = np.asarray(initial.object_pose_w.position_m)+rotate(initial.object_pose_w.quaternion_xyzw, local)
        self.pre = self.grasp + (0., 0., p.pregrasp_clearance_m)
        x,y,z,w = initial.object_pose_w.quaternion_xyzw
        yaw = math.atan2(2*(w*z+x*y), 1-2*(y*y+z*z))
        # canonical z points toward object, canonical x follows object x.
        self.orientation = (math.cos(yaw/2), math.sin(yaw/2), 0., 0.)
        self.start = np.asarray(initial.tcp_pose_w.position_m)
        self.goal = self.pre.copy()
        self.target = self.start.copy()
        self.stage_times = {}

    def _transition(self, stage, obs, goal):
        self.stage_times[self.stage] = obs.sim_time_s-self.stage_start
        self.stage, self.stage_start = stage, obs.sim_time_s
        # v2 joins reference segments continuously. Restarting at the measured
        # TCP after a tolerated tracking error introduces a one-tick jump that
        # can exceed the learner's requested reference speed. The lift endpoint
        # remains anchored to the measured TCP at entry, as specified below.
        self.start = (self.target.copy() if self.skill.controller_family == 'grasp_lift_state_v2'
                      else np.asarray(obs.tcp_pose_w.position_m))
        self.goal = np.asarray(goal)

    def step(self, obs):
        if obs.sim_time_s < self.last_time:
            raise ValueError('Simulation clock moved backwards; reset executor')
        self.last_time = obs.sim_time_s
        t = obs.sim_time_s-self.stage_start
        p = self.skill.parameters
        if self.stage in ('APPROACH', 'DESCEND', 'LIFT'):
            vmax, amax = (p.lift_vmax_mps, p.lift_amax_mps2) if self.stage == 'LIFT' else (.1, .3)
            self.target, done = segment(self.start, self.goal, t, vmax, amax)
            error = np.linalg.norm(np.asarray(obs.tcp_pose_w.position_m)-self.goal)
            if done and error <= .005:
                if self.stage == 'APPROACH':
                    self._transition('DESCEND', obs, self.grasp)
                elif self.stage == 'DESCEND':
                    self._transition('CLOSE', obs, self.grasp)
                else:
                    self._transition('HOLD', obs, self.goal)
        elif self.stage == 'CLOSE':
            self._transition('SETTLE', obs, self.grasp)
        elif self.stage == 'SETTLE' and t >= p.settle_time_s:
            # Fixed once on entry; no moving object-following lift target.
            self._transition('LIFT', obs, np.asarray(obs.tcp_pose_w.position_m)+(0.,0.,.12))
        command = CanonicalCommand(tcp_pose_w=Pose(position_m=tuple(self.target),
            quaternion_xyzw=self.orientation), gripper=Gripper.OPEN if self.stage in ('APPROACH', 'DESCEND') else Gripper.CLOSE)
        if np.any(self.target < obs.workspace_min_m) or np.any(self.target > obs.workspace_max_m):
            raise ValueError('JOINT_OR_WORKSPACE_LIMIT')
        return command
