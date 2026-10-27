"""Coverage for shared per-tool F priors and decision floors."""

import server.chat_tools as chat_tools
from server.config import Settings
from server.gated_executor import gated_call
from server.state import ServerState


def test_floor_is_visible_in_gated_event_and_run_ledger(tmp_path, monkeypatch):
    sandbox = tmp_path / "sandbox"
    sandbox.mkdir()
    monkeypatch.setattr(chat_tools, "SANDBOX_DIR", sandbox)
    state = ServerState(Settings(server_data_dir=str(tmp_path / "data"), review_timeout=5))
    try:
        # A low what-if F value makes the configured LOG_AND_MONITOR floor raise
        # this write from AUTO_ALLOW while keeping the production formula intact.
        state.scoring_engine.severity_priors["write_file"] = 0.0
        result = gated_call(
            "write_file",
            {"filepath": "log.txt", "content": "floor test"},
            state=state,
            confidence=1.0,
            confidence_source="test",
        )

        breakdown = result["score_breakdown"]
        assert breakdown["score_based_decision"] == "AUTO_ALLOW"
        assert breakdown["floor"] == "LOG_AND_MONITOR"
        assert breakdown["floor_applied"] is True
        assert breakdown["decision"] == "LOG_AND_MONITOR"

        run_id = state.run_manager._runs_order[-1]
        record = state.run_manager.get_run(run_id).to_record()
        assert record["decision"]["signals"]["floor_applied"] is True
        assert record["decision"]["signals"]["floor"] == "LOG_AND_MONITOR"
        assert record["outcome_log"]["score_breakdown"]["decision"] == "LOG_AND_MONITOR"
    finally:
        state.shutdown()
