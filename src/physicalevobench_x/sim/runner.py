"""Real development runner. Requires a live SimulationAppContext.

One environment per episode keeps condition dynamics isolated until a reusable
reset implementation has physical validation. This is deliberately conservative
and must be timed before any pilot; it is not a claimed throughput optimization.
"""
import time
import uuid
from pathlib import Path
import numpy as np
import torch
from isaaclab_arena.environments.arena_env_builder import ArenaEnvBuilder
from isaaclab_arena.environments.arena_env_builder_cfg import ArenaEnvBuilderCfg
from .arena_factory import StableLiftEnvironment, StableLiftEnvironmentCfg
from .state_reader import array
from ..control.adapter import EmbodimentAdapter
from ..control.grasp_lift_executor import GraspLiftExecutor
from ..core.schemas import EpisodeResult
from ..core.hashing import file_digest, write_json, append_json
from ..core.conditions import validate_condition


class PhysXRunner:
    def __init__(self, embodiment, output):
        self.embodiment, self.output = embodiment, Path(output)
        self.output.mkdir(parents=True,exist_ok=True)
        package_root=Path(__file__).resolve().parents[1]
        self.frozen_files={str(p):file_digest(p) for p in package_root.rglob('*.py')}
        repo_root=package_root.parents[1]
        self.frozen_files.update({str(p):file_digest(p) for p in (repo_root/'configs').rglob('*.yaml')})
        import yaml
        task_config=yaml.safe_load((repo_root/'configs/tasks/stable_lift_dev.yaml').read_text())
        self.configured_validation=task_config.get('development_validated',False)
        lock=yaml.safe_load((repo_root/'dependencies.lock.yaml').read_text())
        self.frozen_files[str(repo_root/'dependencies.lock.yaml')]=file_digest(repo_root/'dependencies.lock.yaml')
        assets=lock.get('assets',{})
        if assets.get('verified'):
            inventory_path=repo_root/assets['inventory_path']
            if file_digest(inventory_path)!=assets['inventory_sha256']:
                raise RuntimeError('Asset inventory changed')
            import json
            inventory=json.loads(inventory_path.read_text())
            self.frozen_files[str(inventory_path)]=assets['inventory_sha256']
            for name,record in inventory['files'].items():
                path=Path(name) if Path(name).is_absolute() else repo_root/name
                if file_digest(path)!=record['sha256']:
                    raise RuntimeError('Asset checksum mismatch: '+name)
                self.frozen_files[str(path)]=record['sha256']
        write_json(self.output/'runtime_inputs.json',dict(source_files=self.frozen_files,
            embodiment=embodiment,configured_development_validation=self.configured_validation,
            validation_authority='external_freeze_and_acceptance_audit',formal_result_eligible=False))

    def run(self, *, skill, condition, phase, candidate_index, attempt_index):
        validate_condition(condition)
        if any(file_digest(path)!=checksum for path,checksum in self.frozen_files.items()):
            raise RuntimeError('Runtime source/config/asset changed; refusing to mix versions in one run')
        started=time.monotonic()
        self._active_episode_id=uuid.uuid4().hex
        self._steps=0
        self._timings={}
        try:
            result=self._run(skill=skill,condition=condition,phase=phase,candidate_index=candidate_index,attempt_index=attempt_index)
        except Exception as exc:
            # A returned infrastructure failure is replayable and charged only
            # as actual execution cost. Partial trace/error files remain intact.
            write_json(self.output/(self._active_episode_id+'_infrastructure.json'),dict(
                error=type(exc).__name__,message=str(exc),condition=condition,
                simulator_steps=self._steps*4,wall_time_s=time.monotonic()-started))
            try:
                from isaaclab_arena.utils.isaaclab_utils.simulation_app import teardown_simulation_app
                teardown_simulation_app()
            except Exception as cleanup_error:
                write_json(self.output/(self._active_episode_id+'_cleanup_error.json'),
                    dict(error=type(cleanup_error).__name__,message=str(cleanup_error)))
            result=EpisodeResult(episode_id=self._active_episode_id,condition_id=condition['condition_id'],
                split=condition['split'],phase=phase,candidate_index=candidate_index,skill_hash=skill.semantic_hash,
                backend='physx',task_success=False,max_lift_m=0.,completion_time_s=15.,hold_time_s=0.,
                termination_reason='INFRA_FAILURE',infra_failure=type(exc).__name__,attempt_index=attempt_index,
                simulator_steps=self._steps*4,sim_time_s=self._steps*.02,wall_time_s=time.monotonic()-started)
        metadata=self.output/(self._active_episode_id+'.json')
        if metadata.exists():
            import json
            data=json.loads(metadata.read_text())
            self._timings['total_episode_s']=time.monotonic()-started
            data['timings']=self._timings
            write_json(metadata,data)
        return result.model_copy(update={'wall_time_s':time.monotonic()-started})

    @torch.inference_mode()
    def _run(self, *, skill, condition, phase, candidate_index, attempt_index):
        started=time.monotonic()
        episode_id=self._active_episode_id
        axis=(0.,0.,0.,1.) if self.embodiment=='franka_panda' else (0.,2**-.5,0.,2**-.5)
        arena=StableLiftEnvironment().build(StableLiftEnvironmentCfg(embodiment=self.embodiment,
            axis_mapping_xyzw=axis, mass_kg=condition['mass_kg'],offset_xy_m=tuple(condition['offset_xy_m']),
            yaw_rad=condition['yaw_rad']))
        env,cfg=ArenaEnvBuilder(arena,ArenaEnvBuilderCfg(num_envs=1,solve_relations=False,
            resolve_on_reset=False,seed=condition['reset_seed'],mimic=False,
            recorder_dataset_export_dir_path=str(self.output/episode_id),recorder_dataset_filename='arena')).make_registered_and_return_cfg()
        base=env.unwrapped
        base.pebx_task = arena.task
        base.configure_episode_limit(1)
        steps, states, actions = 0, [], []
        self._timings['scene_build_s']=time.monotonic()-started
        try:
            if abs(base.physics_dt-.005)>1e-9 or abs(base.step_dt-.02)>1e-9:
                raise RuntimeError('Control rate does not match lock')
            tick=time.monotonic()
            env.reset(seed=condition['reset_seed'])
            self._timings['reset_s']=time.monotonic()-tick
            task,reader=arena.task,arena.task.reader
            task.episode_id=episode_id
            task.last_tick=None
            task.last_episode_step=-1
            task.ready=False
            if base.action_manager.total_action_dim != 7:
                raise RuntimeError('Native action dimension/order changed')
            mass=array(base.scene['pebx_object'].data.body_mass).reshape(-1)
            if not np.allclose(mass,condition['mass_kg'],atol=1e-5):
                raise RuntimeError('Mass backend readback mismatch')
            robot=base.scene['robot']
            def finite_metadata(value):
                if isinstance(value,list):
                    return [finite_metadata(v) for v in value]
                if isinstance(value,float) and not np.isfinite(value):
                    return str(value)  # explicit unbounded/invalid metadata, never substitute zero
                return value
            effective_robot=dict(joint_names=list(robot.joint_names),
                joint_position_limits=finite_metadata(array(robot.data.joint_pos_limits)[0].tolist()),
                joint_velocity_limits=finite_metadata(array(robot.data.joint_vel_limits)[0].tolist()),
                joint_effort_limits=finite_metadata(array(robot.data.joint_effort_limits)[0].tolist()),
                joint_stiffness=finite_metadata(array(robot.data.joint_stiffness)[0].tolist()),
                joint_damping=finite_metadata(array(robot.data.joint_damping)[0].tolist()),
                units='SI per joint type: radians/metres and N-m/N; joint types are defined in the pinned USD',
                usd_path=str(robot.cfg.spawn.usd_path),
                enabled_self_collisions=robot.cfg.spawn.articulation_props.enabled_self_collisions,
                articulation_solver_position_iterations=robot.cfg.spawn.articulation_props.solver_position_iteration_count,
                articulation_solver_velocity_iterations=robot.cfg.spawn.articulation_props.solver_velocity_iteration_count,
                disable_gravity=robot.cfg.spawn.rigid_props.disable_gravity)
            executor,adapter=GraspLiftExecutor(),EmbodimentAdapter(self.embodiment)
            open_action=np.zeros(7)
            open_action[-1]=1. if self.embodiment=='franka_panda' else 0.
            initial=None
            write_json(self.output/(episode_id+'_reset.json'),dict(observation=reader.read(base,episode_id).model_dump(),
                mass_readback_kg=mass.tolist(),condition=condition,skill=skill.model_dump()))
            loop_started=time.monotonic()
            recording_s=0.
            while steps < 780:
                obs=reader.read(base,episode_id)
                if obs.sim_time_s >= .5-1e-9 and initial is None:
                    initial=obs
                    expected=np.array([.5+condition['offset_xy_m'][0],condition['offset_xy_m'][1],.0325])
                    if np.linalg.norm(np.asarray(obs.object_pose_w.position_m)-expected) > .01:
                        raise RuntimeError('INVALID_RESET: object position failed settle readback')
                    from ..control.geometry import angle
                    import math
                    expected_q=(0.,0.,math.sin(condition['yaw_rad']/2),math.cos(condition['yaw_rad']/2))
                    if (angle(obs.object_pose_w.quaternion_xyzw,expected_q)>.05
                        or np.linalg.norm(obs.object_linear_velocity_w)>.03
                        or np.linalg.norm(obs.object_angular_velocity_w)>.5):
                        raise RuntimeError('INVALID_RESET: object orientation/velocity failed settle readback')
                    executor.reset(skill,obs)
                    task.judge.reset(obs)
                    task.ready=True
                command_record=None
                if initial is None:
                    action=open_action.copy()
                else:
                    try:
                        cmd=executor.step(obs)
                    except ValueError as exc:
                        if str(exc)!='JOINT_OR_WORKSPACE_LIMIT':
                            raise
                        terminal=task.judge.update(obs,hard_failures=('JOINT_OR_WORKSPACE_LIMIT',))
                        task.terminal_evidence=dict(result=terminal,observation=obs.model_dump())
                        break
                    command_record=cmd.model_dump(mode="json")
                    action=adapter.encode(cmd,reader.root_w,reader.control_w,reader.control_to_tcp)
                tick=time.monotonic()
                append_json(self.output/(episode_id+"_trace.jsonl"),dict(observation=obs.model_dump(),
                    native_action=action.tolist(),canonical_command=command_record,
                    stage=executor.stage if initial else "INITIAL_SETTLE"))
                recording_s+=time.monotonic()-tick
                states.append(obs.model_dump())
                actions.append(action.copy())
                _,_,terminated,truncated,_=env.step(torch.as_tensor(action,device=base.device,dtype=torch.float32)[None,:])
                steps+=1
                self._steps=steps
                if bool(terminated.any() or truncated.any()):
                    break
            self._timings['control_loop_s']=time.monotonic()-loop_started-recording_s
            tick=time.monotonic()
            evidence=task.terminal_evidence
            if evidence is None:
                raise RuntimeError('Missing pre-reset terminal evidence')
            trajectory=self.output/(episode_id+'.npz')
            np.savez_compressed(trajectory,sim_time_s=np.array([s['sim_time_s'] for s in states]),
                object_position_m=np.array([s['object_pose_w']['position_m'] for s in states]),
                tcp_position_m=np.array([s['tcp_pose_w']['position_m'] for s in states]),
                native_actions=np.asarray(actions))
            write_json(self.output/(episode_id+'.json'),dict(initial=initial.model_dump(),terminal=evidence,
                embodiment=self.embodiment,condition=condition,mass_readback_kg=mass.tolist(),
                effective_robot=effective_robot,
                requested_skill=skill.model_dump(),stage_times=executor.stage_times,
                configured_development_validation=self.configured_validation,
                validation_authority='external_freeze_and_acceptance_audit',formal_result_eligible=False))
            self._timings['recording_s']=recording_s+time.monotonic()-tick
            return EpisodeResult(episode_id=episode_id,condition_id=condition['condition_id'],split=condition['split'],
                phase=phase,candidate_index=candidate_index,skill_hash=skill.semantic_hash,backend='physx',
                attempt_index=attempt_index,simulator_steps=steps*4,sim_time_s=steps*.02,
                wall_time_s=time.monotonic()-started,trajectory_path=str(trajectory),
                trajectory_sha256=file_digest(trajectory),**evidence['result'])
        except Exception as exc:
            write_json(self.output/(episode_id+'_error.json'),dict(error=type(exc).__name__,message=str(exc),
                simulator_steps=steps*4,wall_time_s=time.monotonic()-started,
                last_observation=states[-1] if states else None))
            raise
        finally:
            tick=time.monotonic()
            env.close()
            from isaaclab_arena.utils.isaaclab_utils.simulation_app import teardown_simulation_app
            teardown_simulation_app()
            self._timings['teardown_s']=time.monotonic()-tick
