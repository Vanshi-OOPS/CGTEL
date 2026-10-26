#!/usr/bin/env python3
"""Offline CGTEL pipeline demonstration across the three risk tiers."""
from cgtel.router.decision_router import DecisionRouter
from cgtel.scoring.engine import RiskScoringEngine
from cgtel.tools import fake_file_delete, fake_file_read, fake_payment_call


def run_dummy_agent():
    print("=" * 70)
    print("   CGTEL Demo: Confidence-Gated Tool Execution Layer Pipeline")
    print("   SCRIPTED REVIEWER (demo only): approves the payment")
    print("=" * 70)
    router = DecisionRouter(input_func=lambda prompt: (print(prompt, end=""), "y")[1])
    engine = RiskScoringEngine()
    cases = [("fake_file_read", fake_file_read, ("config/app_settings.json",)),
             ("fake_file_delete", fake_file_delete, ("/tmp/session_cache.tmp",)),
             ("fake_payment_call", fake_payment_call, ("acc_user_4042", 149.99))]
    for index, (name, tool, args) in enumerate(cases, 1):
        print("--> Step {}: {}".format(index, name))
        result = tool(*args, _scoring_engine=engine, _router=router)
        print("    Assigned Tier : {}".format(tool.last_decision.tier.value))
        print("    Risk Score    : {:.4f}".format(tool.last_decision.score))
        print("    Returned      : {}".format(result))
    print("Demo run complete.")


if __name__ == "__main__":
    run_dummy_agent()
