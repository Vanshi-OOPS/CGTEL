from datetime import datetime, timezone
import pytest
from cgtel.interceptor import gated_tool
from cgtel.types import RiskDecision, RiskTier, ToolCallRequest


def test_gated_tool_interception():
    @gated_tool
    def add(a: int, b: int = 5) -> int:
        """Add two numbers."""
        return a + b

    # Test docstring and function metadata preservation
    assert add.__name__ == "add"
    assert add.__doc__ == "Add two numbers."

    # Execute wrapped function
    res = add(10, b=20)
    assert res == 30

    # Verify intercepted request details
    req = getattr(add, "last_request", None)
    assert req is not None
    assert isinstance(req, ToolCallRequest)
    assert req.tool_name == "add"
    assert req.args == {"a": 10, "b": 20}
    assert req.task_context == ""
    assert isinstance(req.timestamp, datetime)
    assert req.timestamp.tzinfo == timezone.utc

    # Verify intercepted decision details
    dec = getattr(add, "last_decision", None)
    assert dec is not None
    assert isinstance(dec, RiskDecision)
    assert isinstance(dec.tier, RiskTier)


def test_gated_tool_with_context():
    @gated_tool(task_context="audit_log_context")
    def execute_query(query: str, limit: int = 100):
        return f"Executed: {query} (limit={limit})"

    res = execute_query("SELECT * FROM users")
    assert res == "Executed: SELECT * FROM users (limit=100)"

    req = getattr(execute_query, "last_request", None)
    assert req is not None
    assert req.tool_name == "execute_query"
    assert req.args == {"query": "SELECT * FROM users", "limit": 100}
    assert req.task_context == "audit_log_context"


def test_gated_tool_pipeline_tiers():
    @gated_tool
    def read_config():
        return "OK"

    @gated_tool
    def delete_cache():
        return "DELETED"

    @gated_tool
    def payment_process():
        return "PAID"

    # read_config -> AUTO_ALLOW
    res1 = read_config()
    assert res1 == "OK"
    assert read_config.last_decision.tier == RiskTier.AUTO_ALLOW

    # delete_cache -> LOG_AND_MONITOR
    res2 = delete_cache()
    assert res2 == "DELETED"
    assert delete_cache.last_decision.tier == RiskTier.LOG_AND_MONITOR

    # payment_process without approval -> PermissionError
    with pytest.raises(PermissionError):
        payment_process(_auto_approve=False)

    # payment_process with approval -> PAID
    res3 = payment_process(_auto_approve=True)
    assert res3 == "PAID"
    assert payment_process.last_decision.tier == RiskTier.HUMAN_REVIEW


def test_dataclasses():
    req = ToolCallRequest(
        tool_name="test_tool",
        args={"key": "val"},
        task_context="ctx",
    )
    assert req.tool_name == "test_tool"
    assert req.args == {"key": "val"}
    assert req.task_context == "ctx"
    assert isinstance(req.timestamp, datetime)

    decision = RiskDecision(
        score=0.15,
        tier=RiskTier.AUTO_ALLOW,
        contributing_signals={"signal_a": 0.1},
    )
    assert decision.score == 0.15
    assert decision.tier == RiskTier.AUTO_ALLOW
    assert decision.contributing_signals == {"signal_a": 0.1}
