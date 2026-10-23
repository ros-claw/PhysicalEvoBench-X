import importlib.util
import json
from pathlib import Path
import pytest
from physicalevobench_x.core.hashing import file_digest

spec = importlib.util.spec_from_file_location('pilot_support', Path(__file__).parents[1]/'scripts/pilot_support.py')
support = importlib.util.module_from_spec(spec)
spec.loader.exec_module(support)


def test_resume_replays_once_and_rejects_changed_inputs(tmp_path):
    calls = []
    execute = lambda: calls.append(1) or {'answer': 7}
    journal = support.ReplayJournal(tmp_path/'journal', {'version': 'a'})
    assert journal.call({'request': 1}, execute) == {'answer': 7}
    replay = support.ReplayJournal(tmp_path/'journal', {'version': 'a'})
    assert replay.call({'request': 1}, execute) == {'answer': 7}
    assert len(calls) == 1
    with pytest.raises(ValueError, match='identity mismatch'):
        support.ReplayJournal(tmp_path/'journal', {'version': 'b'})
    replay = support.ReplayJournal(tmp_path/'journal', {'version': 'a'})
    with pytest.raises(ValueError, match='diverged'):
        replay.call({'request': 2}, execute)


def test_ambiguous_inflight_physics_never_retried_silently(tmp_path):
    journal = support.ReplayJournal(tmp_path, {'version': 'a'})
    def fail():
        raise RuntimeError('power loss')
    with pytest.raises(RuntimeError, match='power loss'):
        journal.call({'episode': 1}, fail, physical=True)
    journal = support.ReplayJournal(tmp_path, {'version': 'a'})
    with pytest.raises(RuntimeError, match='ambiguous'):
        journal.call({'episode': 1}, lambda: pytest.fail('must not execute'), physical=True)


def test_resume_checks_physical_evidence(tmp_path):
    trace = tmp_path/'trajectory.npz'
    trace.write_bytes(b'physical-evidence-fixture')
    result = {'trajectory_path': str(trace), 'trajectory_sha256': file_digest(trace)}
    journal = support.ReplayJournal(tmp_path/'j', {'version': 'a'})
    journal.call({'episode': 1}, lambda: result, physical=True)
    trace.write_bytes(b'changed')
    journal = support.ReplayJournal(tmp_path/'j', {'version': 'a'})
    with pytest.raises(ValueError, match='changed'):
        journal.call({'episode': 1}, lambda: result, physical=True)


def test_partial_resume_restores_proposal_rng_without_repeating_remote_calls(tmp_path):
    from physicalevobench_x.learners.random_search import RandomSearch
    from physicalevobench_x.core.schemas import SkillSpec
    initial = SkillSpec.initial()
    expected = RandomSearch(17)
    first = expected.propose(initial, [])
    second = expected.propose(first, [])
    journal = support.ReplayJournal(tmp_path, {'version': 'a'})
    proposer = support.replay_factory(journal, RandomSearch)(17)
    assert proposer.propose(initial, []) == first
    # Re-enter a partial run: replay first proposal, then generate the second.
    journal = support.ReplayJournal(tmp_path, {'version': 'a'})
    proposer = support.replay_factory(journal, RandomSearch)(17)
    assert proposer.propose(initial, []) == first
    assert proposer.propose(first, []) == second


def test_complete_matrix_package_aliases_budgets_and_resumes_without_execution(tmp_path, monkeypatch):
    import argparse
    import sys
    import types
    from physicalevobench_x.core.schemas import EpisodeResult
    from physicalevobench_x.core.hashing import digest
    monkeypatch.syspath_prepend(str(Path(__file__).parents[1]/'scripts'))
    import pilot_suite
    calls = []
    class PhysicalFixture:
        # Explicit CPU protocol fixture; never published as physical evidence.
        def __init__(self, body, output):
            self.output = output
            output.mkdir(parents=True, exist_ok=True)
        def run(self, *, skill, condition, phase, candidate_index, attempt_index):
            calls.append((condition['condition_id'], phase))
            episode_id = f'cpu-fixture-{len(calls)}'
            trajectory = self.output/(episode_id+'.npz')
            trajectory.write_bytes(b'CPU protocol fixture only')
            return EpisodeResult(episode_id=episode_id, condition_id=condition['condition_id'],
                split=condition['split'],phase=phase,candidate_index=candidate_index,
                skill_hash=skill.semantic_hash,backend='fake',task_success=False,max_lift_m=0.,
                completion_time_s=15.,hold_time_s=0.,termination_reason='FAKE',attempt_index=attempt_index,
                simulator_steps=1,sim_time_s=.02,wall_time_s=.01,trajectory_path=str(trajectory),
                trajectory_sha256=file_digest(trajectory))
    class Context:
        def __init__(self, args):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
    for name, attrs in {
        'physicalevobench_x.sim.runner': {'PhysXRunner': PhysicalFixture},
        'isaaclab_arena.cli.isaaclab_arena_cli': {'get_isaaclab_arena_cli_parser': argparse.ArgumentParser},
        'isaaclab_arena.utils.isaaclab_utils.simulation_app': {'SimulationAppContext': Context},
    }.items():
        module = types.ModuleType(name)
        module.__dict__.update(attrs)
        monkeypatch.setitem(sys.modules,name,module)
    root = Path(__file__).parents[1]
    suite = tmp_path/'suite'
    data = pilot_suite.plan(suite,root,seeds=1,test_count=2,learners=['random_search_v1'])
    assert data['logical_episode_requests'] == 172
    assert (suite/'private').stat().st_mode & 0o077 == 0
    package = data['packages'][0]['package_id']
    pilot_suite.worker(suite,package,root)
    summary = json.loads((suite/'packages'/package/'summary.json').read_text())
    assert summary['formal_result_eligible'] is False
    assert summary['costs']['physical_episode_executions'] == 53
    assert summary['costs']['aliased_episode_requests'] == 33
    assert summary['costs']['budget_charged_episodes'] == 45
    assert all(c['delta_new'] == 0 for c in summary['cells'])
    assert len(calls) == 53
    pilot_suite.worker(suite,package,root)
    assert len(calls) == 53
