from typing import Any, Dict, Optional


class ReversibilityEstimator:
    """
    Estimates the reversibility score of a tool call on a normalized scale [0.0, 1.0].
    
    Taxonomy:
      - 0.0: Read-only (e.g., fetch, read, list, view)
      - 0.3: Reversible write (e.g., create temp file, update cache)
      - 0.7: Hard-to-reverse write (e.g., delete, purge, drop table)
      - 1.0: Irreversible / External effect (e.g., payment, email send, deploy)
    """

    DEFAULT_KEYWORD_RULES: Dict[str, float] = {
        # Irreversible / External effect (1.0)
        "payment": 1.0,
        "pay": 1.0,
        "charge": 1.0,
        "transfer": 1.0,
        "refund": 1.0,
        "send_email": 1.0,
        "publish": 1.0,
        "deploy": 1.0,
        # Hard-to-reverse write (0.7)
        "delete": 0.7,
        "remove": 0.7,
        "drop": 0.7,
        "truncate": 0.7,
        "purge": 0.7,
        "destroy": 0.7,
        # Reversible write (0.3)
        "write": 0.3,
        "create": 0.3,
        "update": 0.3,
        "modify": 0.3,
        "temp": 0.3,
        "cache": 0.3,
        # Read-only (0.0)
        "read": 0.0,
        "get": 0.0,
        "fetch": 0.0,
        "list": 0.0,
        "view": 0.0,
        "select": 0.0,
        "find": 0.0,
        "search": 0.0,
    }

    def __init__(
        self,
        keyword_rules: Optional[Dict[str, float]] = None,
        default_score: float = 0.5,
    ):
        """
        Initialize with custom keyword rules or default taxonomy.
        """
        self.keyword_rules = (
            keyword_rules if keyword_rules is not None else dict(self.DEFAULT_KEYWORD_RULES)
        )
        self.default_score = self._clamp(default_score)

    @staticmethod
    def _clamp(val: float) -> float:
        return max(0.0, min(1.0, float(val)))

    def estimate(self, tool_name: str, args: Optional[Dict[str, Any]] = None) -> float:
        """
        Estimates the reversibility score for a given tool name and arguments.
        Returns a float in range [0.0, 1.0].
        """
        target_tokens = set()

        # Add tokens from tool name
        clean_tool_name = tool_name.lower().replace("-", "_")
        for token in clean_tool_name.split("_"):
            if token:
                target_tokens.add(token)

        # Add string argument values and key names as tokens
        if args:
            for key, val in args.items():
                for token in key.lower().replace("-", "_").split("_"):
                    if token:
                        target_tokens.add(token)
                if isinstance(val, str):
                    for token in val.lower().replace("-", "_").split("_"):
                        if token:
                            target_tokens.add(token)

        matching_scores = []
        for kw, score in self.keyword_rules.items():
            kw_lower = kw.lower()
            if kw_lower in clean_tool_name or kw_lower in target_tokens:
                matching_scores.append(self._clamp(score))

        if matching_scores:
            # Pick highest risk (most irreversible) match
            return max(matching_scores)

        return self.default_score
