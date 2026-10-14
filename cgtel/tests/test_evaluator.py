import pytest
from benchmark.evaluator import BenchmarkEvaluator, BenchmarkSummaryMetrics, ScenarioEvaluationResult
from benchmark.loader import Scenario, load_scenarios


def test_evaluator_subset_run():
    evaluator = BenchmarkEvaluator()
    scenarios = load_scenarios()

    # Pick a small subset of 6 scenarios (2 low, 2 medium, 2 high)
    low_sub = [s for s in scenarios if s.ground_truth_risk_label == "low"][:2]
    med_sub = [s for s in scenarios if s.ground_truth_risk_label == "medium"][:2]
    high_sub = [s for s in scenarios if s.ground_truth_risk_label == "high"][:2]
    subset = low_sub + med_sub + high_sub

    results, summary = evaluator.evaluate_all(scenarios=subset)

    # Confirm results length
    assert len(results) == 6
    assert isinstance(summary, BenchmarkSummaryMetrics)

    # Check metrics ranges and valid structures
    assert summary.total_scenarios == 6
    assert summary.low_risk_count == 2
    assert summary.medium_risk_count == 2
    assert summary.high_risk_count == 2

    assert 0.0 <= summary.unsafe_execution_rate <= 1.0
    assert 0.0 <= summary.false_positive_rate <= 1.0
    assert isinstance(summary.avg_baseline_latency_ms, float)
    assert isinstance(summary.avg_cgtel_latency_ms, float)
    assert isinstance(summary.avg_latency_overhead_ms, float)

    # Check individual scenario evaluation results
    for res in results:
        assert isinstance(res, ScenarioEvaluationResult)
        assert isinstance(res.scenario_id, str)
        assert res.baseline_latency_ms >= 0.0
        assert res.cgtel_latency_ms >= 0.0
        assert len(res.assigned_tiers) > 0
