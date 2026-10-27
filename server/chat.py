"""Gemini chat endpoint with CGTEL-gated sandbox tools."""

from __future__ import annotations

import json
import asyncio
import os
import posixpath
import random
import threading
import unicodedata
from dataclasses import dataclass, field
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from google.genai import types
from pydantic import BaseModel, Field

from cgtel.logger import logger
from server.chat_tools import CHAT_TOOLS
from server.chat_tools import SANDBOX_DIR
from server.gated_executor import gated_call, resolve_pending
from server.routers import get_server_state
from server.state import ServerState


router = APIRouter(tags=["chat"])
MAX_TOOL_CALLS = 4
_SYSTEM_INSTRUCTION = (
    "You are the CGTEL security assistant. For each user message, call at most ONE tool, "
    "and only call the specific tool needed to do exactly what the user requested. "
    "Never read files to verify or check a payment, email, or deletion the user asked you "
    "to perform. Do not perform extra investigative actions. If tool results say other "
    "proposed calls were skipped, do not mention those skipped calls to the user; reply "
    "only about the one requested action. Tool execution is gated by CGTEL policy; "
    "describe pending approvals clearly and never claim a tool succeeded unless its result says it executed."
)


class ChatRequest(BaseModel):
    session_id: str = Field(min_length=1)
    message: str = Field(min_length=1)


class ChatApproveRequest(BaseModel):
    run_id: str = Field(min_length=1)
    approved: bool


@dataclass
class ChatSession:
    history: list[types.Content] = field(default_factory=list)
    blocked_calls: dict[str, dict[str, Any]] = field(default_factory=dict)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


@dataclass
class PendingChatCall:
    session_id: str
    tool: str
    args: dict[str, Any]


_sessions: dict[str, ChatSession] = {}
_pending_chats: dict[str, PendingChatCall] = {}
_sessions_lock = threading.Lock()
_pending_lock = threading.Lock()
_MODEL_BUSY_REPLY = "Model busy, try again in a moment."


class ModelsUnavailableError(Exception):
    """Raised internally after configured model attempts have been exhausted."""


def _fallback_models() -> list[str]:
    configured = os.getenv("GEMINI_MODEL_FALLBACKS")
    if configured is None:
        configured = "gemini-2.5-flash-lite"
    return [model.strip() for model in configured.split(",") if model.strip()]


def _chat_model() -> str:
    return os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip() or "gemini-2.5-flash"


def _log_model_error(agent: Any, model: str, error: Exception) -> None:
    message = str(error)
    secrets = {
        getattr(agent, "api_key", None),
        os.getenv("GEMINI_API_KEY"),
        os.getenv("GOOGLE_API_KEY"),
    }
    for secret in secrets:
        if secret:
            message = message.replace(secret, "[redacted]")
    logger.error("Gemini chat request failed for model %s: %s", model, message)


def _is_transient_error(error: Exception) -> bool:
    for value in (
        getattr(error, "status_code", None),
        getattr(error, "code", None),
        getattr(getattr(error, "response", None), "status_code", None),
    ):
        try:
            if int(value) in {429, 500, 503}:
                return True
        except (TypeError, ValueError):
            pass
    name = type(error).__name__.lower()
    message = str(error).lower()
    return "timeout" in name or "timed out" in message or "timeout" in message


def _gemini_schema(schema: dict[str, Any]) -> dict[str, Any]:
    type_names = {
        "object": "OBJECT", "array": "ARRAY", "string": "STRING",
        "number": "NUMBER", "integer": "INTEGER", "boolean": "BOOLEAN",
    }
    converted: dict[str, Any] = {}
    for key, value in schema.items():
        if key == "additionalProperties":
            continue
        if key == "type" and isinstance(value, str):
            converted[key] = type_names.get(value, value.upper())
        elif key == "properties":
            converted[key] = {name: _gemini_schema(prop) for name, prop in value.items()}
        elif isinstance(value, dict):
            converted[key] = _gemini_schema(value)
        else:
            converted[key] = value
    return converted


_FUNCTION_DECLARATIONS = [
    types.FunctionDeclaration(
        name=tool["name"],
        description=tool["description"],
        parameters=_gemini_schema(tool["parameters"]),
    )
    for tool in CHAT_TOOLS
]
_GEMINI_TOOLS = [types.Tool(function_declarations=_FUNCTION_DECLARATIONS)]


def _get_session(session_id: str) -> ChatSession:
    with _sessions_lock:
        return _sessions.setdefault(session_id, ChatSession())


def _signature(tool_name: str, args: dict[str, Any]) -> str:
    return json.dumps([tool_name, args], sort_keys=True, separators=(",", ":"), default=str)


