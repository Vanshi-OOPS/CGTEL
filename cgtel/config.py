"""
CGTEL Configuration
Centralized configuration parameters for signal weights and decision thresholds.
"""

# Signal Weights: R = w1 * reversibility + w2 * (1 - confidence) + w3 * failure_rate
DEFAULT_WEIGHTS = {
    "w1": 0.25,  # Reversibility weight
    "w2": 0.25,  # Confidence gap (1 - confidence) weight
    "w3": 0.50,  # Failure/severity signal weight
}

# The severity prior is a per-tool floor on the F input to the existing score
# equation. Observed failure rates can raise F above this prior.
DEFAULT_TOOL_POLICIES = {
    "read_file": {"severity_prior": 0.05, "minimum_decision": None},
    "write_file": {"severity_prior": 0.30, "minimum_decision": "LOG_AND_MONITOR"},
    "send_email": {"severity_prior": 0.10, "minimum_decision": "LOG_AND_MONITOR"},
    "delete_file": {"severity_prior": 0.80, "minimum_decision": "HUMAN_REVIEW"},
    "make_payment": {"severity_prior": 0.80, "minimum_decision": "HUMAN_REVIEW"},
    # The original Desk tool names use the same shared scoring policy.
    "fake_file_read": {"severity_prior": 0.05, "minimum_decision": None},
    "fake_file_delete": {"severity_prior": 0.80, "minimum_decision": "HUMAN_REVIEW"},
    "fake_payment_call": {"severity_prior": 0.80, "minimum_decision": "HUMAN_REVIEW"},
}

# Decision Thresholds
TAU_1 = 0.15  # score < TAU_1 -> AUTO_ALLOW
TAU_2 = 0.35  # TAU_1 <= score < TAU_2 -> LOG_AND_MONITOR; score >= TAU_2 -> HUMAN_REVIEW
