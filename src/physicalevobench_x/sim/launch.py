"""Real upstream reset/step probe. Imported ONLY by explicit GPU commands."""
import sys
from pathlib import Path
from ..core.hashing import write_json


def probe(embodiment, output):
    if sys.version_info[:2] != (3,12):
        raise RuntimeError('Pinned Isaac Sim requires Python 3.12')
    # These upstream imports deliberately follow policy_runner.py startup ordering.
    from isaaclab_arena.cli.isaaclab_arena_cli import get_isaaclab_arena_cli_parser
    from isaaclab_arena.utils.isaaclab_utils.simulation_app import SimulationAppContext
    args = get_isaaclab_arena_cli_parser().parse_args([])
    with SimulationAppContext(args):
        import torch
        from isaaclab_arena_environments.lift_object_environment import LiftObjectEnvironment, LiftObjectEnvironmentCfg
        from isaaclab_arena.environments.arena_env_builder import ArenaEnvBuilder
        from isaaclab_arena.environments.arena_env_builder_cfg import ArenaEnvBuilderCfg
        names = {'franka_panda': 'franka_ik', 'franka_robotiq': 'droid_differential_ik'}
        arena_env = LiftObjectEnvironment().build(LiftObjectEnvironmentCfg(embodiment=names[embodiment]))
        env, cfg = ArenaEnvBuilder(arena_env, ArenaEnvBuilderCfg(num_envs=1, solve_relations=False,
                                                              resolve_on_reset=False,
                recorder_dataset_export_dir_path=str(Path(output).parent/('arena_probe_'+embodiment)),
                recorder_dataset_filename='probe')).make_registered_and_return_cfg()
        base = env.unwrapped
        if abs(base.physics_dt-.005)>1e-9 or abs(base.step_dt-.02)>1e-9:
            raise RuntimeError('Control frequency mismatch')
        obs, info = env.reset()
        action = torch.zeros((1, base.action_manager.total_action_dim), device=base.device)
        # Hold arm, open native gripper. A successful probe is not a grasp check.
        action[:, -1] = 1. if embodiment == 'franka_panda' else 0.
        for _ in range(10):
            env.step(action)
        write_json(Path(output), dict(status='GPU_RESET_STEP_VERIFIED', embodiment=embodiment,
            physics_dt=base.physics_dt, control_dt=base.step_dt, steps=10, task='upstream_lift_object',
            stable_lift_verified=False, formal_result_eligible=False))
        env.close()