def _normalized_argument(value: Any, key: str = "") -> Any:
    if isinstance(value, dict):
        return {
            str(name).strip().casefold(): _normalized_argument(item, str(name).strip().casefold())
            for name, item in sorted(value.items(), key=lambda pair: str(pair[0]).casefold())
        }
    if isinstance(value, (list, tuple)):
        return [_normalized_argument(item, key) for item in value]
    if isinstance(value, str):
        normalized = " ".join(unicodedata.normalize("NFKC", value).split()).casefold()
        if key in {"filepath", "path", "file"}:
            normalized = normalized.strip().strip("\"'").strip()
            raw_path = normalized.replace("\\", "/")
            if raw_path.startswith("sandbox/"):
                raw_path = raw_path[len("sandbox/"):]
            # Resolve relative paths against the actual tool sandbox so forms
            # like ./notes.txt and sandbox/notes.txt compare identically.
            candidate = (SANDBOX_DIR / raw_path).resolve(strict=False)
            root = SANDBOX_DIR.resolve()
            try:
                relative = candidate.relative_to(root).as_posix().casefold()
            except ValueError:
                relative = posixpath.normpath(raw_path)
            # If an extensionless path is ambiguous in the prompt, compare it
            # to an existing common-extension sibling when one is present.
            path_obj = SANDBOX_DIR / relative
            if not path_obj.suffix:
                for extension in (".txt", ".md", ".json", ".log", ".csv"):
                    if (SANDBOX_DIR / f"{relative}{extension}").is_file():
                        relative = f"{relative}{extension}"
                        break
            normalized = relative
        return normalized
    return value


def _agreement_signature(tool_name: str, args: dict[str, Any]) -> str:
    normalized_name = tool_name.strip().casefold().replace("-", "_")
    normalized_args = _normalized_argument(args)
    return json.dumps([normalized_name, normalized_args], sort_keys=True, separators=(",", ":"), default=str)


def _highest_risk_call(calls: list[Any], state: ServerState) -> tuple[int, Any, dict[str, Any], float] | None:
    selected: tuple[int, Any, dict[str, Any], float] | None = None
    for index, call in enumerate(calls):
        name = str(call.name)
        args = dict(call.args or {})
        try:
            score = state.scoring_engine.compute_decision(name, args).score
            risk = float(score) if score is not None else -1.0
        except Exception:
            risk = -1.0
        candidate = (index, call, args, risk)
        if selected is None or risk > selected[3]:
            selected = candidate
    return selected


async def _generate(agent: Any, history: list[types.Content], tools_enabled: bool) -> Any:
    config = types.GenerateContentConfig(
        temperature=0.2,
        system_instruction=_SYSTEM_INSTRUCTION,
        **({
            "tools": _GEMINI_TOOLS,
            "automatic_function_calling": types.AutomaticFunctionCallingConfig(disable=True),
        } if tools_enabled else {}),
    )
    primary = _chat_model()
    models = [primary]
    models.extend(model for model in _fallback_models() if model != primary)
    last_error: Exception | None = None
    for model in models:
        for retry in range(4):
            try:
                return await asyncio.wait_for(
                    agent.client.aio.models.generate_content(
                        model=model,
                        contents=history,
                        config=config,
                    ),
                    timeout=30.0,
                )
            except Exception as exc:
                last_error = exc
                if not _is_transient_error(exc):
                    break
                if retry < 3:
                    delay = 2 ** retry
                    await asyncio.sleep(delay + random.uniform(0.0, delay * 0.25))
        if last_error is not None:
            _log_model_error(agent, model, last_error)
    raise ModelsUnavailableError(_MODEL_BUSY_REPLY) from None


def _content_and_calls(response: Any) -> tuple[Any, list[Any]]:
    candidates = getattr(response, "candidates", None) or []
    content = getattr(candidates[0], "content", None) if candidates else None
    parts = getattr(content, "parts", None) or []
    calls = [part.function_call for part in parts if getattr(part, "function_call", None)]
    if not calls:
        calls = getattr(response, "function_calls", None) or []
    return content, list(calls)


def _reply_text(response: Any) -> str:
    text = getattr(response, "text", None)
    if text:
        return str(text)
    candidates = getattr(response, "candidates", None) or []
    if candidates:
        parts = getattr(getattr(candidates[0], "content", None), "parts", None) or []
        return "".join(str(part.text) for part in parts if getattr(part, "text", None))
    return ""


