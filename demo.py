"""Run the fixed-asset ledger against a fresh, deterministic sample database."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from ledger import bootstrap_database, connect_database, run_query


TABLES = (
    "departments",
    "employees",
    "vendors",
    "supplier_invoices",
    "asset_categories",
    "fixed_assets",
    "asset_assignments",
    "asset_disposals",
)

REPORTS = (
    ("INVOICE RECONCILIATION", "invoice_reconciliation"),
    ("ASSIGNMENT HISTORY", "assignment_history"),
    ("AS-OF ASSET REGISTER", "as_of_asset_register"),
    ("DISPOSAL GAIN OR LOSS", "disposal_gain_loss"),
)


def _display_value(column: str, value: Any) -> str:
    if value is None:
        return "-"
    if column.endswith("_cents") and isinstance(value, int):
        sign = "-" if value < 0 else ""
        absolute = abs(value)
        return f"CNY {sign}{absolute // 100:,}.{absolute % 100:02d}"
    return str(value)


def _render_table(rows: Sequence[Any]) -> str:
    if not rows:
        return "(no rows)"

    columns = tuple(rows[0].keys())
    values = [
        tuple(_display_value(column, row[column]) for column in columns)
        for row in rows
    ]
    widths = [
        max(len(column), *(len(row[index]) for row in values))
        for index, column in enumerate(columns)
    ]

    def line(items: Sequence[str]) -> str:
        return " | ".join(
            item.ljust(widths[index]) for index, item in enumerate(items)
        ).rstrip()

    separator = "-+-".join("-" * width for width in widths)
    return "\n".join((line(columns), separator, *(line(row) for row in values)))


def main() -> None:
    connection = connect_database()
    try:
        bootstrap_database(connection)

        print("FIXED-ASSET LEDGER DEMO")
        print("Synthetic data | Currency: CNY | Monthly straight-line depreciation")
        print("\nSCHEMA AND SEED SUMMARY")
        summary = connection.execute(
            " UNION ALL ".join(
                f"SELECT '{table}' AS table_name, COUNT(*) AS row_count FROM {table}"
                for table in TABLES
            )
        ).fetchall()
        print(_render_table(summary))

        for title, query_name in REPORTS:
            print(f"\n{title}")
            print(_render_table(run_query(connection, query_name)))

        print("\nDEMO OK")
    finally:
        connection.close()


if __name__ == "__main__":
    main()
