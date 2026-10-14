import math
from typing import Any, Callable, Dict, List, Optional


def default_mock_confidence_provider(
    tool_name: str, args: Optional[Dict[str, Any]] = None, **kwargs
) -> float:
    """Default mock provider returning a fixed confidence score of 0.9."""
    return 0.9


def llm_logprobs_confidence_provider(
    tool_name: str, args: Optional[Dict[str, Any]] = None, **kwargs
) -> float:
    """
    Extracts confidence score in [0.0, 1.0] from LLM completion logprobs or self-consistency agreement.
    Supports Gemini (candidates[0].logprobs_result), OpenAI (choices[0].logprobs), or explicit logprobs list.
    Falls back to self-consistency agreement rate or default mock confidence (0.9).
    """
    logprobs_obj = kwargs.get("logprobs")
    response_obj = kwargs.get("response")
    agreement_count = kwargs.get("agreement_count")
    total_samples = kwargs.get("total_samples")

    logprob_values: List[float] = []

    # 1. Direct logprobs list argument
    if isinstance(logprobs_obj, list):
        for lp in logprobs_obj:
            if isinstance(lp, (int, float)):
                logprob_values.append(float(lp))
            elif hasattr(lp, "logprob") and isinstance(lp.logprob, (int, float)):
                logprob_values.append(float(lp.logprob))

    # 2. Extract from response object (Gemini or OpenAI)
    elif response_obj is not None:
        try:
            # Gemini response logprobs_result
            candidates = getattr(response_obj, "candidates", None)
            if candidates and len(candidates) > 0:
                logprobs_result = getattr(candidates[0], "logprobs_result", None)
                if logprobs_result:
                    chosen = getattr(logprobs_result, "chosen_candidates", None) or getattr(logprobs_result, "top_candidates", None)
                    if chosen:
                        for token_choice in chosen:
                            lp = getattr(token_choice, "log_probability", None) or getattr(token_choice, "logprob", None)
                            if lp is not None and isinstance(lp, (int, float)):
                                logprob_values.append(float(lp))

            # OpenAI choice logprobs
            choices = getattr(response_obj, "choices", None)
            if not logprob_values and choices and len(choices) > 0:
                logprobs_data = getattr(choices[0], "logprobs", None)
                if logprobs_data is not None:
                    content = getattr(logprobs_data, "content", None)
                    if content:
                        for token_info in content:
                            lp = getattr(token_info, "logprob", None)
                            if lp is not None and isinstance(lp, (int, float)):
                                logprob_values.append(float(lp))
        except (AttributeError, IndexError):
            pass

    if logprob_values:
        avg_logprob = sum(logprob_values) / len(logprob_values)
        prob = math.exp(avg_logprob)
        return max(0.0, min(1.0, float(prob)))

    # 3. Self-consistency agreement rate fallback
    if agreement_count is not None and total_samples and total_samples > 0:
        ratio = float(agreement_count) / float(total_samples)
        return max(0.0, min(1.0, ratio))

    # 4. Fallback default
    fallback = kwargs.get("fallback_confidence", 0.9)
    return float(fallback)


class ConfidenceExtractor:
    """
    Extracts and normalizes confidence scores from a pluggable provider callback.
    All outputs are normalized strictly to the [0.0, 1.0] interval.
    """

    def __init__(
        self,
        provider: Optional[Callable[..., float]] = None,
        default_confidence: float = 0.9,
    ):
        """
        Initialize with a custom provider callback or fallback default mock provider.
        """
        if provider is not None:
            self.provider = provider
        else:
            self.provider = lambda tool_name, args=None, **kw: default_confidence

    @staticmethod
    def _normalize(val: float) -> float:
        """Clamps confidence score to strictly lie within [0.0, 1.0]."""
        try:
            f_val = float(val)
        except (ValueError, TypeError):
            return 0.0
        return max(0.0, min(1.0, f_val))

    def extract(self, tool_name: str, args: Optional[Dict[str, Any]] = None, **kwargs) -> float:
        """
        Invokes the confidence provider callback and returns a normalized score in [0.0, 1.0].
        """
        try:
            raw_score = self.provider(tool_name, args=args, **kwargs)
        except Exception:
            raw_score = 0.0

        return self._normalize(raw_score)


class LLMConfidenceExtractor(ConfidenceExtractor):
    """
    Confidence extractor specialized for LLM tool-calling responses (logprobs & self-consistency).
    """

    def __init__(
        self,
        provider: Optional[Callable[..., float]] = None,
        fallback_confidence: float = 0.9,
    ):
        def default_provider(tool_name: str, args=None, **kw):
            kw.setdefault("fallback_confidence", fallback_confidence)
            return llm_logprobs_confidence_provider(tool_name, args=args, **kw)

        provider_fn = provider or default_provider
        super().__init__(provider=provider_fn, default_confidence=fallback_confidence)
