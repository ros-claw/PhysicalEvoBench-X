# Pinned upstream audit (2026-10-21)

Inspected actual local source at Arena `c7edf3a9d5d8276565208f72422f8f8a0806d6cf` and Lab `91a0906f93802eb859192dcb0bca879f891e92d6`. No tracked upstream code was modified.

| Interface | Confirmed source | Project consumer |
|---|---|---|
| Startup context / CLI | `isaaclab_arena/utils/isaaclab_utils/simulation_app.py`, `cli/isaaclab_arena_cli.py` | `sim/launch.py`, `sim/commands.py` |
| Typed factory and builder | `environments/arena_environment_factory.py`, `arena_env_builder.py`, `arena_env_builder_cfg.py` | `sim/arena_factory.py`, `sim/runner.py` |
| Task contract | `tasks/task_base.py`, `tasks/task_termination_cfg.py` | `sim/stable_lift_task.py` implements all five abstract methods |
| Completion predicates | `tasks/lift_object_task.py`, `progress_tracking/completion_criteria.py` | shared authoritative judge used by success/failure predicates |
| Pre-reset evidence | `recording/episode_recorder_manager.py`, `environments/isaaclab_arena_manager_based_env.py` | terminal copy during termination, copied by recorder |
| Body/pose/quaternion | `environments/arena_world.py` | xyzw detached public state |
| Pad midpoint | `embodiments/franka/franka.py`, `embodiments/droid/droid.py` | `tool_leftfinger` and `tool_rightfinger` targets |
| Gripper meters | `embodiments/gripper.py` | `get_opening_width_m(world)` |
| Control point | Panda hand + local z 0.107; DROID base_link | full SE(3), root-frame delta, scale 0.5 |
| Binary actions | Franka action config / DROID actions.py | Panda OPEN +1 / CLOSE -1; DROID OPEN 0 / CLOSE +1 |
| Procedural assets | `assets/object.py`, `object_library.py` | explicit CuboidCfg dimensions, no USD bounding helper |
| Body mass | Lab's `assets/rigid_object/base_rigid_object_data.py` and backend data | `data.body_mass` backend readback path; pending execution |
| Image | `docker/Dockerfile.isaaclab_arena` | Isaac Sim 6.1.0; full upstream dev target reused |

Arena's Python package reports 0.3.0; the git SHA is the authority. The selected upstream dev image also requires Isaac-GR00T's pinned submodule even though the benchmark does not use a GR00T policy. The checkout command retrieves that dependency without smudging model payloads.

Registry manifest inspection confirmed the amd64 image digest listed in the dependency lock. Local pull/launch is a separate gate and remains recorded in evidence. Source inspection is not GPU behavior validation.