def _call_result(
    session: ChatSession,
    tool_name: str,
    args: dict[str, Any],
    state: ServerState,
    tool_events: list[dict[str, Any]],
    confidence: float,
    degraded: bool,
) -> dict[str, Any]:
    signature = _signature(tool_name, args)
    if signature in session.blocked_calls:
        previous = session.blocked_calls[signature]
        event = {**previous, "status": "not_retried"}
        tool_events.append(event)
        return {"status": "not_retried", "reason": "A prior call with these arguments is pending or was denied."}

    result = gated_call(
        tool_name,
        args,
        state=state,
        confidence=confidence,
        confidence_source="chat_self_consistency",
        degraded=degraded,
    )
    event = {
        "tool": tool_name,
        "args": args,
        "decision": result.get("decision"),
        "risk": result.get("risk"),
        "status": result["status"],
        "score_breakdown": result.get("score_breakdown"),
    }
    if result["status"] == "pending_approval":
        event["run_id"] = result["run_id"]
    tool_events.append(event)
    if result["status"] in ("pending_approval", "denied"):
        session.blocked_calls[signature] = event
    if result["status"] == "pending_approval":
        with _pending_lock:
            _pending_chats[result["run_id"]] = PendingChatCall("", tool_name, args)
    return result


async def _run_turn(
    agent: Any,
    session_id: str,
    session: ChatSession,
    state: ServerState,
) -> tuple[str, list[dict[str, Any]], str | None]:
    tool_events: list[dict[str, Any]] = []
    action_used = False
    model_turns = 0

    while True:
        model_turns += 1
        if model_turns > MAX_TOOL_CALLS + 1:
            if tool_events and tool_events[-1].get("status") == "pending_approval":
                return "The requested action is awaiting human approval.", tool_events, None
            if tool_events and tool_events[-1].get("status") == "executed":
                return "The requested action was completed.", tool_events, None
            return "I could not complete the requested action. Please try again.", tool_events, None
        history_snapshot = list(session.history)
        try:
            response = await _generate(agent, history_snapshot, tools_enabled=not action_used)
        except ModelsUnavailableError:
            return _MODEL_BUSY_REPLY, tool_events, "Gemini models are unavailable after retries."
        assistant_content, calls = _content_and_calls(response)
        if not calls:
            if assistant_content is not None:
                session.history.append(assistant_content)
            reply = _reply_text(response)
            if reply.strip():
                return reply, tool_events, None
            return _MODEL_BUSY_REPLY, tool_events, "Gemini returned an empty response."

        if action_used:
            # Tool calling is disabled after the one routed action. If the model
            # still returns calls, respond with skipped results and no new gate.
            function_responses = [
                types.Part.from_function_response(
                    name=str(call.name),
                    response={"status": "skipped", "reason": "Only one requested action is processed per user message."},
                )
                for call in calls
            ]
            if assistant_content is not None:
                session.history.append(assistant_content)
            session.history.append(types.Content(role="user", parts=function_responses))
            continue

        # The first proposal triggers three independent samples over the same
        # pre-call conversation. Failed calls are excluded from agreement and
        # mark the resulting confidence as degraded.
        samples: list[dict[str, Any]] = []
        degraded = False
        first_best = _highest_risk_call(calls, state)
        samples.append({"content": assistant_content, "calls": calls, "best": first_best})
        for _ in range(2):
            try:
                sample_response = await _generate(agent, history_snapshot, tools_enabled=True)
                sample_content, sample_calls = _content_and_calls(sample_response)
                samples.append({
                    "content": sample_content,
                    "calls": sample_calls,
                    "best": _highest_risk_call(sample_calls, state) if sample_calls else None,
                })
            except Exception as exc:
                degraded = True
                _log_model_error(agent, _chat_model(), exc)

        candidates = [sample for sample in samples if sample["best"] is not None]
        agreement_counts: dict[str, int] = {}
        for sample in candidates:
            _, call, args, _ = sample["best"]
            key = _agreement_signature(str(call.name), args)
            agreement_counts[key] = agreement_counts.get(key, 0) + 1
        valid_sample_count = len(samples)
        if valid_sample_count < 3:
            degraded = True
        winning_key = max(
            agreement_counts,
            key=lambda key: (
                agreement_counts[key],
                max(sample["best"][3] for sample in candidates
                    if _agreement_signature(str(sample["best"][1].name), sample["best"][2]) == key),
            ),
        )
        winning_count = agreement_counts[winning_key]
        confidence = winning_count / valid_sample_count
        selected_sample = next(
            sample for sample in candidates
            if _agreement_signature(str(sample["best"][1].name), sample["best"][2]) == winning_key
        )
        selected_index, selected_call, selected_args, _ = selected_sample["best"]
        selected_name = str(selected_call.name)
        selected_content = selected_sample["content"]
        if selected_content is not None:
            session.history.append(selected_content)

        function_responses: list[types.Part] = []
        selected_calls = selected_sample["calls"]
        for index, call in enumerate(selected_calls):
            name = str(call.name)
            args = dict(call.args or {})
            if selected_index is None or index != selected_index:
                result: dict[str, Any] = {
                    "status": "skipped",
                    "reason": "This proposal was not selected; only one requested action is processed per user message.",
                }
            else:
                action_used = True
                try:
                    result = _call_result(
                        session, selected_name, selected_args, state, tool_events,
                        confidence=confidence,
                        degraded=degraded,
                    )
                    if result["status"] == "pending_approval":
                        with _pending_lock:
                            pending = _pending_chats.get(result["run_id"])
                            if pending:
                                pending.session_id = session_id
                except Exception as exc:
                    result = {"status": "error", "error": str(exc)}
                    tool_events.append({"tool": name, "args": args, "decision": None, "risk": None, "status": "error"})
            function_responses.append(types.Part.from_function_response(name=name, response=result))
        session.history.append(types.Content(role="user", parts=function_responses))


