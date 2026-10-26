import pytest
from google.genai import errors

from cgtel.agent.llm_agent import LLMAgent
from cgtel.logger.outcome_logger import OutcomeLogger
from cgtel.router.decision_router import DecisionRouter
from cgtel.scoring.engine import RiskScoringEngine
from cgtel.signals.failure_rate import HistoricalFailureRateLookup
from cgtel.types import RiskTier


@pytest.fixture(autouse=True)
def no_api_keys(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)


def make_agent(tool_registry=None, review="y"):
    calls = []
    def read(filepath: str):
        calls.append(filepath)
        return "read"
    def delete(filepath: str, recursive: bool = False):
        calls.append(filepath)
        return True
    def payment(account_id: str, amount: float, currency: str = "USD"):
        calls.append((account_id, amount))
        return "paid"
    read.__name__ = "fake_file_read"
    delete.__name__ = "fake_file_delete"
    payment.__name__ = "fake_payment_call"
    registry = tool_registry or {"fake_file_read": read, "fake_file_delete": delete,
                                  "fake_payment_call": payment}
    asked = []
    router = DecisionRouter(input_func=lambda prompt: (asked.append(prompt), review)[1])
    store = HistoricalFailureRateLookup()
    engine = RiskScoringEngine(failure_rate_lookup=store)
    logger = OutcomeLogger()
    agent = LLMAgent(mode="offline", tool_registry=registry, router=router,
                     scoring_engine=engine, outcome_logger=logger)
    return agent, calls, asked, store, logger


def test_offline_read_executes_with_confidence_and_record():
    agent, calls, _, store, log = make_agent()
    result = agent.run_task("read config")
    assert result["status"] == "EXECUTED"
    assert result["llm_mode"] == "offline_fallback"
    assert calls == ["config/app_settings.json"]
    assert result["decision"].tier == RiskTier.AUTO_ALLOW
    assert result["decision"].score == pytest.approx(0.0667, abs=0.001)
    assert result["decision"].contributing_signals["confidence_source"] == "offline_fallback"
    assert log.entries[-1]["outcome"] == "executed_success"
    assert store.get_failure_rate("fake_file_read") == 0.0


def test_medium_delete_and_review_denial_are_enforced():
    agent, calls, asked, store, log = make_agent(review="n")
    result = agent.run_task("delete cache")
    assert result["decision"].tier == RiskTier.LOG_AND_MONITOR
    assert result["decision"].score == pytest.approx(0.30, abs=0.001)
    result = agent.run_task("pay subscription")
    assert result["status"] == "DENIED_BY_HUMAN_REVIEW"
    assert result["decision"].tier == RiskTier.HUMAN_REVIEW
    assert len(asked) == 1
    assert len(calls) == 1
    assert log.entries[-1]["outcome"] == "denied"
    assert store.get_failure_rate("fake_payment_call") == 0.1


def test_malformed_args_are_rejected_without_body_run():
    agent, calls, _, _, log = make_agent()
    agent._rule_based_fallback = lambda task: ("fake_file_read", {"filepath": "x", "_auto_approve": True})
    result = agent.run_task("read")
    assert result["status"] == "REJECTED_INVALID_ARGS"
    assert not calls
    assert log.entries[-1]["outcome"] == "rejected_invalid"


