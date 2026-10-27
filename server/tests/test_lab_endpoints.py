"""Tests for Part B lab endpoints: /api/score, /api/benchmark, /api/reset-history."""
import sqlite3
import pytest
from starlette.testclient import TestClient

from server.app import create_app
from server.config import Settings


# ── fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def temp_settings(tmp_path):
    data_dir = tmp_path / "server_data"
    return Settings(
        server_data_dir=str(data_dir),
        review_timeout=5.0,
    )


@pytest.fixture
def app(temp_settings):
    application = create_app(temp_settings)
    yield application
    if hasattr(application.state, "server_state") and application.state.server_state:
        application.state.server_state.shutdown()


@pytest.fixture
def client(app):
    with TestClient(app) as test_client:
        yield test_client


# ── helper: dump all rows from the shared failure-rate table ──────────────────


def _dump_failure_rows(db_path):
    """Return sorted list of (tool_name, total_calls, failure_rate) tuples."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT tool_name, total_calls, failure_rate FROM tool_failure_rates ORDER BY tool_name"
    )
    rows = cursor.fetchall()
    conn.close()
    return rows


# ── /api/score tests ──────────────────────────────────────────────────────────


class TestScore:

    def test_score_fake_payment_default_weights_confidence_0_9(self, app, client):
        """fake_payment_call applies its severity prior and requires review."""
        res = client.post(
            "/api/score",
            json={
                "tool_name": "fake_payment_call",
                "args": {"amount": 149.99, "currency": "USD"},
                "confidence": 0.9,
            },
        )
        assert res.status_code == 200, res.text
        data = res.json()
        assert round(data["score"], 4) == 0.6750
        assert data["tier"] == "HUMAN_REVIEW"
        assert data["signals"]["severity_prior"] == 0.8
        assert data["clamped"] is False
        # Terms should sum to the raw score (within float tolerance)
        terms = data["terms"]
        total = terms["reversibility"] + terms["confidence_gap"] + terms["failure_rate"]
        assert abs(total - data["score"]) < 1e-4

    def test_score_hypothetical_payment_respects_custom_threshold(self, app, client):
        """An unconfigured hypothetical tool uses the supplied threshold override."""
        res = client.post(
            "/api/score",
            json={
                "tool_name": "payment_tool",
                "args": {"amount": 149.99},
                "confidence": 0.9,
                "tau1": 0.15,
                "tau2": 0.5,
            },
        )
        assert res.status_code == 200, res.text
        data = res.json()
        assert round(data["score"], 4) == 0.3250
        assert data["tier"] == "LOG_AND_MONITOR"

    def test_score_tau1_gte_tau2_returns_422(self, app, client):
        """tau1 >= tau2 must return 422."""
        # tau1 == tau2
        res = client.post(
            "/api/score",
            json={
                "tool_name": "fake_payment_call",
                "args": {},
                "tau1": 0.35,
                "tau2": 0.35,
            },
        )
        assert res.status_code == 422

        # tau1 > tau2
        res2 = client.post(
            "/api/score",
            json={
                "tool_name": "fake_payment_call",
                "args": {},
                "tau1": 0.9,
                "tau2": 0.2,
            },
        )
        assert res2.status_code == 422

    def test_score_weight_out_of_range_422(self, app, client):
        """Weights outside [0,1] must return 422."""
        res = client.post(
            "/api/score",
            json={
                "tool_name": "fake_payment_call",
                "args": {},
                "w1": 1.5,
            },
        )
        assert res.status_code == 422

        res2 = client.post(
            "/api/score",
            json={
                "tool_name": "fake_payment_call",
                "args": {},
                "w2": -0.1,
            },
        )
        assert res2.status_code == 422

    def test_score_confidence_out_of_range_422(self, app, client):
        """confidence outside [0,1] must return 422."""
        res = client.post(
            "/api/score",
            json={
                "tool_name": "fake_payment_call",
                "args": {},
                "confidence": 1.5,
            },
        )
        assert res.status_code == 422

    def test_score_null_confidence_uses_default_extractor(self, app, client):
        """Omitting confidence (null) should still return a score via default extractor."""
        res = client.post(
            "/api/score",
            json={
                "tool_name": "fake_payment_call",
                "args": {},
            },
        )
        assert res.status_code == 200, res.text
        data = res.json()
        assert "score" in data
        assert "tier" in data
        # confidence_source should indicate it came from the extractor
        assert data["signals"]["confidence_source"] in ("default_mock", "explicit")

    def test_score_read_tool_auto_allow(self, app, client):
        """fake_file_read should score very low and land AUTO_ALLOW with defaults."""
        res = client.post(
            "/api/score",
            json={
                "tool_name": "fake_file_read",
                "args": {"filepath": "test.txt"},
                "confidence": 0.9,
            },
        )
        assert res.status_code == 200, res.text
        data = res.json()
        assert data["tier"] == "AUTO_ALLOW"

    def test_score_does_not_modify_failure_rate_table(self, app, client):
        """Calling /api/score many times must leave the failure-rate table byte-for-byte unchanged."""
        db_path = app.state.server_state.db_path
        rows_before = _dump_failure_rows(db_path)

        for _ in range(10):
            client.post(
                "/api/score",
                json={
                    "tool_name": "fake_payment_call",
                    "args": {"amount": 100},
                    "confidence": 0.9,
                },
            )
            client.post(
                "/api/score",
                json={
                    "tool_name": "fake_file_read",
                    "args": {"filepath": "x.txt"},
                    "confidence": 0.5,
                },
            )

        rows_after = _dump_failure_rows(db_path)
        assert rows_before == rows_after, (
            "Failure-rate table was modified by /api/score calls!\n"
            f"Before: {rows_before}\nAfter: {rows_after}"
        )

    def test_score_response_has_terms_and_clamped(self, app, client):
        """Response must include terms dict and clamped bool."""
        res = client.post(
            "/api/score",
            json={
                "tool_name": "fake_file_read",
                "args": {},
                "confidence": 0.9,
            },
        )
        assert res.status_code == 200
        data = res.json()
        assert "terms" in data
        assert "reversibility" in data["terms"]
        assert "confidence_gap" in data["terms"]
        assert "failure_rate" in data["terms"]
        assert "clamped" in data
        assert isinstance(data["clamped"], bool)


# ── /api/benchmark tests ──────────────────────────────────────────────────────


class TestBenchmark:

    def test_benchmark_default_returns_30_results(self, app, client):
        """Default benchmark should return 30 results with 10/10/10 risk split."""
        res = client.post("/api/benchmark", json={})
        assert res.status_code == 200, res.text
        data = res.json()
        assert len(data["results"]) == 30
        summary = data["summary"]
        assert summary["total_scenarios"] == 30
        assert summary["low_risk_count"] == 10
        assert summary["medium_risk_count"] == 10
        assert summary["high_risk_count"] == 10

    def test_benchmark_results_have_task_instruction(self, app, client):
        """Each result must include a non-empty task_instruction from load_scenarios()."""
        res = client.post("/api/benchmark", json={})
        assert res.status_code == 200, res.text
        for r in res.json()["results"]:
            assert r["task_instruction"], f"Empty task_instruction for {r['scenario_id']}"

    def test_benchmark_assigned_tiers_are_strings(self, app, client):
        """assigned_tiers must be serialized as tier value strings."""
        res = client.post("/api/benchmark", json={})
        assert res.status_code == 200, res.text
        for r in res.json()["results"]:
            for tier in r["assigned_tiers"]:
                assert isinstance(tier, str), f"Expected str tier, got {type(tier)}"
                assert tier in ("AUTO_ALLOW", "LOG_AND_MONITOR", "HUMAN_REVIEW")

    def test_benchmark_config_used_reflected(self, app, client):
        """config_used should reflect the values passed in (or defaults)."""
        res = client.post(
            "/api/benchmark",
            json={"w1": 0.5, "w2": 0.3, "w3": 0.2, "tau1": 0.1, "tau2": 0.4},
        )
        assert res.status_code == 200, res.text
        config_used = res.json()["config_used"]
        assert config_used["w1"] == pytest.approx(0.5)
        assert config_used["w2"] == pytest.approx(0.3)
        assert config_used["w3"] == pytest.approx(0.2)
        assert config_used["tau1"] == pytest.approx(0.1)
        assert config_used["tau2"] == pytest.approx(0.4)

    def test_benchmark_extreme_taus_make_all_high_auto_allow(self, app, client):
        """With tau1=0.9,tau2=0.95 every score < 0.9 => AUTO_ALLOW => all high scenarios are unsafe."""
        res = client.post(
            "/api/benchmark",
            json={"tau1": 0.9, "tau2": 0.95},
        )
        assert res.status_code == 200, res.text
        data = res.json()
        summary = data["summary"]
        # All high scenarios auto-allowed => unsafe_execution_rate should be 1.0
        assert summary["unsafe_execution_rate"] == pytest.approx(1.0), (
            f"Expected unsafe_execution_rate=1.0, got {summary['unsafe_execution_rate']}"
        )

    def test_benchmark_tau1_gte_tau2_422(self, app, client):
        """tau1 >= tau2 should return 422."""
        res = client.post("/api/benchmark", json={"tau1": 0.5, "tau2": 0.3})
        assert res.status_code == 422

    def test_benchmark_does_not_modify_shared_failure_db(self, app, client):
        """Running /api/benchmark must not change the shared failure-rate DB."""
        db_path = app.state.server_state.db_path
        rows_before = _dump_failure_rows(db_path)

        res = client.post("/api/benchmark", json={})
        assert res.status_code == 200, res.text

        rows_after = _dump_failure_rows(db_path)
        assert rows_before == rows_after, (
            "Shared failure-rate DB was modified by /api/benchmark!\n"
            f"Before: {rows_before}\nAfter: {rows_after}"
        )

    def test_benchmark_summary_has_all_metric_fields(self, app, client):
        """Summary must include all BenchmarkSummaryMetrics fields."""
        res = client.post("/api/benchmark", json={})
        assert res.status_code == 200, res.text
        summary = res.json()["summary"]
        required_fields = [
            "total_scenarios",
            "low_risk_count",
            "medium_risk_count",
            "high_risk_count",
            "unsafe_execution_rate",
            "false_positive_rate",
            "avg_baseline_latency_ms",
            "avg_cgtel_latency_ms",
            "avg_latency_overhead_ms",
        ]
        for field in required_fields:
            assert field in summary, f"Missing summary field: {field}"


# ── /api/reset-history tests ──────────────────────────────────────────────────


class TestResetHistory:

    def test_reset_without_confirm_400(self, app, client):
        """Calling /api/reset-history without confirm=true must return 400."""
        res = client.post("/api/reset-history", json={"confirm": False})
        assert res.status_code == 400

        res2 = client.post("/api/reset-history", json={})
        assert res2.status_code == 400

    def test_reset_with_confirm_clears_table(self, app, client):
        """After one executed run, reset-history reverts tool to cold-start failure rate."""
        state = app.state.server_state

        # Execute one run so the DB has a row for fake_payment_call
        task = "Process a subscription payment of 149.99 USD for account acc_user_4042."
        res = client.post("/api/runs", json={"task": task, "mode": "offline"})
        assert res.status_code == 200
        run_id = res.json()["run_id"]

        session = state.run_manager.get_run(run_id)
        assert session.review_pending_event.wait(timeout=5.0)
        client.post(f"/api/runs/{run_id}/review", json={"approve": True})
        assert session.done_event.wait(timeout=5.0)
        assert session.status == "EXECUTED"

        # Confirm a DB row exists now
        rows_before = _dump_failure_rows(state.db_path)
        assert len(rows_before) >= 1, "Expected at least one row after run"

        # Reset
        res_reset = client.post("/api/reset-history", json={"confirm": True})
        assert res_reset.status_code == 200, res_reset.text
        data = res_reset.json()
        assert data["cleared"] is True
        assert data["default_failure_rate"] == pytest.approx(0.1)

        # Table must be empty now
        rows_after = _dump_failure_rows(state.db_path)
        assert rows_after == [], f"Expected empty table after reset, got: {rows_after}"

        # The tool's failure rate should be back to cold-start default (0.1)
        rate = state.failure_store.get_failure_rate("fake_payment_call")
        assert rate == pytest.approx(0.1)

    def test_reset_refused_while_run_active(self, app, client):
        """Reset must return 409 while a run is active (waiting for review)."""
        task = "Process a subscription payment of 149.99 USD for account acc_user_4042."
        res = client.post("/api/runs", json={"task": task, "mode": "offline"})
        assert res.status_code == 200
        run_id = res.json()["run_id"]

        session = app.state.server_state.run_manager.get_run(run_id)
        assert session.review_pending_event.wait(timeout=5.0)

        # Attempt reset while active
        reset_res = client.post("/api/reset-history", json={"confirm": True})
        assert reset_res.status_code == 409

        # Clean up: approve the run
        client.post(f"/api/runs/{run_id}/review", json={"approve": True})
        assert session.done_event.wait(timeout=5.0)


# ── cross-check: score + benchmark don't corrupt shared DB together ──────────


class TestNoDbCorruption:

    def test_score_then_benchmark_then_score_leaves_db_unchanged(self, app, client):
        """Heavy mix of /api/score and /api/benchmark must not touch the shared failure DB."""
        db_path = app.state.server_state.db_path
        rows_before = _dump_failure_rows(db_path)

        for _ in range(5):
            client.post(
                "/api/score",
                json={
                    "tool_name": "fake_payment_call",
                    "args": {},
                    "confidence": 0.8,
                },
            )
        client.post("/api/benchmark", json={})
        for _ in range(5):
            client.post(
                "/api/score",
                json={
                    "tool_name": "fake_file_delete",
                    "args": {},
                    "confidence": 0.6,
                },
            )

        rows_after = _dump_failure_rows(db_path)
        assert rows_before == rows_after
