import json
import os
from collections import Counter
from typing import Any, Callable, Dict, Optional, Tuple

from google import genai
from google.genai import types

from cgtel.logger import logger
from cgtel.router.decision_router import DecisionRouter
from cgtel.scoring.engine import RiskScoringEngine
from cgtel.signals.confidence import LLMConfidenceExtractor


# Tool declarations for Gemini Function Calling
def fake_file_read(filepath: str) -> str:
    """Reads the content of a file from disk. Use this for reading configuration files or inspecting documents."""
    pass


def fake_file_delete(filepath: str, recursive: bool = False) -> bool:
    """Deletes a file or directory from disk. Use this for removing temporary files or caches."""
    pass


def fake_payment_call(account_id: str, amount: float, currency: str = "USD") -> dict:
    """Initiates a financial payment transaction for subscription or billing renewal."""
    pass


GEMINI_TOOLS = [fake_file_read, fake_file_delete, fake_payment_call]


class LLMAgent:
    """
    LLM Agent that takes natural language task instructions, calls Google's Gemini API (google-genai SDK)
    using function-calling/tool-calling to select tools and arguments, and routes that
    decision through the existing @gated_tool interceptor pipeline.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: str = "gemini-flash-latest",
        tool_registry: Optional[Dict[str, Callable]] = None,
        scoring_engine: Optional[RiskScoringEngine] = None,
        router: Optional[DecisionRouter] = None,
        num_consistency_samples: int = 3,
    ):
        self.api_key = (
            api_key
            or os.environ.get("GEMINI_API_KEY")
            or os.environ.get("GOOGLE_API_KEY")
        )
        self.model_name = model_name
        self.num_consistency_samples = num_consistency_samples

        # Default registered gated tools (reuse existing gated tools)
        if tool_registry is not None:
            self.tool_registry = tool_registry
        else:
            from demo import fake_file_delete, fake_file_read, fake_payment_call

            self.tool_registry = {
                "fake_file_read": fake_file_read,
                "fake_file_delete": fake_file_delete,
                "fake_payment_call": fake_payment_call,
            }

        self.confidence_extractor = LLMConfidenceExtractor()
        self.scoring_engine = scoring_engine or RiskScoringEngine(
            confidence_extractor=self.confidence_extractor
        )
        self.router = router or DecisionRouter()

        self.client = genai.Client(api_key=self.api_key) if self.api_key else None

    def _query_gemini_once(self, task_instruction: str) -> Tuple[Optional[str], Optional[dict], Any]:
        """Queries Gemini API using google-genai Client."""
        if not self.client:
            return None, None, None

        response = self.client.models.generate_content(
            model=self.model_name,
            contents=task_instruction,
            config=types.GenerateContentConfig(
                tools=GEMINI_TOOLS,
                temperature=0.2,
            ),
        )

        tool_name = None
        tool_args = None

        if getattr(response, "function_calls", None):
            fc = response.function_calls[0]
            tool_name = fc.name
            tool_args = dict(fc.args) if fc.args else {}
        elif getattr(response, "candidates", None) and response.candidates:
            content = getattr(response.candidates[0], "content", None)
            if content and getattr(content, "parts", None):
                for part in content.parts:
                    fc = getattr(part, "function_call", None)
                    if fc and getattr(fc, "name", None):
                        tool_name = fc.name
                        tool_args = dict(fc.args) if getattr(fc, "args", None) else {}
                        break

        return tool_name, tool_args, response

    def _rule_based_fallback(self, task_instruction: str) -> Tuple[str, dict]:
        """Rule-based fallback for selecting tool and arguments when API key is unavailable."""
        task_lower = task_instruction.lower()
        if "delete" in task_lower or "remove" in task_lower or "cache" in task_lower:
            return "fake_file_delete", {
                "filepath": "/tmp/session_cache.tmp",
                "recursive": True,
            }
        elif "payment" in task_lower or "pay" in task_lower or "subscription" in task_lower:
            return "fake_payment_call", {
                "account_id": "acc_user_4042",
                "amount": 149.99,
                "currency": "USD",
            }
        else:
            return "fake_file_read", {"filepath": "config/app_settings.json"}

    def run_task(
        self,
        task_instruction: str,
        auto_approve: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """
        Processes a natural language task instruction.
        Calls Gemini API (google-genai SDK) with function calling and self-consistency agreement calculation
        (or fallback if GEMINI_API_KEY is not set).
        Routes selected tool call through the CGTEL @gated_tool interceptor pipeline.
        """
        tool_name: str
        tool_args: dict
        response_obj = None

        top_count = None
        total_samples = None

        if self.api_key and self.client:
            try:
                samples = []
                last_response = None
                for _ in range(self.num_consistency_samples):
                    t_name, t_args, resp = self._query_gemini_once(task_instruction)
                    last_response = resp
                    if t_name is not None:
                        args_key = json.dumps(t_args, sort_keys=True) if t_args else "{}"
                        samples.append((t_name, args_key, t_args))

                if samples:
                    # Self-consistency agreement across samples
                    counter = Counter((s[0], s[1]) for s in samples)
                    (top_tool, top_args_json), top_count = counter.most_common(1)[0]
                    top_args = next(s[2] for s in samples if s[0] == top_tool and s[1] == top_args_json)

                    tool_name = top_tool
                    tool_args = top_args
                    response_obj = last_response

                    total_samples = len(samples)
                    confidence_val = top_count / float(total_samples)

                    logger.info(
                        f"[LLMAgent] Gemini API (google-genai) call SUCCESS: Selected tool '{tool_name}' via {self.model_name} with {confidence_val:.2f} confidence ({top_count}/{total_samples} agreement)."
                    )
                    print(
                        f"  [GEMINI API SUCCESS] Tool '{tool_name}' selected via {self.model_name} with {confidence_val:.2f} confidence ({top_count}/{total_samples} self-consistency agreement)"
                    )
                else:
                    logger.warning(
                        "[LLMAgent] Gemini returned no function calls. Falling back to rule-based agent."
                    )
                    tool_name, tool_args = self._rule_based_fallback(task_instruction)
            except Exception as e:
                logger.warning(
                    f"[LLMAgent] Gemini API call failed ({e}). Falling back to rule-based agent."
                )
                tool_name, tool_args = self._rule_based_fallback(task_instruction)
        else:
            logger.info(
                "[LLMAgent] GEMINI_API_KEY not found in environment. Using rule-based agent fallback."
            )
            tool_name, tool_args = self._rule_based_fallback(task_instruction)

        if tool_name not in self.tool_registry:
            raise KeyError(f"Tool '{tool_name}' is not registered in LLMAgent tool_registry.")

        target_tool = self.tool_registry[tool_name]

        # Extract confidence score through ConfidenceExtractor (or fallback)
        extracted_confidence = self.confidence_extractor.extract(
            tool_name,
            args=tool_args,
            response=response_obj,
            agreement_count=top_count,
            total_samples=total_samples,
            fallback_confidence=0.9,
        )

        # Execute target gated tool through existing @gated_tool pipeline
        result = target_tool(
            **tool_args,
            _task_context=task_instruction,
            _auto_approve=auto_approve,
        )

        decision = getattr(target_tool, "last_decision", None)
        request = getattr(target_tool, "last_request", None)

        return {
            "task_instruction": task_instruction,
            "tool_name": tool_name,
            "args": tool_args,
            "result": result,
            "extracted_confidence": extracted_confidence,
            "decision": decision,
            "request": request,
        }
