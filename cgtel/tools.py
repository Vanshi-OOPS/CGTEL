"""Simulated tools used by the demos and LLM agent."""
from cgtel.interceptor import gated_tool


@gated_tool(task_context="Reading workspace configuration file")
def fake_file_read(filepath: str) -> str:
    """Simulates reading a file from disk."""
    return "Content of '{}'".format(filepath)


@gated_tool(task_context="Cleaning up temporary cache directory")
def fake_file_delete(filepath: str, recursive: bool = False) -> bool:
    """Simulates deleting a file or directory."""
    print("  [EXEC] Deleting file '{}' (recursive={})...".format(filepath, recursive))
    return True


@gated_tool(task_context="Processing monthly billing subscription renewal")
def fake_payment_call(account_id: str, amount: float, currency: str = "USD") -> dict:
    """Simulates initiating a financial payment transaction."""
    print("  [EXEC] Processing payment of {} {} for account {}...".format(amount, currency, account_id))
    return {"status": "SUCCESS", "transaction_id": "tx_9988776655"}
