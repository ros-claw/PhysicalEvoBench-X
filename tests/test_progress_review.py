"""CPU-only audit fixtures; never benchmark performance evidence."""
import importlib.util
import json
from pathlib import Path

import pytest
from physicalevobench_x.core.schemas import EpisodeResult, SkillSpec

spec = importlib.util.spec_from_file_location(
    'progress_review', Path(__file__).parents[1]/'tools/check_completed_packages.py')
review = importlib.util.module_from_spec(spec)
spec.loader.exec_module(review)


def record(eid, condition, skill, success=True, infra=None):
    return EpisodeResult(episode_id=eid, condition_id=condition, split='target_test',
                         phase='evaluation', candidate_index=0, skill_hash=skill.semantic_hash,
                         backend='fake', task_success=success, max_lift_m=.12 if success else 0.,
                         completion_time_s=8. if success else 15., hold_time_s=1. if success else 0.,
                         termination_reason='CPU_FIXTURE', infra_failure=infra, attempt_index=0,
                         simulator_steps=1, sim_time_s=.02, wall_time_s=.01)


def write_pairs(path, attempts, summary):
    (path/'pair_attempts.jsonl').write_text(''.join(json.dumps(a)+'\n' for a in attempts))
    (path/'summary.json').write_text(json.dumps(summary))


def test_progress_alias_is_one_physical_episode_per_condition(tmp_path):
    skill = SkillSpec.initial()
    rows = [record('one', 'c1', skill), record('two', 'c2', skill, False)]
    summary = dict(pairs=2, before_successes=1, after_successes=1,
                   delta_new=0., evaluation_aliased=True)
    write_pairs(tmp_path, [dict(included=True, episode_ids=[r.episode_id]) for r in rows], summary)
    actual, excluded = review.check_pairs(tmp_path, rows, skill, skill,
                                         [dict(condition_id='c1'), dict(condition_id='c2')])
    assert actual == summary and excluded == set()
    with pytest.raises(ValueError, match='episode count'):
        review.check_pairs(tmp_path, rows+rows, skill, skill,
                           [dict(condition_id='c1'), dict(condition_id='c2')])


def test_progress_detects_tampered_negative_transfer_summary(tmp_path):
    before = SkillSpec.initial()
    data = before.model_dump()
    data['parameters']['settle_time_s'] = .4
    after = SkillSpec.model_validate(data)
    rows = [record('b', 'c', before), record('a', 'c', after, False)]
    summary = dict(pairs=1, before_successes=1, after_successes=0,
                   delta_new=-1., evaluation_aliased=False)
    attempts = [dict(included=True, episode_ids=['b', 'a'])]
    write_pairs(tmp_path, attempts, summary)
    assert review.check_pairs(tmp_path, rows, before, after, [dict(condition_id='c')])[0] == summary
    summary['delta_new'] = 1.
    write_pairs(tmp_path, attempts, summary)
    with pytest.raises(ValueError, match='arithmetic'):
        review.check_pairs(tmp_path, rows, before, after, [dict(condition_id='c')])


def test_progress_excludes_both_original_sides_after_infra_retry(tmp_path):
    before = SkillSpec.initial()
    data = before.model_dump()
    data['parameters']['settle_time_s'] = .4
    after = SkillSpec.model_validate(data)
    rows = [record('original_b', 'c', before),
            record('original_a', 'c', after, False, 'CPU_FIXTURE_INFRA'),
            record('retry_b', 'c', before, False), record('retry_a', 'c', after)]
    attempts = [dict(included=False, episode_ids=['original_b', 'original_a']),
                dict(included=True, episode_ids=['retry_b', 'retry_a'])]
    summary = dict(pairs=1, before_successes=0, after_successes=1,
                   delta_new=1., evaluation_aliased=False)
    write_pairs(tmp_path, attempts, summary)
    actual, excluded = review.check_pairs(tmp_path, rows, before, after, [dict(condition_id='c')])
    assert actual == summary and excluded == {'original_b', 'original_a'}
