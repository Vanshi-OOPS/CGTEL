import os
import tempfile
import pytest
from cgtel.signals.failure_rate import HistoricalFailureRateLookup


def test_cold_start_default():
    lookup = HistoricalFailureRateLookup()
    # Unrecorded tool should return cold-start default (0.1)
    assert lookup.get_failure_rate("unknown_tool") == 0.1
    lookup.close()


def test_custom_cold_start_default():
    lookup = HistoricalFailureRateLookup(default_failure_rate=0.25)
    assert lookup.get_failure_rate("unknown_tool") == 0.25
    lookup.close()


def test_running_average_update():
    lookup = HistoricalFailureRateLookup()

    # Tool 1: First observation is a failure (1.0) -> rate becomes 1.0 (1 call, 1 failure)
    rate1 = lookup.update("read_file", is_failure=True)
    assert pytest.approx(rate1, 0.001) == 1.0
    assert pytest.approx(lookup.get_failure_rate("read_file"), 0.001) == 1.0

    # Second observation is a success (0.0) -> rate becomes 0.5 (2 calls, 1 failure)
    rate2 = lookup.update("read_file", is_failure=False)
    assert pytest.approx(rate2, 0.001) == 0.5
    assert pytest.approx(lookup.get_failure_rate("read_file"), 0.001) == 0.5

    # Third observation is a success (0.0) -> rate becomes 1/3 ~ 0.3333
    rate3 = lookup.update("read_file", is_failure=False)
    assert pytest.approx(rate3, 0.001) == 1 / 3

    lookup.close()


def test_sqlite_file_persistence():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = tmp.name

    try:
        # Create lookup and insert record
        store1 = HistoricalFailureRateLookup(db_path=db_path)
        store1.update("payment_tool", is_failure=True)
        store1.update("payment_tool", is_failure=True)
        assert store1.get_failure_rate("payment_tool") == 1.0

        # Create new lookup instance pointing to same file and verify persistence
        store2 = HistoricalFailureRateLookup(db_path=db_path)
        assert store2.get_failure_rate("payment_tool") == 1.0
    finally:
        if os.path.exists(db_path):
            os.remove(db_path)
