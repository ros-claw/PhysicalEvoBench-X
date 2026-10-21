"""Authoritative CPU-testable judge, also consumed by Arena termination terms."""
from dataclasses import dataclass
import math
import numpy as np
from ..control.geometry import relative, angle


@dataclass(frozen=True)
class JudgeConfig:
    lift_m: float = .08
    hold_s: float = 1.
    drift_m: float = .015
    drift_rad: float = math.pi/12
    linear_speed_mps: float = .03
    angular_speed_radps: float = .5
    timeout_s: float = 15.


class StableLiftJudge:
    def __init__(self, config=JudgeConfig()):
        self.config = config

    def reset(self, initial):
        self.z0 = initial.object_pose_w.position_m[2]
        self.start_time = self.last_time = initial.sim_time_s
        self.hold_start = None
        self.anchor = None
        self.max_lift = 0.
        self.max_hold = 0.
        self.terminal = None

    def update(self, obs, *, hard_failures=(), static_support_clear=True):
        if self.terminal is not None:
            return self.terminal
        if obs.sim_time_s < self.last_time:
            raise ValueError('Nonmonotonic simulation time')
        self.last_time = obs.sim_time_s
        elapsed = obs.sim_time_s-self.start_time
        lift = obs.object_pose_w.position_m[2]-self.z0
        self.max_lift = max(self.max_lift, lift)
        failures = list(hard_failures)
        if any(p < lo or p > hi for p,lo,hi in zip(obs.object_pose_w.position_m, obs.workspace_min_m, obs.workspace_max_m)):
            failures.append('OBJECT_OUT_OF_BOUNDS')
        if failures:
            self.terminal = self._result(False, failures[0], elapsed, failures)
            return self.terminal
        relative_pose = relative(obs.tcp_pose_w, obs.object_pose_w)
        qualifies = (lift >= self.config.lift_m-1e-12 and static_support_clear
            and np.linalg.norm(obs.object_linear_velocity_w) <= self.config.linear_speed_mps
            and np.linalg.norm(obs.object_angular_velocity_w) <= self.config.angular_speed_radps)
        if qualifies and self.anchor is not None:
            qualifies = (np.linalg.norm(np.asarray(relative_pose.position_m)-self.anchor.position_m) <= self.config.drift_m
                and angle(relative_pose.quaternion_xyzw, self.anchor.quaternion_xyzw) <= self.config.drift_rad)
        if not qualifies:
            self.hold_start, self.anchor = None, None
        elif self.hold_start is None:
            self.hold_start, self.anchor = obs.sim_time_s, relative_pose
        if self.hold_start is not None:
            held = obs.sim_time_s-self.hold_start
            self.max_hold = max(self.max_hold, held)
            if held >= self.config.hold_s-1e-12 and elapsed <= self.config.timeout_s+1e-12:
                self.terminal = self._result(True, 'SUCCESS', elapsed, [])
        if self.terminal is None and elapsed >= self.config.timeout_s-1e-12:
            self.terminal = self._result(False, 'TIME_LIMIT', self.config.timeout_s, [])
        return self.terminal

    def _result(self, success, reason, time, failures):
        return dict(task_success=success, termination_reason=reason, completion_time_s=min(time, 15.),
            constraint_violations=failures, hold_time_s=self.max_hold, max_lift_m=self.max_lift)
