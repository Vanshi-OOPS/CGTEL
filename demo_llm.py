#!/usr/bin/env python3
"""CGTEL Gemini integration demo. Pass --offline for the deterministic fallback."""
import os
import sys

from cgtel.agent.llm_agent import LLMAgent
from cgtel.router.decision_router import DecisionRouter


TASKS = [
    "Read the application configuration file config/app_settings.json.",
    "Delete the temporary session cache file at /tmp/session_cache.tmp.",
    "Process a subscription payment of 149.99 USD for account acc_user_4042.",
    "Reject the proposed subscription payment of 149.99 USD for account acc_user_4042.",
]


def main():
    offline = "--offline" in sys.argv
    key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not offline and not key:
        print("LIVE GEMINI DEMO requires GEMINI_API_KEY or GOOGLE_API_KEY; no run started.", file=sys.stderr)
        return 2
    print("OFFLINE FALLBACK - NOT A LIVE LLM RUN" if offline else
          "LIVE GEMINI RUN | model: {}".format(os.environ.get("CGTEL_GEMINI_MODEL", "gemini-flash-latest")))
    review_answers = iter(["y", "n"])
    def scripted_review(prompt):
        print("SCRIPTED REVIEWER (demo only): ", end="")
        answer = next(review_answers, "n")
        print(answer)
        return answer
    router = DecisionRouter(input_func=scripted_review if offline else input)
    agent = LLMAgent(mode="offline" if offline else "live", router=router)
    counts = {"executed": 0, "denied": 0, "rejected": 0, "errors": 0}
    for task in TASKS:
        print("\nTask: {}".format(task))
        result = agent.run_task(task)
        print("  Status: {} | mode: {}".format(result["status"], result["llm_mode"]))
        if result.get("tool_name"):
            print("  Proposed: {} {}".format(result["tool_name"], result.get("args")))
        if result.get("decision"):
            decision = result["decision"]
            signals = decision.contributing_signals
            if decision.tier is None or decision.score is None:
                print("  Risk assessment: NOT ASSESSED (no tool proposal was routed)")
            else:
                print("  Confidence: {} ({}) | V/C/F: {}/{}/{} | R: {:.4f} | tier: {}".format(
                    signals.get("confidence"), signals.get("confidence_source"),
                    signals.get("reversibility"), signals.get("confidence"), signals.get("failure_rate"),
                    decision.score, decision.tier.value))
        if result["status"] == "EXECUTED":
            counts["executed"] += 1
            print("  Routing outcome: executed | result: {}".format(result.get("result")))
        elif result["status"] == "DENIED_BY_HUMAN_REVIEW":
            counts["denied"] += 1
            print("  Routing outcome: denied; NOT EXECUTED")
        elif result["status"].startswith("REJECTED"):
            counts["rejected"] += 1
            print("  Routing outcome: rejected; NOT EXECUTED")
        else:
            counts["errors"] += 1
            print("  Routing outcome: {} ({})".format(result["status"], result.get("error", "")))
        print("  Outcome log: {}".format(result.get("outcome_log")))
    print("\nRun totals: {}".format(counts))
    return 0


if __name__ == "__main__":
    sys.exit(main())
