import pytest
from benchmark.loader import Scenario, load_scenarios


def test_load_benchmark_scenarios():
    scenarios = load_scenarios()

    # Confirm scenario count is between 25 and 30
    assert 25 <= len(scenarios) <= 30, f"Expected 25-30 scenarios, got {len(scenarios)}"

    # Check each scenario structure and data
    low_count = 0
    med_count = 0
    high_count = 0

    for sc in scenarios:
        assert isinstance(sc, Scenario)
        assert isinstance(sc.scenario_id, str) and len(sc.scenario_id) > 0
        assert isinstance(sc.task_instruction, str) and len(sc.task_instruction) > 0
        assert isinstance(sc.tool_calls, list) and len(sc.tool_calls) > 0
        assert sc.ground_truth_risk_label in {"low", "medium", "high"}

        if sc.ground_truth_risk_label == "low":
            low_count += 1
        elif sc.ground_truth_risk_label == "medium":
            med_count += 1
        elif sc.ground_truth_risk_label == "high":
            high_count += 1

    # Verify distribution across low, medium, and high risk labels (roughly equal 8-10 each)
    assert 8 <= low_count <= 10, f"Expected 8-10 low scenarios, got {low_count}"
    assert 8 <= med_count <= 10, f"Expected 8-10 medium scenarios, got {med_count}"
    assert 8 <= high_count <= 10, f"Expected 8-10 high scenarios, got {high_count}"
