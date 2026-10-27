"""Unit and integration tests for CGTEL server endpoints."""
import json
import time
import pytest
from starlette.testclient import TestClient

from server.app import create_app
from server.config import Settings


def test_health_endpoint(client: TestClient):
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "live_available" in data
    assert "model" in data
    assert "mode_default" in data


def test_config_endpoint(client: TestClient):
    response = client.get("/api/config")
    assert response.status_code == 200
    data = response.json()
    assert "weights" in data
    assert "tau1" in data
    assert "tau2" in data
    assert "tools" in data
    tools = {t["name"]: t for t in data["tools"]}
    assert "fake_file_read" in tools
    assert "fake_file_delete" in tools
    assert "fake_payment_call" in tools
    assert len(tools["fake_file_read"]["params"]) >= 1


def test_a_offline_read_auto_allow(app, client: TestClient):
    """Test (a): offline run of Read config ends EXECUTED with tier AUTO_ALLOW."""
    task = "Read the application configuration file config/app_settings.json."
    res = client.post("/api/runs", json={"task": task, "mode": "offline"})
    assert res.status_code == 200
    run_id = res.json()["run_id"]

    manager = app.state.server_state.run_manager
    session = manager.get_run(run_id)
    assert session is not None
    assert session.done_event.wait(timeout=5.0)

    assert session.status == "EXECUTED"
    assert session.tool_name == "fake_file_read"
    assert session.result == "Content of 'config/app_settings.json'"
    assert session.serialized_decision is not None
    assert session.serialized_decision["tier"] == "AUTO_ALLOW"
    assert session.serialized_decision["assessed"] is True
    # R includes the read severity prior and cold-start failure rate.
    assert round(session.serialized_decision["score"], 4) == 0.075

    # Test SSE replay
    sse_res = client.get(f"/api/runs/{run_id}/events")
    assert sse_res.status_code == 200
    body = sse_res.text
    assert "event: run_started" in body
    assert "event: scored" in body
    assert "event: run_finished" in body
    assert "AUTO_ALLOW" in body


def test_b_offline_payment_denied_by_human_review(app, client: TestClient):
    """Test (b): payment task pauses at review_required, POST review approve=false ends DENIED_BY_HUMAN_REVIEW and payment body never ran."""
    task = "Process a subscription payment of 149.99 USD for account acc_user_4042."
    res = client.post("/api/runs", json={"task": task, "mode": "offline"})
    assert res.status_code == 200
    run_id = res.json()["run_id"]

    manager = app.state.server_state.run_manager
    session = manager.get_run(run_id)
    assert session is not None

    # Wait until it pauses at review_required
    assert session.review_pending_event.wait(timeout=5.0)
    assert session.review_pending is True

    # Check review_required payload
    history = [e for e in session.events_history if e[0] == "review_required"]
    assert len(history) == 1
    rev_data = history[0][1]
    assert rev_data["tool_name"] == "fake_payment_call"
    assert rev_data["args"]["amount"] == 149.99
    assert rev_data["score"] == pytest.approx(0.675, abs=1e-6)
    assert rev_data["tau2"] == 0.35
    assert rev_data["timeout_seconds"] > 0
    assert "reversibility" in rev_data["signals"]

    # Reject the review
    rev_res = client.post(f"/api/runs/{run_id}/review", json={"approve": False})
    assert rev_res.status_code == 200
    assert rev_res.json()["approved"] is False

    assert session.done_event.wait(timeout=5.0)
    assert session.status == "DENIED_BY_HUMAN_REVIEW"
    # Payment body never ran: result is None
    assert session.result is None
    assert session.serialized_decision["tier"] == "HUMAN_REVIEW"
    assert session.serialized_decision["assessed"] is True

    # Check outcome log
    assert session.outcome_log is not None
    assert session.outcome_log["outcome"] == "denied"


def test_c_offline_payment_approved_executed(app, client: TestClient):
    """Test (c): payment task pauses at review_required, approve=true ends EXECUTED."""
    task = "Process a subscription payment of 149.99 USD for account acc_user_4042."
    res = client.post("/api/runs", json={"task": task, "mode": "offline"})
    assert res.status_code == 200
    run_id = res.json()["run_id"]

    manager = app.state.server_state.run_manager
    session = manager.get_run(run_id)
    assert session is not None

    assert session.review_pending_event.wait(timeout=5.0)
    assert session.review_pending is True

    rev_res = client.post(f"/api/runs/{run_id}/review", json={"approve": True})
    assert rev_res.status_code == 200
    assert rev_res.json()["approved"] is True

    assert session.done_event.wait(timeout=5.0)
    assert session.status == "EXECUTED"
    assert session.result == {
        "status": "SUCCESS",
        "transaction_id": "tx_9988776655",
    }
    assert session.serialized_decision["assessed"] is True


