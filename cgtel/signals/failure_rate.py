import sqlite3
from typing import Optional, Union


class HistoricalFailureRateLookup:
    """
    SQLite-backed store for tracking and querying historical tool failure rates.
    Keyed by tool_name. Cold-start default rate is 0.1.
    """

    def __init__(
        self,
        db_path: str = ":memory:",
        default_failure_rate: float = 0.1,
    ):
        """
        Initialize the lookup store.
        :param db_path: Path to SQLite database file or ':memory:' for transient store.
        :param default_failure_rate: Cold-start default failure rate (default: 0.1).
        """
        self.db_path = db_path
        self.default_failure_rate = max(0.0, min(1.0, float(default_failure_rate)))
        self._shared_conn: Optional[sqlite3.Connection] = None
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        if self.db_path == ":memory:":
            if self._shared_conn is None:
                self._shared_conn = sqlite3.connect(":memory:")
            return self._shared_conn
        return sqlite3.connect(self.db_path)

    def _init_db(self) -> None:
        conn = self._get_connection()
        with conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS tool_failure_rates (
                    tool_name TEXT PRIMARY KEY,
                    total_calls INTEGER NOT NULL DEFAULT 0,
                    failure_rate REAL NOT NULL DEFAULT 0.1
                )
                """
            )
        if self.db_path != ":memory:":
            conn.close()

    def get_failure_rate(self, tool_name: str) -> float:
        """
        Returns observed failure rate for `tool_name`, or the cold-start default (0.1).
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT failure_rate FROM tool_failure_rates WHERE tool_name = ?",
            (tool_name,),
        )
        row = cursor.fetchone()
        if self.db_path != ":memory:":
            conn.close()

        if row is not None:
            return float(row[0])
        return self.default_failure_rate

    def update(self, tool_name: str, is_failure: Union[bool, float]) -> float:
        """
        Updates the running average failure rate for a given tool.
        :param tool_name: Name of the tool.
        :param is_failure: True/1.0 if execution failed, False/0.0 if succeeded.
        :return: Updated running average failure rate.
        """
        val = 1.0 if is_failure is True else (0.0 if is_failure is False else float(is_failure))
        val = max(0.0, min(1.0, val))

        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT total_calls, failure_rate FROM tool_failure_rates WHERE tool_name = ?",
            (tool_name,),
        )
        row = cursor.fetchone()

        if row is None:
            new_total = 1
            new_rate = val
        else:
            old_total, old_rate = row
            new_total = old_total + 1
            new_rate = old_rate + (val - old_rate) / new_total

        new_rate = max(0.0, min(1.0, new_rate))

        with conn:
            conn.execute(
                """
                INSERT INTO tool_failure_rates (tool_name, total_calls, failure_rate)
                VALUES (?, ?, ?)
                ON CONFLICT(tool_name) DO UPDATE SET
                    total_calls = excluded.total_calls,
                    failure_rate = excluded.failure_rate
                """,
                (tool_name, new_total, new_rate),
            )

        if self.db_path != ":memory:":
            conn.close()

        return new_rate

    def close(self) -> None:
        """Closes shared database connection if using memory store."""
        if self._shared_conn is not None:
            self._shared_conn.close()
            self._shared_conn = None
