"""Real PhysX judge diagnostics: free-body toss and deliberate release during lift.

Trusted diagnostics deliberately perturb physics/actions; they are not contestant
rollouts and never enter learning or benchmark success-rate tables.
"""
import argparse
from pathlib import Path


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    from isaaclab_arena.cli.isaaclab_arena_cli import get_isaaclab_arena_cli_parser
    from isaaclab_arena.utils.isaaclab_utils.simulation_app import SimulationAppContext
    with SimulationAppContext(get_isaaclab_arena_cli_parser().parse_args([])):
        import torch
        from isaaclab_arena.environments.arena_env_builder import ArenaEnvBuilder
        from isaaclab_arena.environments.arena_env_builder_cfg import ArenaEnvBuilderCfg
        from isaaclab_arena.utils.isaaclab_utils.simulation_app import teardown_simulation_app
        from physicalevobench_x.sim.arena_factory import StableLiftEnvironment,StableLiftEnvironmentCfg
        from physicalevobench_x.control.adapter import EmbodimentAdapter
        from physicalevobench_x.control.grasp_lift_executor import GraspLiftExecutor
        from physicalevobench_x.core.schemas import SkillSpec,CanonicalCommand,Gripper
        from physicalevobench_x.core.hashing import append_json,write_json,file_digest
        args.output.mkdir(parents=True,exist_ok=False)
        results=[]
        for body in ('franka_panda','franka_robotiq'):
            for attack in ('toss','release_during_lift'):
                directory=args.output/body/attack
                directory.mkdir(parents=True)
                axis=(0.,0.,0.,1.) if body=='franka_panda' else (0.,2**-.5,0.,2**-.5)
                arena=StableLiftEnvironment().build(StableLiftEnvironmentCfg(embodiment=body,axis_mapping_xyzw=axis))
                env,_=ArenaEnvBuilder(arena,ArenaEnvBuilderCfg(num_envs=1,solve_relations=False,resolve_on_reset=False,
                    recorder_dataset_export_dir_path=str(directory/'arena'),recorder_dataset_filename='judge')).make_registered_and_return_cfg()
                base=env.unwrapped
                base.pebx_task=arena.task
                base.configure_episode_limit(1)
                reader,adapter=arena.task.reader,EmbodimentAdapter(body)
                executor=GraspLiftExecutor()
                initial=None
                attack_applied=False
                force_active=False
                try:
                    with torch.inference_mode():
                        env.reset(seed=42)
                        reference=reader.read(base,'judge_diagnostic').tcp_pose_w
                        cube=base.scene['pebx_object']
                        for _ in range(780):
                            obs=reader.read(base,'judge_diagnostic')
                            if obs.sim_time_s>=.5-1e-9 and initial is None:
                                initial=obs
                                executor.reset(SkillSpec.initial(),obs)
                            cmd=CanonicalCommand(tcp_pose_w=reference,gripper=Gripper.OPEN)
                            if initial is not None and attack=='release_during_lift':
                                cmd=executor.step(obs)
                                if obs.object_pose_w.position_m[2]-initial.object_pose_w.position_m[2]>.09:
                                    attack_applied=True
                                if attack_applied:
                                    cmd=cmd.model_copy(update={'gripper':Gripper.OPEN})
                            if attack=='toss' and initial is not None and not attack_applied:
                                force=torch.tensor([[[0.,0.,20.]]],device=base.device)
                                cube.permanent_wrench_composer.add_forces_and_torques(force,torch.zeros_like(force),is_global=True)
                                attack_applied=force_active=True
                            action=adapter.encode(cmd,reader.root_w,reader.control_w,reader.control_to_tcp)
                            append_json(directory/'trace.jsonl',dict(observation=obs.model_dump(),attack_applied=attack_applied,
                                command=cmd.model_dump(mode='json'),native_action=action.tolist()))
                            _,_,terminated,truncated,_=env.step(torch.as_tensor(action,device=base.device,dtype=torch.float32)[None,:])
                            if force_active:
                                cube.permanent_wrench_composer.reset()
                                force_active=False
                            if bool(terminated.any() or truncated.any()):
                                break
                        terminal=arena.task.terminal_evidence
                        passed=bool(attack_applied and terminal and not terminal['result']['task_success']
                            and terminal['result']['max_lift_m']>=.08 and terminal['result']['hold_time_s']<1.)
                        result=dict(backend='physx',body=body,diagnostic=attack,attack_applied=attack_applied,
                            passed=passed,terminal=terminal,trace_sha256=file_digest(directory/'trace.jsonl'))
                        write_json(directory/'result.json',result)
                        results.append(result)
                        write_json(args.output/'partial.json',results)
                finally:
                    env.close()
                    teardown_simulation_app()
        write_json(args.output/'judge_adversarial.json',dict(backend='physx',
            status='GPU_VERIFIED' if all(r['passed'] for r in results) else 'GPU_CHECK_FAILED',
            diagnostics=results,formal_result_eligible=False,note='Controlled evaluator diagnostics, not learner episodes'))


if __name__=='__main__':
    main()
