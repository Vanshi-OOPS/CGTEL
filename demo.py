#!/usr/bin/env python3
"""
CGTEL End-to-End Demo Script
Demonstrates tool call interception, risk scoring signal extraction, and policy routing across three risk tiers:
1. AUTO_ALLOW
2. LOG_AND_MONITOR
3. HUMAN_REVIEW
"""

from cgtel.interceptor import gated_tool


@gated_tool(task_context="Reading workspace configuration file")
def fake_file_read(filepath: str) -> str:
    """Simulates reading a file from disk (Read-only -> AUTO_ALLOW)."""
    return f"Content of '{filepath}'"


@gated_tool(task_context="Cleaning up temporary cache directory")
def fake_file_delete(filepath: str, recursive: bool = False) -> bool:
    """Simulates deleting a file or directory (Hard-to-reverse write -> LOG_AND_MONITOR)."""
    print(f"  [EXEC] Deleting file '{filepath}' (recursive={recursive})...")
    return True


@gated_tool(task_context="Processing monthly billing subscription renewal")
def fake_payment_call(account_id: str, amount: float, currency: str = "USD") -> dict:
    """Simulates initiating a financial payment transaction (External effect -> HUMAN_REVIEW)."""
    print(f"  [EXEC] Processing payment of {amount} {currency} for account {account_id}...")
    return {"status": "SUCCESS", "transaction_id": "tx_9988776655"}


def run_dummy_agent():
    print("=" * 70)
    print("   CGTEL Demo: Context-Gated Tool Execution Layer Pipeline")
    print("=" * 70 + "\n")

    # 1. Fake File Read (Tier: AUTO_ALLOW)
    print("--> Step 1: Agent calls `fake_file_read`")
    read_res = fake_file_read("config/app_settings.json")
    dec1 = getattr(fake_file_read, "last_decision", None)
    score1_str = f"{dec1.score:.4f}" if dec1 else "N/A"
    tier1_str = dec1.tier.value if dec1 else "N/A"
    print(f"    Assigned Tier : {tier1_str}")
    print(f"    Risk Score    : {score1_str}")
    print(f"    Returned      : {read_res}\n")

    # 2. Fake File Delete (Tier: LOG_AND_MONITOR)
    print("--> Step 2: Agent calls `fake_file_delete`")
    del_res = fake_file_delete("/tmp/session_cache.tmp", recursive=True)
    dec2 = getattr(fake_file_delete, "last_decision", None)
    score2_str = f"{dec2.score:.4f}" if dec2 else "N/A"
    tier2_str = dec2.tier.value if dec2 else "N/A"
    print(f"    Assigned Tier : {tier2_str}")
    print(f"    Risk Score    : {score2_str}")
    print(f"    Returned      : {del_res}\n")

    # 3. Fake Payment Call (Tier: HUMAN_REVIEW) - Auto-approved for non-blocking demo execution
    print("--> Step 3: Agent calls `fake_payment_call` (Passing auto-approval for automated demo)")
    pay_res = fake_payment_call("acc_user_4042", 149.99, currency="USD", _auto_approve=True)
    dec3 = getattr(fake_payment_call, "last_decision", None)
    score3_str = f"{dec3.score:.4f}" if dec3 else "N/A"
    tier3_str = dec3.tier.value if dec3 else "N/A"
    print(f"    Assigned Tier : {tier3_str}")
    print(f"    Risk Score    : {score3_str}")
    print(f"    Returned      : {pay_res}\n")

    print("=" * 70)
    print("Demo execution completed successfully across all 3 risk tiers.")
    print("=" * 70)


if __name__ == "__main__":
    run_dummy_agent()
