"""CPU-only tests of diagnostic duration and safety behavior."""
from physicalevobench_x.measurement.comparison import FullHorizonComparison


def test_comparison_does_not_end_when_a_judge_succeeds(observation):
    comparison=FullHorizonComparison();comparison.reset(observation(t=0.,height=.1))
    for i in range(1,101):
        assert comparison.update(observation(t=i*.02,height=.2,tcp_height=.3)) is None
    assert comparison.candidate.terminal['task_success']
    assert comparison.legacy.terminal['task_success']
    assert comparison.update(observation(t=15.,height=.2,tcp_height=.3))['termination_reason']=='DIAGNOSTIC_HORIZON_COMPLETE'


def test_diagnostic_hard_stop_is_retained_after_first_success(observation):
    comparison=FullHorizonComparison();comparison.reset(observation(t=0.,height=.1))
    for i in range(1,101):comparison.update(observation(t=i*.02,height=.2,tcp_height=.3))
    result=comparison.update(observation(t=2.02,height=.2,tcp_height=.3),hard_failures=['MEASURED_SAFETY_STOP'])
    assert not result['task_success'] and result['constraint_violations']==['MEASURED_SAFETY_STOP']
    assert comparison.candidate.terminal['task_success'] # first crossing remains inspectable
