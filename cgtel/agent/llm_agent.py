"""Gemini-backed proposal agent; CGTEL remains the sole execution gate."""
import json
import os
from collections import Counter
from typing import Any, Callable, Dict, Optional, Tuple

from google import genai
from google.genai import types

from cgtel.logger import logger
from cgtel.logger.outcome_logger import OutcomeLogger
from cgtel.interceptor import gated_tool
from cgtel.router.decision_router import DecisionRouter
from cgtel.scoring.engine import RiskScoringEngine
from cgtel.signals.confidence import LLMConfidenceExtractor
from cgtel.tools import fake_file_delete, fake_file_read, fake_payment_call
from cgtel.types import RiskDecision, RiskTier, ToolCallRequest


def _declaration(name, description, parameters):
    props = {key: {field: value for field, value in spec.items() if field != "required"}
             for key, spec in parameters.items()}
    return {"name": name, "description": description,
            "parameters": {"type": "OBJECT", "properties": props,
                           "required": [key for key, spec in parameters.items() if spec.get("required")]}}


GEMINI_TOOLS = [fake_file_read, fake_file_delete, fake_payment_call]
_DECLARATIONS = [
    _declaration("fake_file_read", "Read a simulated file", {"filepath": {"type": "STRING", "required": True}}),
    _declaration("fake_file_delete", "Delete a simulated file", {"filepath": {"type": "STRING", "required": True}, "recursive": {"type": "BOOLEAN"}}),
    _declaration("fake_payment_call", "Make a simulated payment", {"account_id": {"type": "STRING", "required": True}, "amount": {"type": "NUMBER", "required": True}, "currency": {"type": "STRING"}}),
]


