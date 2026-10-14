#!/usr/bin/env python3
"""
CGTEL Demo Script with Real LLM Reasoning Agent
Demonstrates natural language task instructions processed by LLMAgent using Google's Gemini API tool-calling,
flowing through interception, real confidence extraction (logprobs / self-consistency proxy), risk scoring, and policy routing.
"""

import os
from cgtel.agent.llm_agent import LLMAgent


def run_llm_agent_demo():
    print("=" * 75)
    print("   CGTEL Demo: LLM Agent Reasoning Core + Context-Gated Tool Execution")
    print("=" * 75)

    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    api_key_status = "DETECTED" if api_key else "NOT SET (Using Rule-based Fallback)"
    print(f"  [STATUS] GEMINI_API_KEY: {api_key_status}\n")

    agent = LLMAgent()

    task_instructions = [
        "Read the current application configuration file config/app_settings.json to inspect system parameters.",
        "Clean up and recursively delete the temporary session cache file at /tmp/session_cache.tmp.",
        "Process this month's subscription payment of 149.99 USD for account acc_user_4042.",
    ]

    for i, instruction in enumerate(task_instructions, 1):
        print(f"--> Task {i}: '{instruction}'")
        res = agent.run_task(instruction, auto_approve=True)

        tool_name = res["tool_name"]
        args = res["args"]
        result = res["result"]
        confidence = res["extracted_confidence"]
        dec = res["decision"]

        print(f"    Selected Tool  : {tool_name}")
        print(f"    Tool Arguments : {args}")
        print(f"    LLM Confidence : {confidence:.4f}")
        if dec:
            print(f"    Assigned Tier  : {dec.tier.value}")
            print(f"    Risk Score     : {dec.score:.4f}")
            print(f"    Signals        : {dec.contributing_signals}")
        print(f"    Returned       : {result}\n")

    print("=" * 75)
    print("LLM Agent Demo completed successfully.")
    print("=" * 75)


if __name__ == "__main__":
    run_llm_agent_demo()
