"""
CGTEL Configuration
Centralized configuration parameters for signal weights and decision thresholds.
"""

# Signal Weights: R = w1 * reversibility + w2 * (1 - confidence) + w3 * failure_rate
DEFAULT_WEIGHTS = {
    "w1": 1.0 / 3.0,  # Reversibility weight
    "w2": 1.0 / 3.0,  # Confidence gap (1 - confidence) weight
    "w3": 1.0 / 3.0,  # Historical failure rate weight
}

# Decision Thresholds
TAU_1 = 0.15  # score < TAU_1 -> AUTO_ALLOW
TAU_2 = 0.35  # TAU_1 <= score < TAU_2 -> LOG_AND_MONITOR; score >= TAU_2 -> HUMAN_REVIEW
