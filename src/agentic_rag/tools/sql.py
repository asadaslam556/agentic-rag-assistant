"""Text-to-SQL: the planner writes one read-only query against a SQLite database.

The schema and a few worked examples go into the tool description, so the
planning model sees them next to the question and writes the SQL itself. A
query that fails comes back as an observation carrying SQLite's error, which
is what lets the model fix its own query on the next step.

Read-only is enforced by SQLite rather than by inspecting the SQL text,
because text filters are easy to talk around:

- an authorizer allows reads and nothing else, so INSERT, UPDATE, DELETE,
  CREATE, DROP, ATTACH, and PRAGMA are refused before they run
- the same authorizer only allows functions on an explicit list, because
  one call such as randomblob(900000000) allocates in a single step that
  the time limit below cannot interrupt
- on Python 3.11 and later, SQLite's own length limit caps any one string
  or blob at MAX_VALUE_BYTES, which also bounds group_concat
- the connection is set to query_only, a second lock on the same door
- execute() runs exactly one statement, so "SELECT 1; DROP TABLE x" fails
- a progress handler stops any query that runs past the time limit
- at most MAX_ROWS rows come back

A `.sql` script is loaded into an in-memory database, so the sample data is
plain text in git and nothing is ever written to disk. A `.db`, `.sqlite`,
or `.sqlite3` file is opened read-only in place.
"""

from __future__ import annotations

import re
import sqlite3
import threading
import time
from pathlib import Path

from agentic_rag.core.types import Evidence, ToolResult
from agentic_rag.tools.base import Tool, ToolSpec
from agentic_rag.tools.structured import format_number

MAX_ROWS = 50
TIME_LIMIT_SECONDS = 2.0
MAX_VALUE_BYTES = 1_000_000
_MAX_SQL_CHARS = 2000
# "-- Q: question" followed by "-- SQL: query" on the next line
_EXAMPLE = re.compile(r"^--\s*Q:\s*(.+?)\s*\n--\s*SQL:\s*(.+?)\s*$", re.MULTILINE)
_READ_ACTIONS = {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ}
# Aggregates, arithmetic, text, dates, and the functions LIKE and GLOB call
# under the hood. Everything that manufactures large values on request
# (randomblob, zeroblob, printf, format) or reaches outside the database
# (load_extension) is left off.
ALLOWED_FUNCTIONS = frozenset(
    """count sum total avg min max group_concat string_agg
    abs round ceil ceiling floor sign
    length lower upper substr substring trim ltrim rtrim replace instr
    coalesce ifnull nullif iif typeof
    date time datetime julianday strftime unixepoch
    like glob""".split()
)


def _authorize(action: int, _table: str | None, name: str | None, *_: object) -> int:
    # for SQLITE_FUNCTION, SQLite passes the function name as the second argument
    if action == sqlite3.SQLITE_FUNCTION:
        allowed = (name or "").lower() in ALLOWED_FUNCTIONS
    else:
        allowed = action in _READ_ACTIONS
    return sqlite3.SQLITE_OK if allowed else sqlite3.SQLITE_DENY


def _open(path: Path) -> tuple[sqlite3.Connection, list[tuple[str, str]]]:
    """A connection to the database plus the worked examples found in it."""
    if path.suffix.lower() == ".sql":
        script = path.read_text(encoding="utf-8")
        connection = sqlite3.connect(":memory:", check_same_thread=False)
        connection.executescript(script)
        examples = _EXAMPLE.findall(script)
    else:
        uri = f"{path.resolve().as_uri()}?mode=ro"
        connection = sqlite3.connect(uri, uri=True, check_same_thread=False)
        examples = []
    return connection, examples


def _schema(connection: sqlite3.Connection) -> list[str]:
    lines = []
    tables = connection.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    ).fetchall()
    for (table,) in tables:
        columns = connection.execute(f'PRAGMA table_info("{table}")').fetchall()
        lines.append(f"{table}({', '.join(f'{c[1]} {c[2]}'.strip() for c in columns)})")
    return lines


