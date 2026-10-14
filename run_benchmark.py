#!/usr/bin/env python3
"""
CGTEL Benchmark Execution Script
Runs full benchmark evaluation across all scenarios and displays a formatted summary report.
"""

from benchmark.evaluator import BenchmarkEvaluator


def main():
    print("=" * 85)
    print("                  CGTEL BENCHMARK EVALUATION RUNNER")
    print("=" * 85 + "\n")

    evaluator = BenchmarkEvaluator()
    results, summary = evaluator.evaluate_all()

    # Per-Scenario Results Table
    header = f"{'Scenario ID':<15} | {'Ground Truth':<12} | {'CGTEL Assigned Tiers':<25} | {'Baseline (ms)':<13} | {'CGTEL (ms)':<10}"
    print(header)
    print("-" * len(header))

    for res in results:
        tiers_str = ", ".join(t.value for t in res.assigned_tiers)
        print(
            f"{res.scenario_id:<15} | {res.ground_truth_risk_label:<12} | {tiers_str:<25} | {res.baseline_latency_ms:<13.4f} | {res.cgtel_latency_ms:<10.4f}"
        )

    print("\n" + "=" * 85)
    print("                         SUMMARY METRICS REPORT")
    print("=" * 85)
    print(f" Total Scenarios Evaluated   : {summary.total_scenarios} (Low: {summary.low_risk_count}, Med: {summary.medium_risk_count}, High: {summary.high_risk_count})")
    print(f" Unsafe Execution Rate       : {summary.unsafe_execution_rate * 100:.2f}%  (High-risk calls AUTO_ALLOWed)")
    print(f" False Positive Rate         : {summary.false_positive_rate * 100:.2f}%  (Low-risk calls flagged/reviewed)")
    print(f" Avg Baseline Latency        : {summary.avg_baseline_latency_ms:.4f} ms")
    print(f" Avg CGTEL Pipeline Latency  : {summary.avg_cgtel_latency_ms:.4f} ms")
    print(f" Avg Latency Overhead        : {summary.avg_latency_overhead_ms:.4f} ms")
    print("=" * 85 + "\n")


if __name__ == "__main__":
    main()
