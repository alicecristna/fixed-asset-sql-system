"""Small, deterministic runner for the SQLite fixed-asset ledger.

Accounting rules live in SQL.  This module only owns connection setup,
transaction boundaries, loading SQL files, and returning query results.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Final


PROJECT_ROOT: Final = Path(__file__).resolve().parent
SQL_ROOT: Final = (PROJECT_ROOT / "sql").resolve()
MINIMUM_SQLITE_VERSION: Final = (3, 37, 0)

QUERY_FILES: Final = {
    "invoice_reconciliation": "queries/invoice_reconciliation.sql",
    "assignment_history": "queries/assignment_history.sql",
    "as_of_asset_register": "queries/as_of_asset_register.sql",
    "disposal_gain_loss": "queries/disposal_gain_loss.sql",
}

TRANSACTION_CONTROL_KEYWORDS: Final = frozenset(
    {"BEGIN", "COMMIT", "END", "ROLLBACK", "SAVEPOINT", "RELEASE"}
)


def _parse_sqlite_version(version: str) -> tuple[int, int, int]:
    """Return a comparable three-part SQLite version tuple."""

    try:
        parts = tuple(int(part) for part in version.split(".")[:3])
    except ValueError as exc:  # pragma: no cover - defensive runtime guard
        raise RuntimeError(f"Unrecognised SQLite version: {version!r}") from exc
    if len(parts) != 3:  # pragma: no cover - SQLite normally uses x.y.z
        raise RuntimeError(f"Unrecognised SQLite version: {version!r}")
    return parts


def _enable_foreign_keys(connection: sqlite3.Connection) -> None:
    """Enable and verify foreign-key enforcement on an idle connection."""

    if connection.in_transaction:
        raise RuntimeError("foreign keys must be enabled on an idle connection")
    connection.execute("PRAGMA foreign_keys = ON")
    enabled = connection.execute("PRAGMA foreign_keys").fetchone()[0]
    if enabled != 1:
        raise RuntimeError("Could not enable SQLite foreign-key enforcement")


def _split_sql_statements(script: str) -> list[str]:
    """Split a trusted SQL script without breaking trigger bodies or literals."""

    statements: list[str] = []
    buffer: list[str] = []
    for character in script:
        buffer.append(character)
        if character == ";" and sqlite3.complete_statement("".join(buffer)):
            statement = "".join(buffer).strip()
            if statement:
                statements.append(statement)
            buffer.clear()

    remainder = "".join(buffer).strip()
    if remainder:
        statements.append(remainder)
    return statements


def _first_sql_keyword(statement: str) -> str:
    """Return the first keyword after whitespace and SQL comments."""

    index = 0
    length = len(statement)
    while index < length:
        while index < length and (
            statement[index].isspace() or statement[index] == "\ufeff"
        ):
            index += 1
        if statement.startswith("--", index):
            newline = statement.find("\n", index + 2)
            if newline == -1:
                return ""
            index = newline + 1
            continue
        if statement.startswith("/*", index):
            comment_end = statement.find("*/", index + 2)
            if comment_end == -1:
                return ""
            index = comment_end + 2
            continue
        break

    keyword_start = index
    while index < length and (
        statement[index].isalpha() or statement[index] == "_"
    ):
        index += 1
    return statement[keyword_start:index].upper()


def connect_database(path: str | Path = ":memory:") -> sqlite3.Connection:
    """Open a ledger connection with required safety settings enabled.

    Autocommit mode is intentional: multi-statement writes go through
    :func:`execute_atomic_script`, which supplies an explicit transaction.
    """

    connection = sqlite3.connect(path, isolation_level=None)
    try:
        connection.row_factory = sqlite3.Row
        version = connection.execute("SELECT sqlite_version()").fetchone()[0]
        if _parse_sqlite_version(version) < MINIMUM_SQLITE_VERSION:
            required = ".".join(map(str, MINIMUM_SQLITE_VERSION))
            raise RuntimeError(
                f"SQLite {required} or newer is required; found {version}"
            )

        _enable_foreign_keys(connection)
        return connection
    except Exception:
        connection.close()
        raise


def read_sql(relative_path: str | Path) -> str:
    """Read one ``.sql`` file, confined to this repository's SQL directory."""

    requested = Path(relative_path)
    if requested.is_absolute():
        raise ValueError("SQL paths must be relative to the sql directory")

    resolved = (SQL_ROOT / requested).resolve()
    try:
        resolved.relative_to(SQL_ROOT)
    except ValueError as exc:
        raise ValueError("SQL path escapes the sql directory") from exc

    if resolved.suffix.lower() != ".sql":
        raise ValueError("Only .sql files may be loaded")
    if not resolved.is_file():
        raise FileNotFoundError(f"SQL file not found: {relative_path}")
    return resolved.read_text(encoding="utf-8")


def execute_atomic_script(connection: sqlite3.Connection, script: str) -> None:
    """Execute repository DDL/DML as one all-or-nothing transaction.

    Transaction-control statements belong to this runner and are rejected
    inside ``script``.  Statements are split with SQLite's own completeness
    parser, so semicolons in strings and trigger bodies stay intact.
    """

    if connection.in_transaction:
        raise RuntimeError("execute_atomic_script requires an idle connection")

    statements = _split_sql_statements(script)
    for statement in statements:
        if _first_sql_keyword(statement) in TRANSACTION_CONTROL_KEYWORDS:
            raise ValueError(
                "transaction-control statements are not allowed inside "
                "an atomic script"
            )

    try:
        connection.execute("BEGIN IMMEDIATE")
        for statement in statements:
            connection.execute(statement)
        connection.commit()
    except Exception:
        connection.rollback()
        raise


def bootstrap_database(connection: sqlite3.Connection) -> None:
    """Install schema, reporting views, and synthetic fixtures atomically."""

    _enable_foreign_keys(connection)

    existing_objects = connection.execute(
        """
        SELECT name
        FROM sqlite_schema
        WHERE name NOT LIKE 'sqlite_%'
          AND type IN ('table', 'view', 'trigger', 'index')
        LIMIT 1
        """
    ).fetchone()
    if existing_objects is not None:
        raise ValueError("bootstrap_database requires a fresh database")

    script = "\n\n".join(
        (
            read_sql("schema.sql"),
            read_sql("views.sql"),
            read_sql("seed.sql"),
        )
    )
    execute_atomic_script(connection, script)


def run_query(connection: sqlite3.Connection, query_name: str) -> list[sqlite3.Row]:
    """Run one of the four public, read-only reporting queries."""

    try:
        relative_path = QUERY_FILES[query_name]
    except KeyError as exc:
        allowed = ", ".join(QUERY_FILES)
        raise ValueError(
            f"Unknown query {query_name!r}; choose one of: {allowed}"
        ) from exc

    return connection.execute(read_sql(relative_path)).fetchall()
