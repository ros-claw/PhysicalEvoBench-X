"""Development candidate based on observed pose path length, not native velocity.

This class is not registered as the benchmark judge. It requires separate
physical validation and a new protocol freeze before any formal experiment.
"""
from collections import deque
from dataclasses import dataclass,fields
import math
import numpy as np
from ..control.geometry import angle, relative


@dataclass(frozen=True)
class PoseWindowConfig:
    version: str = 'pose_path_window_candidate_v1'
    lift_m: float = .08
    hold_s: float = 1.
    drift_m: float = .015
    drift_rad: float = math.pi/12
    linear_speed_mps: float = .03
    angular_speed_radps: float = .5
    timeout_s: float = 15.
    window_s: float = .10
    max_gap_s: float = .025

    def __post_init__(self):
        values=[self.lift_m,self.hold_s,self.drift_m,self.drift_rad,self.linear_speed_mps,
                self.angular_speed_radps,self.timeout_s,self.window_s,self.max_gap_s]
        if any(type(v) not in (int,float) or not math.isfinite(v) or v<=0 for v in values):
            raise ValueError('Positive finite measurement settings required')
        if self.version!='pose_path_window_candidate_v1':
            raise ValueError('Unsupported measurement candidate version')
        if not self.max_gap_s<=self.window_s<=self.hold_s<self.timeout_s:
            raise ValueError('Require max_gap <= window <= hold < timeout')


def load_pose_window_config(path):
    import yaml
    from pathlib import Path
    data=yaml.safe_load(Path(path).read_text())
    metadata={'status','formal_result_eligible','velocity_source','default_benchmark_judge_replaced'}
    if (not isinstance(data,dict) or set(data)!={f.name for f in fields(PoseWindowConfig)}|metadata
        or data['status']!='CANDIDATE_NOT_PHYSICALLY_VALIDATED'
        or data['formal_result_eligible'] is not False or data['default_benchmark_judge_replaced'] is not False
        or data['velocity_source']!='observed_world_pose_path_length'):
        raise ValueError('Invalid experimental measurement configuration')
    return PoseWindowConfig(**{k:v for k,v in data.items() if k not in metadata})


class PoseWindowJudge:
    """Continuous observed hold with path-length speed in a trailing window.

    Summing segment lengths prevents cancellation of observed back-and-forth
    motion. It cannot certify motion faster than the sampling rate.
    """
    def __init__(self,config=PoseWindowConfig()):
        self.config=config

    def reset(self,initial):
        self.start_time=self.last_time=initial.sim_time_s
        self.z0=initial.object_pose_w.position_m[2]
        self.last_pose=initial.object_pose_w
        self.last_tcp=initial.tcp_pose_w
        self.history=deque([(initial.sim_time_s,initial.object_pose_w)])
        self.hold_start=self.anchor=None
        self.max_lift=self.max_hold=0.
        self.terminal=None
        self.gap_resets=0
        self.last_window_speeds=None

    def _speeds(self,t):
        cutoff=t-self.config.window_s
        while len(self.history)>2 and self.history[1][0]<=cutoff+1e-12:
            self.history.popleft()
        if self.history[0][0]>cutoff+1e-12:
            return None
        linear=angular=covered=0.
        for (ta,a),(tb,b) in zip(self.history,list(self.history)[1:]):
            overlap=max(0.,min(tb,t)-max(ta,cutoff))
            if overlap<=0:continue
            fraction=overlap/(tb-ta)
            linear+=float(np.linalg.norm(np.array(b.position_m)-a.position_m))*fraction
            angular+=angle(b.quaternion_xyzw,a.quaternion_xyzw)*fraction
            covered+=overlap
        if covered<self.config.window_s-1e-10:
            return None
        return linear/self.config.window_s,angular/self.config.window_s

    def update(self,obs,*,hard_failures=(),static_support_clear=True):
        if self.terminal is not None:return self.terminal
        t=obs.sim_time_s
        if t<self.last_time:raise ValueError('Nonmonotonic measurement clock')
        elapsed=t-self.start_time
        lift=obs.object_pose_w.position_m[2]-self.z0
        self.max_lift=max(self.max_lift,lift)
        failures=list(hard_failures)
        if any(p<lo or p>hi for p,lo,hi in zip(obs.object_pose_w.position_m,
                    obs.workspace_min_m,obs.workspace_max_m)):
            failures.append('OBJECT_OUT_OF_BOUNDS')
        if failures:
            self.terminal=self._result(False,failures[0],elapsed,failures)
            return self.terminal
        gap=t-self.last_time
        if gap==0:
            def same_pose(a,b):
                return (a.position_m==b.position_m and angle(a.quaternion_xyzw,b.quaternion_xyzw)<=1e-12)
            if not same_pose(obs.object_pose_w,self.last_pose) or not same_pose(obs.tcp_pose_w,self.last_tcp):
                raise ValueError('Different poses at the same measurement timestamp')
            return self.terminal
        if gap>self.config.max_gap_s+1e-12:
            self.history.clear()
            self.hold_start=self.anchor=None
            self.gap_resets+=1
        self.history.append((t,obs.object_pose_w))
        self.last_time,self.last_pose=t,obs.object_pose_w
        self.last_tcp=obs.tcp_pose_w
        speeds=self._speeds(t)
        self.last_window_speeds=speeds
        qualifies=(speeds is not None and lift>=self.config.lift_m-1e-12 and static_support_clear
                   and speeds[0]<=self.config.linear_speed_mps+1e-12
                   and speeds[1]<=self.config.angular_speed_radps+1e-12)
        rel=relative(obs.tcp_pose_w,obs.object_pose_w)
        if qualifies and self.anchor is not None:
            qualifies=(np.linalg.norm(np.array(rel.position_m)-self.anchor.position_m)<=self.config.drift_m
                       and angle(rel.quaternion_xyzw,self.anchor.quaternion_xyzw)<=self.config.drift_rad)
        if not qualifies:
            self.hold_start=self.anchor=None
        elif self.hold_start is None:
            self.hold_start,self.anchor=t,rel
        if self.hold_start is not None:
            held=t-self.hold_start
            self.max_hold=max(self.max_hold,held)
            if held>=self.config.hold_s-1e-12 and elapsed<=self.config.timeout_s+1e-12:
                self.terminal=self._result(True,'SUCCESS',elapsed,[])
        if self.terminal is None and elapsed>=self.config.timeout_s-1e-12:
            self.terminal=self._result(False,'TIME_LIMIT',self.config.timeout_s,[])
        return self.terminal

    def _result(self,success,reason,elapsed,failures):
        return dict(task_success=success,termination_reason=reason,
                    completion_time_s=min(elapsed,self.config.timeout_s),
                    constraint_violations=failures,hold_time_s=self.max_hold,max_lift_m=self.max_lift)
