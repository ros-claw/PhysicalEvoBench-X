"""Trusted full-horizon observer used only by native measurement diagnostics."""
from .pose_window import PoseWindowJudge,PoseWindowConfig
from ..sim.judge import StableLiftJudge,JudgeConfig


class FullHorizonComparison:
    def __init__(self,config=PoseWindowConfig()):
        self.config=config
        self.candidate=PoseWindowJudge(config)
        self.legacy=StableLiftJudge(JudgeConfig())

    def reset(self,initial):
        self.start_time=initial.sim_time_s
        self.candidate.reset(initial);self.legacy.reset(initial)
        self.terminal=None

    def update(self,obs,*,hard_failures=(),static_support_clear=True):
        if self.terminal is not None:return self.terminal
        self.candidate.update(obs,hard_failures=hard_failures,static_support_clear=static_support_clear)
        self.legacy.update(obs,hard_failures=hard_failures,static_support_clear=static_support_clear)
        failures=list(hard_failures)
        if any(p<lo or p>hi for p,lo,hi in zip(obs.object_pose_w.position_m,
                    obs.workspace_min_m,obs.workspace_max_m)):failures.append('OBJECT_OUT_OF_BOUNDS')
        elapsed=obs.sim_time_s-self.start_time
        if failures or elapsed>=self.config.timeout_s-1e-12:
            candidate=self.candidate.terminal
            self.terminal=dict(task_success=bool(candidate and candidate['task_success'] and not failures),
                termination_reason=failures[0] if failures else 'DIAGNOSTIC_HORIZON_COMPLETE',
                completion_time_s=min(elapsed,self.config.timeout_s),constraint_violations=failures,
                hold_time_s=self.candidate.max_hold,max_lift_m=self.candidate.max_lift)
        return self.terminal
