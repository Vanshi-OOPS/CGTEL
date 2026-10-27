"""Focused plain-message generation test with a mocked Gemini response."""

from types import SimpleNamespace

import pytest

import server.chat as chat_module
from server.chat import ChatSession, ModelsUnavailableError, _agreement_signature, _run_turn


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_plain_message_returns_text_without_tool_events(monkeypatch):
    monkeypatch.setenv("GEMINI_MODEL", "test-model")
    monkeypatch.setenv("GEMINI_MODEL_FALLBACKS", "")

    class FakeModels:
        async def generate_content(self, **kwargs):
            assert kwargs["model"] == "test-model"
            return SimpleNamespace(text="Hello!", candidates=[])

    agent = SimpleNamespace(
        model_name="unused-model",
        api_key=None,
        client=SimpleNamespace(aio=SimpleNamespace(models=FakeModels())),
    )
    reply, tool_events, error = await _run_turn(
        agent, "plain-hi-test", ChatSession(), state=None
    )

    assert reply.strip()
    assert tool_events == []
    assert error is None


def _function_response(name, args):
    call = SimpleNamespace(name=name, args=args)
    content = SimpleNamespace(parts=[SimpleNamespace(function_call=call)])
    return SimpleNamespace(candidates=[SimpleNamespace(content=content)], text=None)


def _tool_state():
    class Scoring:
        @staticmethod
        def compute_decision(tool_name, args):
            return SimpleNamespace(score=0.2)

    return SimpleNamespace(scoring_engine=Scoring())


@pytest.mark.anyio
async def test_chat_normalizes_read_paths_and_uses_three_sample_agreement(monkeypatch, tmp_path):
    import server.chat_tools as chat_tools

    (tmp_path / "red.txt").write_text("sample", encoding="utf-8")
    monkeypatch.setattr(chat_tools, "SANDBOX_DIR", tmp_path)
    assert _agreement_signature("read_file", {"filepath": "sandbox/notes.txt"}) == _agreement_signature(
        "READ_FILE", {"filepath": r".\notes.txt"}
    )
    assert _agreement_signature("read_file", {"filepath": '"sandbox/RED"'}) == _agreement_signature(
        "read_file", {"filepath": "red.txt"}
    )
    responses = [
        _function_response("read_file", {"filepath": "sandbox/notes.txt"}),
        _function_response("read_file", {"filepath": "notes.txt"}),
        _function_response("read_file", {"filepath": r".\notes.txt"}),
        SimpleNamespace(candidates=[], text="The notes are ready."),
    ]

    async def fake_generate(*args, **kwargs):
        return responses.pop(0)

    calls = []

    def fake_gate(tool_name, args, **kwargs):
        calls.append((tool_name, args, kwargs))
        return {
            "status": "executed", "risk": 0.03, "decision": "AUTO_ALLOW",
            "score_breakdown": {"V": 0.0, "C": kwargs["confidence"], "F": 0.1,
                                "weights": {"w1": 1 / 3, "w2": 1 / 3, "w3": 1 / 3},
                                "R": 0.03, "decision": "AUTO_ALLOW", "degraded": kwargs["degraded"]},
        }

    monkeypatch.setattr(chat_module, "_generate", fake_generate)
    monkeypatch.setattr(chat_module, "gated_call", fake_gate)
    reply, events, error = await _run_turn(SimpleNamespace(), "agreement-test", ChatSession(), _tool_state())

    assert reply == "The notes are ready."
    assert error is None
    assert len(calls) == 1
    assert calls[0][2]["confidence"] == 1.0
    assert calls[0][2]["degraded"] is False
    assert events[0]["decision"] == "AUTO_ALLOW"


def test_missing_read_file_is_an_execution_result_not_an_exception(tmp_path, monkeypatch):
    import server.chat_tools as chat_tools

    monkeypatch.setattr(chat_tools, "SANDBOX_DIR", tmp_path)
    result = chat_tools.read_file("red")
    assert result["error"] == "file not found"
    assert result["filepath"] == "red"


@pytest.mark.anyio
async def test_chat_failed_sample_is_degraded_and_excluded_from_agreement(monkeypatch):
    responses = [
        _function_response("read_file", {"filepath": "notes.txt"}),
        ModelsUnavailableError("sample unavailable"),
        _function_response("read_file", {"filepath": "sandbox/notes.txt"}),
        SimpleNamespace(candidates=[], text="Read complete."),
    ]

    async def fake_generate(*args, **kwargs):
        next_response = responses.pop(0)
        if isinstance(next_response, Exception):
            raise next_response
        return next_response

    calls = []

    def fake_gate(tool_name, args, **kwargs):
        calls.append(kwargs)
        return {
            "status": "executed", "risk": 0.03, "decision": "AUTO_ALLOW",
            "score_breakdown": {"V": 0.0, "C": kwargs["confidence"], "F": 0.1,
                                "weights": {"w1": 1 / 3, "w2": 1 / 3, "w3": 1 / 3},
                                "R": 0.03, "decision": "AUTO_ALLOW", "degraded": kwargs["degraded"]},
        }

    monkeypatch.setattr(chat_module, "_generate", fake_generate)
    monkeypatch.setattr(chat_module, "gated_call", fake_gate)
    _, events, error = await _run_turn(SimpleNamespace(), "degraded-test", ChatSession(), _tool_state())

    assert error is None
    assert calls[0]["confidence"] == 1.0
    assert calls[0]["degraded"] is True
    assert events[0]["score_breakdown"]["degraded"] is True
