"""GPU module: import only after SimulationAppContext has started."""
import copy
from functools import partial
import torch
from isaaclab.managers import TerminationTermCfg
from isaaclab_arena.tasks.task_base import TaskBase
from isaaclab_arena.tasks.task_termination_cfg import TaskTerminationCfg
from isaaclab_arena.progress_tracking.completion_criteria import CompletionCriteria
from isaaclab_arena.metrics.success_rate import SuccessRateMetric
from .judge import StableLiftJudge, robot_hard_failures
from ..control.geometry import rotate
import numpy as np


class StableLiftTask(TaskBase):
    def __init__(self, reader):
        super().__init__(episode_length_s=15.5,task_description='Lift the free cuboid and hold it stably.')
        self.reader = reader
        self.judge = StableLiftJudge()
        self.last_tick = None
        self.last_episode_step = -1
        self.ready = False
        self.terminal_evidence = None
        self.current_observation = None
        self.episode_id = 'development'

    def get_scene_cfg(self):
        return None

    def get_events_cfg(self):
        return None

    def get_mimic_env_cfg(self, arm_mode):
        raise NotImplementedError('PEBX v0.1 freezes mimic=False')

    def get_metrics(self):
        return [SuccessRateMetric()]

    def get_termination_cfg(self):
        return TaskTerminationCfg(timeout_s=15.5,
            success=[CompletionCriteria(name='stable_lift',predicate_sequence=[task_success])],
            failures={'pebx_failure':TerminationTermCfg(func=task_failure,params={})})

    def sample(self, env):
        tick = int(env.common_step_counter)
        if self.last_tick == tick:
            return self.judge.terminal if self.ready else None
        step = int(env.episode_length_buf[0].item())
        if step < self.last_episode_step:
            self.ready = False
        self.last_tick, self.last_episode_step = tick, step
        obs = self.reader.read(env,self.episode_id)
        self.current_observation = obs
        if obs.sim_time_s < .5-1e-9:
            return None
        if not self.ready:
            self.judge.reset(obs)
            self.ready = True
            self.terminal_evidence = None
        # Bounding cuboid world z radius excludes support from the procedural table.
        q, size = obs.object_pose_w.quaternion_xyzw, obs.object_size_m
        axes = [rotate(q, np.eye(3)[i]) for i in range(3)]
        radius_z = sum(abs(axes[i][2])*size[i]/2 for i in range(3))
        clear = obs.object_pose_w.position_m[2]-radius_z > .01
        from .state_reader import array
        limits = array(env.scene['robot'].data.joint_pos_limits)[0]
        result = self.judge.update(obs,static_support_clear=clear,
                                  hard_failures=robot_hard_failures(obs, limits))
        if result is not None:
            # Saved during termination computation, before auto-reset. Recorder copies it.
            self.terminal_evidence = dict(result=copy.deepcopy(result),observation=obs.model_dump())
        return result


def task_success(env):
    result = env.pebx_task.sample(env)
    return torch.tensor([bool(result and result['task_success'])],device=env.device)


def task_failure(env):
    result = env.pebx_task.sample(env)
    return torch.tensor([bool(result and not result['task_success'])],device=env.device)


def terminal_record(env, env_id):
    env.pebx_task.sample(env)
    return {'pebx_terminal_evidence':copy.deepcopy(env.pebx_task.terminal_evidence)}