def test_e_concurrent_second_run_gets_409(app, client: TestClient):
    """Test (e): a concurrent second run gets 409 while the first is active."""
    task1 = "Process a subscription payment of 149.99 USD for account acc_user_4042."
    res1 = client.post("/api/runs", json={"task": task1, "mode": "offline"})
    assert res1.status_code == 200
    run_id1 = res1.json()["run_id"]

    manager = app.state.server_state.run_manager
    session1 = manager.get_run(run_id1)
    assert session1.review_pending_event.wait(timeout=5.0)

    # Attempt second run while first is waiting for review
    task2 = "Read the application configuration file config/app_settings.json."
    res2 = client.post("/api/runs", json={"task": task2, "mode": "offline"})
    assert res2.status_code == 409
    assert "currently active" in res2.json()["detail"]

    # Now resolve first run to cleanly release lock
    client.post(f"/api/runs/{run_id1}/review", json={"approve": True})
    assert session1.done_event.wait(timeout=5.0)

    # After completion, subsequent run succeeds
    res3 = client.post("/api/runs", json={"task": task2, "mode": "offline"})
    assert res3.status_code == 200
    run_id3 = res3.json()["run_id"]
    session3 = manager.get_run(run_id3)
    assert session3.done_event.wait(timeout=5.0)
    assert session3.status == "EXECUTED"


def test_f_review_timeout_denies(tmp_path):
    """Test (f): review timeout denies when no review is posted (using ~1s timeout)."""
    settings = Settings(
        server_data_dir=str(tmp_path / "server_data"),
        review_timeout=1.0,
    )
    application = create_app(settings)
    with TestClient(application) as custom_client:
        task = "Process a subscription payment of 149.99 USD for account acc_user_4042."
        res = custom_client.post("/api/runs", json={"task": task, "mode": "offline"})
        assert res.status_code == 200
        run_id = res.json()["run_id"]

        manager = application.state.server_state.run_manager
        session = manager.get_run(run_id)

        # Do NOT post review; wait for timeout (~1.0s)
        assert session.done_event.wait(timeout=4.0)
        assert session.status == "DENIED_BY_HUMAN_REVIEW"
        assert session.result is None

        # Verify review_timeout event was recorded
        timeout_events = [
            e for e in session.events_history if e[0] == "review_timeout"
        ]
        assert len(timeout_events) == 1
        assert timeout_events[0][1]["timeout_seconds"] == 1.0


def test_stats_and_runs_listing(app, client: TestClient):
    """Verify GET /api/runs and GET /api/stats reflect executed and denied runs."""
    # 1. Run read (executed)
    r1 = client.post(
        "/api/runs",
        json={
            "task": "Read the application configuration file config/app_settings.json.",
            "mode": "offline",
        },
    )
    s1 = app.state.server_state.run_manager.get_run(r1.json()["run_id"])
    assert s1.done_event.wait(timeout=5.0)

    # 2. Run payment (denied)
    r2 = client.post(
        "/api/runs",
        json={
            "task": "Process a subscription payment of 149.99 USD for account acc_user_4042.",
            "mode": "offline",
        },
    )
    s2 = app.state.server_state.run_manager.get_run(r2.json()["run_id"])
    assert s2.review_pending_event.wait(timeout=5.0)
    client.post(f"/api/runs/{s2.run_id}/review", json={"approve": False})
    assert s2.done_event.wait(timeout=5.0)

    # Query /api/runs
    runs_res = client.get("/api/runs?limit=10")
    assert runs_res.status_code == 200
    runs_list = runs_res.json()
    assert len(runs_list) >= 2
    # Newest first
    assert runs_list[0]["run_id"] == s2.run_id
    assert runs_list[1]["run_id"] == s1.run_id

    # Query /api/stats
    stats_res = client.get("/api/stats")
    assert stats_res.status_code == 200
    stats = stats_res.json()
    totals = stats["totals"]
    assert totals["executed"] >= 1
    assert totals["denied"] >= 1
    # Check tool stats in sqlite
    tools = {t["tool_name"]: t for t in stats["tools"]}
    assert "fake_file_read" in tools
    assert tools["fake_file_read"]["total_calls"] >= 1


def test_review_errors(app, client: TestClient):
    # 404 for unknown run
    res = client.post("/api/runs/nonexistent_run/review", json={"approve": True})
    assert res.status_code == 404

    # 409 when no review is pending (completed run)
    r = client.post(
        "/api/runs",
        json={
            "task": "Read the application configuration file config/app_settings.json.",
            "mode": "offline",
        },
    )
    s = app.state.server_state.run_manager.get_run(r.json()["run_id"])
    assert s.done_event.wait(timeout=5.0)
    res2 = client.post(f"/api/runs/{s.run_id}/review", json={"approve": True})
    assert res2.status_code == 409


def test_g_rejected_run_assessed_false(app, client: TestClient, monkeypatch):
    """Test (g): a REJECTED run (unsupported tool) serializes with assessed=False, score=None, tier=None."""
    from cgtel.agent.llm_agent import LLMAgent

    def _fake_fallback(self, task_instruction):
        return "nonexistent_tool_xyz", {}

    monkeypatch.setattr(LLMAgent, "_rule_based_fallback", _fake_fallback)

    res = client.post("/api/runs", json={"task": "do something unusual", "mode": "offline"})
    assert res.status_code == 200
    run_id = res.json()["run_id"]

    manager = app.state.server_state.run_manager
    session = manager.get_run(run_id)
    assert session is not None
    assert session.done_event.wait(timeout=5.0)

    assert session.status.startswith("REJECTED")
    dec = session.serialized_decision
    assert dec is not None
    assert dec["assessed"] is False
    assert dec["score"] is None
    assert dec["tier"] is None


def test_live_mode_without_key_fails(app, client: TestClient, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    res = client.post("/api/runs", json={"task": "Read file", "mode": "live"})
    assert res.status_code == 400
    assert "Live mode requires GEMINI_API_KEY" in res.json()["detail"]
