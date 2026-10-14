import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

VALID_RISK_LABELS = {"low", "medium", "high"}


@dataclass
class Scenario:
    """Represents a benchmark agent task scenario."""

    scenario_id: str
    task_instruction: str
    tool_calls: List[Dict[str, Any]]
    ground_truth_risk_label: str

    def __post_init__(self):
        if not self.scenario_id or not isinstance(self.scenario_id, str):
            raise ValueError("Scenario scenario_id must be a non-empty string.")
        if not self.task_instruction or not isinstance(self.task_instruction, str):
            raise ValueError("Scenario task_instruction must be a non-empty string.")
        if not isinstance(self.tool_calls, list):
            raise ValueError("Scenario tool_calls must be a list.")
        if self.ground_truth_risk_label not in VALID_RISK_LABELS:
            raise ValueError(
                f"Scenario ground_truth_risk_label must be one of {VALID_RISK_LABELS}, got '{self.ground_truth_risk_label}'"
            )


def load_scenarios(benchmark_dir: Optional[str] = None) -> List[Scenario]:
    """
    Loads all scenario JSON/YAML files from the benchmark scenarios directory.
    Returns a list of structured Scenario objects sorted by scenario_id.
    """
    if benchmark_dir is None:
        base_dir = Path(__file__).parent / "scenarios"
    else:
        base_dir = Path(benchmark_dir)

    if not base_dir.exists() or not base_dir.is_dir():
        raise FileNotFoundError(f"Benchmark scenarios directory not found at: {base_dir}")

    scenarios = []

    # Process all JSON files in base_dir
    json_files = list(base_dir.glob("*.json"))

    for filepath in json_files:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)

        scenario = Scenario(
            scenario_id=data["scenario_id"],
            task_instruction=data["task_instruction"],
            tool_calls=data["tool_calls"],
            ground_truth_risk_label=data["ground_truth_risk_label"],
        )
        scenarios.append(scenario)

    return sorted(scenarios, key=lambda s: s.scenario_id)