def test_live_api_failure_and_no_call_do_not_fallback(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    agent, calls, _, _, log = make_agent()
    agent.mode = "live"
    agent.client = object()
    agent._query_gemini_once = lambda task: (_ for _ in ()).throw(RuntimeError("network error"))
    result = agent.run_task("read config")
    assert result["status"] == "LLM_ERROR"
    assert result["llm_mode"] == "live"
    assert not calls
    assert log.entries[-1]["outcome"] == "llm_error"
    assert result["assessment_status"] == "NOT_ASSESSED"
    assert result["decision"].tier is None
    assert result["decision"].score is None
    assert result["outcome_log"]["tier"] is None
    assert result["outcome_log"]["score"] is None


def test_gemini_503_is_not_assessed_and_never_routed():
    agent, calls, asked, _, log = make_agent()
    agent.mode = "live"

    class Models:
        def generate_content(self, **kwargs):
            raise errors.ServerError(503, {"error": {"message": "high demand"}})

    agent.client = type("Client", (), {"models": Models()})()
    result = agent.run_task("Process a payment")

    assert result["status"] == "LLM_ERROR"
    assert result["assessment_status"] == "NOT_ASSESSED"
    assert result["decision"].tier is None
    assert result["decision"].score is None
    assert result["outcome_log"]["tier"] is None
    assert result["outcome_log"]["score"] is None
    assert result["outcome_log"]["signals"]["assessment_status"] == "NOT_ASSESSED"
    assert result["outcome_log"]["outcome"] == "llm_error"
    assert calls == []
    assert asked == []


def test_confidence_values_change_risk_tier():
    agent, calls, _, _, _ = make_agent()
    agent.mode = "live"
    agent.client = object()
    votes = iter([("fake_file_read", {"filepath": "x"}, None, []),
                  ("fake_file_read", {"filepath": "y"}, None, []),
                  ("fake_file_read", {"filepath": "z"}, None, [])])
    agent._query_gemini_once = lambda task: next(votes)
    result = agent.run_task("read")
    assert result["extracted_confidence"] == pytest.approx(1 / 3)
    assert result["decision"].contributing_signals["confidence"] == pytest.approx(1 / 3, abs=0.0001)
    assert result["decision"].score == pytest.approx(0.2556, abs=0.001)
    assert result["decision"].tier == RiskTier.LOG_AND_MONITOR
    assert result["decision"].contributing_signals["confidence_source"] == "llm_self_consistency"


def test_explicit_confidence_is_clamped_by_engine():
    engine = RiskScoringEngine()
    _, signals = engine.evaluate("fake_file_read", {}, confidence=4, confidence_source="test")
    assert signals["confidence"] == 1.0
    assert signals["confidence_source"] == "test"


@pytest.mark.parametrize("tool,args,status", [
    ("not_registered", {"filepath": "x"}, "REJECTED_UNSUPPORTED_TOOL"),
    ("fake_file_read", {}, "REJECTED_INVALID_ARGS"),
    ("fake_file_read", {"filepath": "x", "_confidence": 1.0}, "REJECTED_INVALID_ARGS"),
    ("fake_payment_call", {"account_id": "a"}, "REJECTED_INVALID_ARGS"),
    ("fake_payment_call", {"account_id": "a", "amount": "oops"}, "REJECTED_INVALID_ARGS"),
])
def test_invalid_proposals_never_execute(tool, args, status):
    agent, calls, _, _, log = make_agent()
    agent._rule_based_fallback = lambda task: (tool, args)
    result = agent.run_task("proposal")
    assert result["status"] == status
    assert calls == []
    assert log.entries[-1]["outcome"] == "rejected_invalid"


def test_missing_human_approval_denies_on_eof():
    agent, calls, _, _, log = make_agent()
    agent.router = DecisionRouter(input_func=lambda prompt: (_ for _ in ()).throw(EOFError()))
    result = agent.run_task("pay subscription")
    assert result["status"] == "DENIED_BY_HUMAN_REVIEW"
    assert result["decision"].tier == RiskTier.HUMAN_REVIEW
    assert calls == []
    assert log.entries[-1]["outcome"] == "denied"


def test_live_no_function_call_is_not_fallback():
    agent, calls, _, _, log = make_agent()
    agent.mode = "live"
    agent.client = object()
    agent._query_gemini_once = lambda task: (None, None, object(), [])
    result = agent.run_task("read")
    assert result["status"] == "NO_TOOL_CALL"
    assert result["llm_mode"] == "live"
    assert calls == []
    assert log.entries[-1]["outcome"] == "llm_error"


def test_gemini_config_disables_automatic_function_calling():
    agent, _, _, _, _ = make_agent()
    captured = {}
    class Models:
        def generate_content(self, **kwargs):
            captured.update(kwargs)
            return type("Response", (), {"function_calls": []})()
    agent.client = type("Client", (), {"models": Models()})()
    agent.mode = "live"
    agent._query_gemini_once("test")
    config = captured["config"]
    assert config.automatic_function_calling.disable is True
    assert config.tools