@router.post("/chat")
async def post_chat(
    payload: ChatRequest,
    state: ServerState = Depends(get_server_state),
) -> dict[str, Any]:
    if not state.live_available:
        return {"reply": _MODEL_BUSY_REPLY, "tool_events": [], "error": "Gemini chat is not configured."}
    try:
        agent = state.get_agent("live")
    except Exception as exc:
        _log_model_error(None, _chat_model(), exc)
        return {"reply": _MODEL_BUSY_REPLY, "tool_events": [], "error": "Gemini chat is unavailable."}

    session = _get_session(payload.session_id)
    async with session.lock:
        session.history.append(types.Content(role="user", parts=[types.Part(text=payload.message)]))
        try:
            reply, tool_events, error = await _run_turn(agent, payload.session_id, session, state)
        except Exception as exc:
            _log_model_error(agent, _chat_model(), exc)
            return {"reply": _MODEL_BUSY_REPLY, "tool_events": [], "error": "Gemini chat request failed."}
    # Keep the user-facing state authoritative even if the model's wording is
    # inaccurate after receiving a tool result.
    if any(event.get("status") == "pending_approval" for event in tool_events):
        reply = "This action is awaiting human approval."
    elif any(event.get("status") == "denied" for event in tool_events):
        reply = "The action was denied and was not executed."
    response = {"reply": reply, "tool_events": tool_events}
    if error:
        response["error"] = error
    return response


@router.post("/chat/approve")
async def approve_chat_tool(
    payload: ChatApproveRequest,
    state: ServerState = Depends(get_server_state),
) -> dict[str, Any]:
    if not state.live_available:
        raise HTTPException(status_code=503, detail="Gemini chat requires GEMINI_API_KEY or GOOGLE_API_KEY")
    with _pending_lock:
        pending = _pending_chats.get(payload.run_id)
    if pending is None:
        raise HTTPException(status_code=404, detail="No chat approval is pending for this run")

    session = _get_session(pending.session_id)
    async with session.lock:
        with _pending_lock:
            if _pending_chats.get(payload.run_id) is not pending:
                raise HTTPException(status_code=409, detail="This chat approval has already been resolved")
            _pending_chats.pop(payload.run_id, None)
        try:
            result = resolve_pending(payload.run_id, payload.approved, state=state)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        record = state.run_manager.get_run(payload.run_id)
        event = {
            "tool": pending.tool,
            "args": pending.args,
            "decision": (record.serialized_decision or {}).get("tier") if record else None,
            "risk": (record.serialized_decision or {}).get("score") if record else None,
            "status": result["status"],
            "score_breakdown": getattr(record, "score_breakdown", None) if record else None,
        }
        session.blocked_calls[_signature(pending.tool, pending.args)] = event
        resolution = "approved" if payload.approved else "denied"
        session.history.append(types.Content(role="user", parts=[types.Part(
            text=(f"Human review {resolution} the pending tool call. Its resolution result is: "
                  + json.dumps(result, default=str)
                  + ". Do not request or retry this tool call.")
        )]))
        if result.get("status") == "executed":
            reply = f"The {pending.tool} action was approved and executed."
        elif result.get("status") == "denied":
            reply = f"The {pending.tool} action was denied and was not executed."
        else:
            reply = f"The {pending.tool} action was approved but could not be completed."
        session.history.append(types.Content(role="model", parts=[types.Part(text=reply)]))
        return {"reply": reply, "tool_events": [event]}


__all__ = ["router", "ChatRequest", "ChatApproveRequest"]
