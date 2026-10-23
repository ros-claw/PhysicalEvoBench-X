"""Versioned on-disk runtime constants, consumed by the real scene and judge."""
from pathlib import Path
import yaml
from .judge import JudgeConfig
from ..core.schemas import BOUNDS

ROOT = Path(__file__).resolve().parents[3]


def load_runtime(embodiment):
    task=yaml.safe_load((ROOT/'configs/tasks/stable_lift_dev.yaml').read_text())
    body=yaml.safe_load((ROOT/'configs/embodiments'/f'{embodiment}.yaml').read_text())
    if (task['physics_dt_s']!=.005 or task['control_dt_s']!=.02
        or task['settle_s']!=.5 or task['execution_s']!=15.
        or task['object_size_m']!=[.045,.045,.065] or body['native_action_scale']!=.5):
        raise ValueError('Runtime config requires a new supported protocol implementation')
    if task.get('parameter_bounds')!={k:list(v) for k,v in BOUNDS.items()}:
        raise ValueError('Task bounds and executable SkillSpec bounds differ')
    expected=('panda_hand',[0.,0.,.107],1.,-1.) if embodiment=='franka_panda' else ('base_link',[0.,0.,0.],0.,1.)
    actual=(body['native_control_body'],body['native_control_offset_m'],body['open_command'],body['close_command'])
    if actual!=expected:
        raise ValueError('Adapter metadata does not match the supported native interface')
    judge=JudgeConfig(lift_m=task['lift_height_m'],hold_s=task['hold_s'],drift_m=task['position_drift_m'],
        drift_rad=task['rotation_drift_rad'],linear_speed_mps=task['linear_speed_mps'],
        angular_speed_radps=task['angular_speed_radps'],timeout_s=task['execution_s'])
    return task,body,judge
