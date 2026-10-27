"""Regression coverage for the Desk human-review approval flow."""


def _start_payment_review(client, app):
    response = client.post(
        "/api/runs",
        json={"task": "pay rohan 5000", "mode": "offline"},
    )
    assert response.status_code == 200
    run_id = response.json().get("run_id")
    assert isinstance(run_id, str) and run_id

    session = app.state.server_state.run_manager.get_run(run_id)
    assert session is not None
    assert session.review_pending_event.wait(timeout=5)
    assert session.review_pending
    return run_id, session


def test_desk_payment_approval_executes_and_updates_telemetry(client, app):
    run_id, session = _start_payment_review(client, app)

    response = client.post(f"/api/runs/{run_id}/review", json={"approve": True})
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "run_id": run_id, "approved": True}
    assert session.done_event.wait(timeout=5)
    assert session.status == "EXECUTED"
    assert session.result == {
        "status": "SUCCESS",
        "transaction_id": "tx_9988776655",
    }

    event_types = [event_type for event_type, _ in session.events_history]
    assert "review_resolved" in event_types
    assert event_types.index("review_resolved") < event_types.index("run_finished")
    finished = next(data for kind, data in session.events_history if kind == "run_finished")
    assert finished.get("result") == session.result
    assert finished.get("status") == "EXECUTED"

    stats_response = client.get("/api/stats")
    assert stats_response.status_code == 200
    stats = stats_response.json()
    assert stats.get("session_totals", {}).get("executed", 0) >= 1
    payment_stats = next(
        (tool for tool in (stats.get("tools") or []) if tool.get("tool_name") == "fake_payment_call"),
        None,
    )
    assert payment_stats is not None
    assert payment_stats.get("total_calls", 0) >= 1


def test_desk_payment_denial_does_not_execute(client, app):
    run_id, session = _start_payment_review(client, app)

    response = client.post(f"/api/runs/{run_id}/review", json={"approve": False})
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "run_id": run_id, "approved": False}
    assert session.done_event.wait(timeout=5)
    assert session.status == "DENIED_BY_HUMAN_REVIEW"
    assert session.result is None
    assert session.outcome_log is not None
    assert session.outcome_log.get("outcome") == "denied"

    event_types = [event_type for event_type, _ in session.events_history]
    assert "review_resolved" in event_types
    assert event_types.index("review_resolved") < event_types.index("run_finished")
    finished = next(data for kind, data in session.events_history if kind == "run_finished")
    assert finished.get("status") == "DENIED_BY_HUMAN_REVIEW"
    assert finished.get("result") is None
