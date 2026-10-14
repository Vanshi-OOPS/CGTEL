import pytest
from cgtel.signals.reversibility import ReversibilityEstimator


def test_default_taxonomy_scores():
    estimator = ReversibilityEstimator()

    # Read-only (0.0)
    assert estimator.estimate("read_file") == 0.0
    assert estimator.estimate("get_user_info") == 0.0
    assert estimator.estimate("fetch_metrics") == 0.0
    assert estimator.estimate("list_directory") == 0.0

    # Reversible-write (0.3)
    assert estimator.estimate("create_temp_file") == 0.3
    assert estimator.estimate("update_cache") == 0.3
    assert estimator.estimate("write_draft") == 0.3

    # Hard-to-reverse write (0.7)
    assert estimator.estimate("delete_record") == 0.7
    assert estimator.estimate("remove_user") == 0.7
    assert estimator.estimate("purge_logs") == 0.7

    # Irreversible / External effect (1.0)
    assert estimator.estimate("payment_checkout") == 1.0
    assert estimator.estimate("transfer_funds") == 1.0
    assert estimator.estimate("send_email_notification") == 1.0
    assert estimator.estimate("deploy_production") == 1.0


def test_argument_keyword_matching():
    estimator = ReversibilityEstimator()

    # Tool name is vague, but argument value indicates payment
    assert estimator.estimate("execute_action", args={"action_type": "payment"}) == 1.0
    # Argument key indicates delete
    assert estimator.estimate("manage_data", args={"delete_flag": True}) == 0.7


def test_custom_keyword_rules():
    custom_rules = {
        "format_disk": 1.0,
        "scratch": 0.1,
    }
    estimator = ReversibilityEstimator(keyword_rules=custom_rules, default_score=0.4)

    assert estimator.estimate("format_disk_c") == 1.0
    assert estimator.estimate("scratch_notes") == 0.1
    # Fallback to default score
    assert estimator.estimate("unknown_operation") == 0.4


def test_score_clamping():
    estimator = ReversibilityEstimator(
        keyword_rules={"too_high": 2.5, "too_low": -1.0}, default_score=1.5
    )

    assert estimator.default_score == 1.0
    assert estimator.estimate("too_high") == 1.0
    assert estimator.estimate("too_low") == 0.0
