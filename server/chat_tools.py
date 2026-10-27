"""Mock tools for chat workflows, with all filesystem access contained in sandbox/."""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any, Callable


SANDBOX_DIR = Path(__file__).resolve().parent.parent / "sandbox"
_APPEND_LOCK = threading.Lock()


def _sandbox_path(filepath: str) -> Path:
    """Resolve a caller path and reject traversal, symlinks, and sandbox escapes."""
    if not isinstance(filepath, str) or not filepath.strip():
        raise ValueError("filepath must be a non-empty string")
    if "\x00" in filepath:
        raise ValueError("filepath contains a null byte")

    requested = Path(filepath)
    if ".." in requested.parts:
        raise ValueError("parent-directory traversal is not allowed")

    root = SANDBOX_DIR.resolve()
    candidate = (requested if requested.is_absolute() else root / requested).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ValueError("path must resolve inside the sandbox directory") from exc
    if candidate == root:
        raise ValueError("a file path is required; the sandbox root is not a file")
    return candidate


def read_file(filepath: str) -> dict[str, Any]:
    """Read UTF-8 text from a file inside sandbox/."""
    path = _sandbox_path(filepath)
    if not path.is_file():
        # A well-formed path to a missing file is a valid read request. Report
        # the operational result without turning it into a scoring failure.
        return {"filepath": str(path.relative_to(SANDBOX_DIR.resolve())), "error": "file not found"}
    return {"filepath": str(path.relative_to(SANDBOX_DIR.resolve())), "content": path.read_text(encoding="utf-8")}


def write_file(filepath: str, content: str) -> dict[str, Any]:
    """Write UTF-8 text to a file inside sandbox/, creating parent directories."""
    if not isinstance(content, str):
        raise ValueError("content must be a string")
    path = _sandbox_path(filepath)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Re-resolve after directory creation to ensure existing symlinks remain contained.
    path = _sandbox_path(str(path))
    path.write_text(content, encoding="utf-8")
    return {"filepath": str(path.relative_to(SANDBOX_DIR.resolve())), "bytes_written": len(content.encode("utf-8"))}


def delete_file(filepath: str) -> dict[str, Any]:
    """Delete one file inside sandbox/; directories are not recursively removed."""
    path = _sandbox_path(filepath)
    if not path.is_file():
        raise FileNotFoundError(f"sandbox file not found: {filepath}")
    path.unlink()
    return {"filepath": str(path.relative_to(SANDBOX_DIR.resolve())), "deleted": True}


def send_email(to: str, subject: str, body: str) -> dict[str, Any]:
    """Mock an email by recording it in sandbox/outbox.json; no network is used."""
    if not all(isinstance(value, str) and value.strip() for value in (to, subject, body)):
        raise ValueError("to, subject, and body must be non-empty strings")
    message = {"to": to, "subject": subject, "body": body}
    return _append_record("outbox.json", message, "email")


def make_payment(recipient: str, amount: float, currency: str, memo: str = "") -> dict[str, Any]:
    """Mock a payment by recording it in sandbox/payments.json; no payment is sent."""
    if not isinstance(recipient, str) or not recipient.strip():
        raise ValueError("recipient must be a non-empty string")
    if isinstance(amount, bool) or not isinstance(amount, (int, float)) or amount <= 0:
        raise ValueError("amount must be a positive number")
    if not isinstance(currency, str) or len(currency) != 3 or not currency.isalpha():
        raise ValueError("currency must be a three-letter code")
    if not isinstance(memo, str):
        raise ValueError("memo must be a string")
    record = {"recipient": recipient, "amount": amount, "currency": currency.upper(), "memo": memo}
    return _append_record("payments.json", record, "payment")


def _append_record(filename: str, record: dict[str, Any], kind: str) -> dict[str, Any]:
    path = _sandbox_path(filename)
    path.parent.mkdir(parents=True, exist_ok=True)
    path = _sandbox_path(str(path))
    with _APPEND_LOCK:
        if path.exists():
            try:
                entries = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise ValueError(f"sandbox/{filename} must contain a JSON array") from exc
            if not isinstance(entries, list):
                raise ValueError(f"sandbox/{filename} must contain a JSON array")
        else:
            entries = []
        entries.append(record)
        path.write_text(json.dumps(entries, indent=2) + "\n", encoding="utf-8")
    return {"mock": True, "kind": kind, "record": record, "records": len(entries)}


ToolExecute = Callable[..., dict[str, Any]]


def _schema(properties: dict[str, dict[str, str]], required: list[str]) -> dict[str, Any]:
    return {"type": "object", "properties": properties, "required": required, "additionalProperties": False}


CHAT_TOOLS: list[dict[str, Any]] = [
    {"name": "read_file", "description": "Read a UTF-8 text file inside the sandbox directory.",
     "parameters": _schema({"filepath": {"type": "string", "description": "Path relative to sandbox/."}}, ["filepath"]), "execute": read_file},
    {"name": "write_file", "description": "Write UTF-8 text to a file inside the sandbox directory.",
     "parameters": _schema({"filepath": {"type": "string", "description": "Path relative to sandbox/."}, "content": {"type": "string", "description": "Text to write."}}, ["filepath", "content"]), "execute": write_file},
    {"name": "delete_file", "description": "Delete one file inside the sandbox directory.",
     "parameters": _schema({"filepath": {"type": "string", "description": "Path relative to sandbox/."}}, ["filepath"]), "execute": delete_file},
    {"name": "send_email", "description": "Mock an email and append it to sandbox/outbox.json; does not send email.",
     "parameters": _schema({"to": {"type": "string", "description": "Mock recipient address."}, "subject": {"type": "string", "description": "Email subject."}, "body": {"type": "string", "description": "Email body."}}, ["to", "subject", "body"]), "execute": send_email},
    {"name": "make_payment", "description": "Mock a payment and append it to sandbox/payments.json; does not transfer funds.",
     "parameters": _schema({"recipient": {"type": "string", "description": "Mock payment recipient."}, "amount": {"type": "number", "description": "Positive mock amount."}, "currency": {"type": "string", "description": "Three-letter currency code."}, "memo": {"type": "string", "description": "Optional payment memo."}}, ["recipient", "amount", "currency"]), "execute": make_payment},
]


TOOLS = CHAT_TOOLS

__all__ = ["SANDBOX_DIR", "CHAT_TOOLS", "TOOLS", "read_file", "write_file", "delete_file", "send_email", "make_payment"]
