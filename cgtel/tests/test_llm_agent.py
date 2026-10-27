import pytest
from cgtel.agent.llm_agent import GEMINI_TOOLS, LLMAgent
from cgtel.types import RiskTier


def test_gemini_tools_schema():
    assert isinstance(GEMINI_TOOLS, list)
    assert len(GEMINI_TOOLS) == 3
    tool_names = [t.__name__ for t in GEMINI_TOOLS]
    assert "fake_file_read" in tool_names
    assert "fake_file_delete" in tool_names
    assert "fake_payment_call" in tool_names


def test_llm_agent_fallback_mode(monkeypatch):
    # Agent without API key should use fallback natural language parser
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    agent = LLMAgent(api_key=None)

    # 1. Read task -> AUTO_ALLOW
    res1 = agent.run_task("Please read the configuration file app_settings.json", auto_approve=True)
    assert res1["tool_name"] == "fake_file_read"
    assert res1["decision"].tier == RiskTier.AUTO_ALLOW

    # 2. Delete task -> HUMAN_REVIEW floor
    res2 = agent.run_task("Remove and delete temporary session cache", auto_approve=True)
    assert res2["tool_name"] == "fake_file_delete"
    assert res2["decision"].tier == RiskTier.HUMAN_REVIEW

    # 3. Payment task -> HUMAN_REVIEW
    res3 = agent.run_task("Process subscription payment of 149.99 USD", auto_approve=True)
    assert res3["tool_name"] == "fake_payment_call"
    assert res3["decision"].tier == RiskTier.HUMAN_REVIEW