def _render(value: object) -> str:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return "none" if value is None else str(value)
    return format_number(value)


class SQLTool(Tool):
    """Exact answers from tabular records: counts, sums, rankings, filters."""

    def __init__(self, database_path: str | Path):
        self.path = Path(database_path)
        self._connection, self.examples = _open(self.path)
        self.tables = _schema(self._connection)
        # schema first, locks after: reading sqlite_master needs PRAGMA
        self._connection.execute("PRAGMA query_only = ON")
        self._connection.set_authorizer(_authorize)
        # ponytail: Connection.setlimit is Python 3.11+. On 3.10 the function
        # allowlist still blocks the one-call allocators; only group_concat
        # over a huge join is left bounded by the time limit alone
        if hasattr(self._connection, "setlimit"):
            self._connection.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, MAX_VALUE_BYTES)
        # parallel branches share one connection, and SQLite connections are
        # not safe to use from two threads at once
        self._lock = threading.Lock()

        description = [
            "Run one read-only SQLite SELECT against the structured database and get exact rows back. "
            "Use it for counts, totals, averages, rankings, and filters over records. "
            "Only common aggregate, math, text, and date functions are available.",
            "    Schema:",
            *(f"      {line}" for line in self.tables),
        ]
        if self.examples:
            description.append("    Examples:")
            for question, sql in self.examples:
                description += [f"      Q: {question}", f"      SQL: {sql}"]
        self.spec = ToolSpec(
            name="sql_query",
            description="\n".join(description),
            parameters={"sql": "One SQLite SELECT statement that uses only the tables and columns above."},
            required=["sql"],
        )

    def close(self) -> None:
        self._connection.close()

    def run(self, sql: str) -> ToolResult:
        sql = str(sql).strip().rstrip(";").strip()
        if not sql or len(sql) > _MAX_SQL_CHARS:
            return ToolResult(evidence=[], observation=f"Error: the query must be 1-{_MAX_SQL_CHARS} characters.")

        deadline = time.monotonic() + TIME_LIMIT_SECONDS
        with self._lock:
            # a non-zero return from the handler interrupts the running query
            self._connection.set_progress_handler(lambda: time.monotonic() > deadline, 1000)
            try:
                cursor = self._connection.execute(sql)
                columns = [column[0] for column in cursor.description or []]
                rows = cursor.fetchmany(MAX_ROWS + 1)
            except sqlite3.Error as exc:
                return ToolResult(
                    evidence=[],
                    observation=(
                        f"The query failed: {str(exc).rstrip('.')}. Only one SELECT is allowed, using the tables "
                        "and columns in the schema and common aggregate, math, text, and date functions. "
                        "Fix the query and try again."
                    ),
                )
            finally:
                self._connection.set_progress_handler(None, 0)

        truncated = len(rows) > MAX_ROWS
        rows = rows[:MAX_ROWS]
        labels = [column.replace("_", " ") for column in columns]
        rendered = [
            ", ".join(f"{label} {_render(value)}" for label, value in zip(labels, row, strict=True))
            for row in rows
        ]
        if not rows:
            text = "The database query returned no rows."
        elif len(rows) == 1:
            text = f"Database query result: {rendered[0]}."
        else:
            listed = "; ".join(f"({number}) {row}" for number, row in enumerate(rendered, 1))
            text = f"The database query returned {len(rows)} rows: {listed}."
        if truncated:
            text += f" Only the first {MAX_ROWS} rows are shown."

        evidence = Evidence(
            id="",
            text=text,
            source_type="sql",
            # the query itself is the reference, so a reader can rerun it
            source_ref=f"{self.path.name}: {sql}",
            title="Database query",
            tool_name=self.spec.name,
            rank=0,
            score=1.0,
        )
        return ToolResult(evidence=[evidence], observation=f"SQL: {sql}\n{text}")
