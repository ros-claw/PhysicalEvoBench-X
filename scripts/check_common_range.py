"""Predeclared development range checks, including combined boundary stress.

Run both embodiments with the native interpreter. No formal test split is used.
Failures stay in the report and do not abort remaining development cases.
"""
import argparse
import itertools
from pathlib import Path
import yaml


def plan(config):
    from physicalevobench_x.core.schemas import SkillSpec
    from physicalevobench_x.core.conditions import generate
    from physicalevobench_x.core.hashing import digest
    initial = SkillSpec.initial().model_dump()
    bounds = config['bounds']
    cases = []
    for field, (lo, hi) in bounds.items():
        for label, value in [('low', lo), ('mid', (lo+hi)/2), ('high', hi)]:
            data = {**initial, 'parameters': {**initial['parameters'], field: value}}
            cases.append((f'{field}/{label}', SkillSpec.model_validate(data), None))
    # Eight fixed combined corners: physical extremes alternate independently of skill corners.
    # These are development checks, not evidence that the entire continuous box is safe.
    fields = list(bounds)
    for index in range(8):
        bits = [(index >> (j % 3)) & 1 for j in range(5)]
        params = {field: bounds[field][bits[j]] for j, field in enumerate(fields)}
        stress = dict(offset_xy_m=[.03 if index & 1 else -.03, .03 if index & 2 else -.03],
                      yaw_rad=.1745329252 if index & 4 else -.1745329252,
                      mass_kg=.5 if index % 2 else .1)
        cases.append((f'combined/{index}', SkillSpec.model_validate({**initial, 'parameters': params}), stress))
    base = generate(123, {'dev': 1})['dev'][0]
    base.update(offset_xy_m=[0., 0.], yaw_rad=0., mass_kg=.2)
    return [dict(case_id=name, skill=skill.model_dump(),
                 condition=dict(base, **(stress or {}), condition_id=digest(['common_range_v1', name])[:24]))
            for name, skill, stress in cases]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--embodiment', choices=['franka_panda', 'franka_robotiq'], required=True)
    parser.add_argument('--config', type=Path, default=Path('configs/development/common_range_candidate.yaml'))
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    from physicalevobench_x.core.hashing import write_json, append_json, file_digest
    from physicalevobench_x.core.schemas import SkillSpec
    cases = plan(yaml.safe_load(args.config.read_text()))
    args.output.mkdir(parents=True, exist_ok=False)
    write_json(args.output/'plan.json', dict(cases=cases, config_sha256=file_digest(args.config),
                                            embodiment=args.embodiment, formal_result_eligible=False))
    from isaaclab_arena.cli.isaaclab_arena_cli import get_isaaclab_arena_cli_parser
    from isaaclab_arena.utils.isaaclab_utils.simulation_app import SimulationAppContext
    with SimulationAppContext(get_isaaclab_arena_cli_parser().parse_args([])):
        from physicalevobench_x.sim.runner import PhysXRunner
        runner = PhysXRunner(args.embodiment, args.output/'trajectories')
        results = []
        for case in cases:
            result = runner.run(skill=SkillSpec.model_validate(case['skill']), condition=case['condition'],
                                phase='calibration', candidate_index=0, attempt_index=0)
            append_json(args.output/'episode_results.jsonl', result)
            results.append(dict(case_id=case['case_id'], **result.model_dump()))
            write_json(args.output/'progress.json', dict(completed=len(results), planned=len(cases)))
        write_json(args.output/'range_check.json', dict(backend='physx', status='MEASUREMENTS_COMPLETE',
            embodiment=args.embodiment, measurements=results, planned_episodes=len(cases),
            successes=sum(r['task_success'] for r in results), formal_result_eligible=False))


if __name__ == '__main__':
    main()