class LLMAgent:
    def __init__(self, api_key: Optional[str] = None, model_name: Optional[str] = None,
                 tool_registry: Optional[Dict[str, Callable]] = None,
                 scoring_engine: Optional[RiskScoringEngine] = None,
                 router: Optional[DecisionRouter] = None,
                 num_consistency_samples: int = 3, mode: Optional[str] = None,
                 outcome_logger: Optional[OutcomeLogger] = None):
        # Credentials are intentionally read only from environment variables.
        self.api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        self.model_name = model_name or os.environ.get("CGTEL_GEMINI_MODEL", "gemini-flash-latest")
        if mode not in (None, "live", "offline"):
            raise ValueError("mode must be 'live' or 'offline'")
        self.mode = mode or ("live" if self.api_key else "offline")
        self.num_consistency_samples = num_consistency_samples
        registry = tool_registry or {
            "fake_file_read": fake_file_read, "fake_file_delete": fake_file_delete,
            "fake_payment_call": fake_payment_call,
        }
        self.tool_registry = {
            name: tool if getattr(tool, "_cgtel_gated", False) else gated_tool(tool)
            for name, tool in registry.items()
        }
        self.confidence_extractor = LLMConfidenceExtractor(fallback_confidence=0.0)
        self.scoring_engine = scoring_engine or RiskScoringEngine(confidence_extractor=self.confidence_extractor)
        self.router = router or DecisionRouter()
        self.outcome_logger = outcome_logger or OutcomeLogger()
        self.client = genai.Client(api_key=self.api_key) if self.api_key and self.mode == "live" else None

    def _query_gemini_once(self, task_instruction: str) -> Tuple[Optional[str], Optional[dict], Any, list]:
        if not self.client:
            return None, None, None, []
        config = types.GenerateContentConfig(
            tools=[types.Tool(function_declarations=_DECLARATIONS)],
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
            response_logprobs=False, temperature=0.2,
        )
        response = self.client.models.generate_content(model=self.model_name, contents=task_instruction, config=config)
        calls = getattr(response, "function_calls", None) or []
        if not calls:
            candidates = getattr(response, "candidates", None) or []
            if candidates:
                content = getattr(candidates[0], "content", None)
                calls = [getattr(part, "function_call", None) for part in (getattr(content, "parts", None) or [])]
                calls = [call for call in calls if call and getattr(call, "name", None)]
        if not calls:
            return None, None, response, []
        extras = [{"tool_name": call.name, "args": dict(call.args or {})} for call in calls[1:]]
        return calls[0].name, dict(calls[0].args or {}), response, extras

    def _rule_based_fallback(self, task_instruction: str) -> Tuple[str, dict]:
        text = task_instruction.lower()
        if "delete" in text or "remove" in text or "cache" in text:
            return "fake_file_delete", {"filepath": "/tmp/session_cache.tmp", "recursive": True}
        if "payment" in text or "pay" in text or "subscription" in text:
            return "fake_payment_call", {"account_id": "acc_user_4042", "amount": 149.99, "currency": "USD"}
        return "fake_file_read", {"filepath": "config/app_settings.json"}

    def _result(self, task, status, mode, **kwargs):
        result = {"task_instruction": task, "status": status, "llm_mode": mode,
                  "outcome_log": self.outcome_logger.entries[-1] if self.outcome_logger.entries else None}
        result.update(kwargs)
        return result

    def run_task(self, task_instruction: str, auto_approve: Optional[bool] = None) -> Dict[str, Any]:
        live = self.mode == "live"
        mode_label = "live" if live else "offline_fallback"
        print("[LIVE GEMINI RUN] {}".format(self.model_name) if live else "[OFFLINE FALLBACK - NOT A LIVE LLM RUN]")
        if live and not self.client:
            return self._llm_failure(task_instruction, mode_label, "Live mode requires a Gemini API key")
        confidence = 0.0
        confidence_source = "offline_fallback" if not live else "llm_self_consistency"
        response = None
        ignored_calls = []
        if live:
            try:
                votes = []
                for _ in range(self.num_consistency_samples):
                    item = self._query_gemini_once(task_instruction)
                    if item[0] is None:
                        return self._llm_failure(task_instruction, mode_label,
                                                 "Gemini returned no function call", "NO_TOOL_CALL")
                    votes.append(item)
                if not votes:
                    return self._llm_failure(task_instruction, mode_label, "Gemini returned no function call", "NO_TOOL_CALL")
                counts = Counter((v[0], json.dumps(v[1], sort_keys=True)) for v in votes)
                (tool_name, _), count = counts.most_common(1)[0]
                chosen = next(v for v in votes if v[0] == tool_name and json.dumps(v[1], sort_keys=True) == _)
                tool_args, response = chosen[1], chosen[2]
                confidence = count / float(len(votes))
                confidence_source = "llm_self_consistency"
                ignored_calls = chosen[3]
            except Exception as exc:
                logger.warning("Gemini call failed: %s", exc)
                return self._llm_failure(task_instruction, mode_label, str(exc))
        else:
            tool_name, tool_args = self._rule_based_fallback(task_instruction)
            confidence = 0.9

        if tool_name not in self.tool_registry:
            return self._rejected(task_instruction, mode_label, tool_name, tool_args, "REJECTED_UNSUPPORTED_TOOL", ignored_calls)
        target = self.tool_registry[tool_name]
        try:
            sig = __import__("inspect").signature(target)
            params = sig.parameters
            if any(k.startswith("_") or k not in params for k in tool_args):
                raise ValueError("unsupported or reserved argument")
            sig.bind(**tool_args)
            for key, value in tool_args.items():
                annotation = params[key].annotation
                if annotation is float and (not isinstance(value, (int, float)) or isinstance(value, bool)):
                    raise ValueError("{} must be numeric".format(key))
                if annotation is str and not isinstance(value, str):
                    raise ValueError("{} must be a string".format(key))
                if annotation is bool and not isinstance(value, bool):
                    raise ValueError("{} must be boolean".format(key))
        except (TypeError, ValueError) as exc:
            return self._rejected(task_instruction, mode_label, tool_name, tool_args, "REJECTED_INVALID_ARGS", ignored_calls, str(exc))

        try:
            result = target(**tool_args, _task_context=task_instruction,
                            _confidence=confidence, _confidence_source=confidence_source,
                            _scoring_engine=self.scoring_engine, _router=self.router,
                            _auto_approve=auto_approve, _outcome_logger=self.outcome_logger,
                            _llm_mode=mode_label)
        except PermissionError:
            decision = getattr(target, "last_decision", None)
            return self._result(task_instruction, "DENIED_BY_HUMAN_REVIEW", mode_label,
                                tool_name=tool_name, args=tool_args, decision=decision,
                                extracted_confidence=confidence, ignored_calls=ignored_calls)
        except Exception as exc:
            return self._result(task_instruction, "EXECUTION_ERROR", mode_label,
                                tool_name=tool_name, args=tool_args, error=str(exc),
                                decision=getattr(target, "last_decision", None))
        decision = getattr(target, "last_decision", None)
        return self._result(task_instruction, "EXECUTED", mode_label, tool_name=tool_name,
                            args=tool_args, result=result, extracted_confidence=confidence,
                            decision=decision, ignored_calls=ignored_calls)

    def _rejected(self, task, mode, tool, args, status, ignored, error=None):
        decision = RiskDecision(0.0, RiskTier.HUMAN_REVIEW, {"confidence_source": mode})
        request = ToolCallRequest(tool, args, task)
        entry = self.outcome_logger.log_outcome(request, decision, False,
            metadata={"rejected_invalid": True, "llm_mode": mode})
        return self._result(task, status, mode, tool_name=tool, args=args, error=error,
                            decision=decision, outcome_log=entry, ignored_calls=ignored)

    def _llm_failure(self, task, mode, error, status="LLM_ERROR"):
        decision = RiskDecision(None, None, {"assessment_status": "NOT_ASSESSED",
                                             "confidence_source": "llm_error"})
        request = ToolCallRequest("llm_proposal", {}, task)
        entry = self.outcome_logger.log_outcome(request, decision, False, error=RuntimeError(error),
                 metadata={"llm_error": True, "llm_mode": mode})
        return self._result(task, status, mode, error=error, decision=decision,
                            assessment_status="NOT_ASSESSED", outcome_log=entry)
