"""JSON arrays and typed constraint tuples describe the same retained outcome."""
import importlib.util
from pathlib import Path


def test_json_terminal_matches_typed_result_and_still_detects_changed_score(monkeypatch):
    from physicalevobench_x.core.schemas import EpisodeResult
    root=Path(__file__).resolve().parents[1];monkeypatch.syspath_prepend(str(root/'tools'))
    spec=importlib.util.spec_from_file_location('fresh_audit',root/'tools/audit_fresh_native.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    result=EpisodeResult(episode_id='unit',condition_id='unit',split='dev',phase='calibration',candidate_index=0,
        skill_hash='0'*64,backend='fake',task_success=True,max_lift_m=.1,completion_time_s=8.,hold_time_s=1.,
        termination_reason='SUCCESS',attempt_index=0,simulator_steps=1700,sim_time_s=8.5,wall_time_s=1.)
    terminal=dict(task_success=True,constraint_violations=[],max_lift_m=.1,completion_time_s=8.,hold_time_s=1.,termination_reason='SUCCESS')
    assert module.result_matches(terminal,result)
    terminal['completion_time_s']=7.
    assert not module.result_matches(terminal,result)
