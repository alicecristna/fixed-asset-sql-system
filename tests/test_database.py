from __future__ import annotations

import sqlite3
import subprocess
import sys
import unittest
from pathlib import Path

from ledger import (
    bootstrap_database,
    connect_database,
    execute_atomic_script,
    read_sql,
    run_query,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class BootstrappedDatabaseTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.connection = connect_database()
        bootstrap_database(self.connection)

    def tearDown(self) -> None:
        self.connection.close()

    def assert_rejected(
        self, statement: str, parameters: tuple[object, ...] = ()
    ) -> None:
        with self.assertRaises(sqlite3.IntegrityError):
            self.connection.execute(statement, parameters)


class RunnerTests(unittest.TestCase):
    def test_fresh_database_bootstraps_all_strict_tables(self) -> None:
        connection = connect_database()
        self.addCleanup(connection.close)

        bootstrap_database(connection)

        expected_counts = {
            "departments": 3,
            "employees": 5,
            "vendors": 3,
            "supplier_invoices": 3,
            "asset_categories": 3,
            "fixed_assets": 4,
            "asset_assignments": 5,
            "asset_disposals": 1,
        }
        actual_counts = {
            table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in expected_counts
        }
        self.assertEqual(actual_counts, expected_counts)

        table_list = connection.execute("PRAGMA table_list").fetchall()
        strict_by_table = {
            row["name"]: row["strict"]
            for row in table_list
            if row["name"] in expected_counts
        }
        self.assertEqual(strict_by_table, dict.fromkeys(expected_counts, 1))

        invoice = connection.execute(
            """
            SELECT gross_amount_cents, capitalizable_amount_cents
            FROM supplier_invoices
            WHERE invoice_id = 1
            """
        ).fetchone()
        self.assertEqual(dict(invoice), {
            "gross_amount_cents": 2_712_000,
            "capitalizable_amount_cents": 2_400_000,
        })

    def test_bootstrap_rejects_non_fresh_database(self) -> None:
        connection = connect_database()
        self.addCleanup(connection.close)
        connection.execute("CREATE TABLE preexisting (id INTEGER PRIMARY KEY) STRICT")

        with self.assertRaisesRegex(ValueError, "fresh database"):
            bootstrap_database(connection)

    def test_atomic_script_rolls_back_earlier_ddl_and_dml_on_failure(self) -> None:
        connection = connect_database()
        self.addCleanup(connection.close)
        broken_script = """
            CREATE TABLE atomic_probe (
                probe_id INTEGER PRIMARY KEY,
                probe_key TEXT NOT NULL UNIQUE
            ) STRICT;
            INSERT INTO atomic_probe VALUES (1, 'same-key');
            INSERT INTO atomic_probe VALUES (2, 'same-key');
        """

        with self.assertRaises(sqlite3.IntegrityError):
            execute_atomic_script(connection, broken_script)

        self.assertFalse(connection.in_transaction)
        object_count = connection.execute(
            "SELECT COUNT(*) FROM sqlite_schema WHERE name = 'atomic_probe'"
        ).fetchone()[0]
        self.assertEqual(object_count, 0)
        self.assertEqual(connection.execute("SELECT 1").fetchone()[0], 1)

    def test_atomic_script_refuses_to_implicitly_commit_caller_transaction(self) -> None:
        connection = connect_database()
        self.addCleanup(connection.close)
        connection.execute("BEGIN")
        self.addCleanup(connection.rollback)

        with self.assertRaisesRegex(RuntimeError, "idle connection"):
            execute_atomic_script(connection, "SELECT 1;")

        self.assertTrue(connection.in_transaction)

    def test_atomic_script_rejects_embedded_commit_without_partial_write(self) -> None:
        connection = connect_database()
        self.addCleanup(connection.close)
        connection.execute(
            "CREATE TABLE atomic_probe (probe_key TEXT NOT NULL UNIQUE) STRICT"
        )

        with self.assertRaisesRegex(ValueError, "transaction-control"):
            execute_atomic_script(
                connection,
                """
                INSERT INTO atomic_probe VALUES ('first');
                /* the caller must not control this transaction */ COMMIT;
                INSERT INTO atomic_probe VALUES ('first');
                """,
            )

        self.assertEqual(
            connection.execute("SELECT COUNT(*) FROM atomic_probe").fetchone()[0],
            0,
        )

    def test_atomic_script_rejects_bom_prefixed_commit(self) -> None:
        connection = connect_database()
        self.addCleanup(connection.close)
        connection.execute(
            "CREATE TABLE atomic_probe (probe_key TEXT NOT NULL UNIQUE) STRICT"
        )

        with self.assertRaisesRegex(ValueError, "transaction-control"):
            execute_atomic_script(
                connection,
                """
                INSERT INTO atomic_probe VALUES ('first');
                \ufeffCOMMIT;
                INSERT INTO atomic_probe VALUES ('first');
                """,
            )

        self.assertEqual(
            connection.execute("SELECT COUNT(*) FROM atomic_probe").fetchone()[0],
            0,
        )

    def test_bootstrap_enables_foreign_keys_on_a_raw_connection(self) -> None:
        connection = sqlite3.connect(":memory:", isolation_level=None)
        self.addCleanup(connection.close)
        self.assertEqual(connection.execute("PRAGMA foreign_keys").fetchone()[0], 0)

        bootstrap_database(connection)

        self.assertEqual(connection.execute("PRAGMA foreign_keys").fetchone()[0], 1)
        with self.assertRaises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO employees (
                    employee_code, employee_name, department_id, employment_status
                ) VALUES ('SYN-RAW-ORPHAN', 'Synthetic Orphan', 999, 'ACTIVE')
                """
            )

    def test_sql_loader_is_confined_and_query_names_are_allowlisted(self) -> None:
        self.assertIn("CREATE TABLE departments", read_sql("schema.sql"))
        with self.assertRaisesRegex(ValueError, "escapes"):
            read_sql("../README.md")
        with self.assertRaisesRegex(ValueError, "relative"):
            read_sql(PROJECT_ROOT / "sql" / "schema.sql")

        connection = connect_database()
        self.addCleanup(connection.close)
        bootstrap_database(connection)
        with self.assertRaisesRegex(ValueError, "Unknown query"):
            run_query(connection, "../../schema")

    def test_demo_output_is_byte_for_byte_repeatable(self) -> None:
        command = [sys.executable, "-B", "demo.py"]
        first = subprocess.check_output(command, cwd=PROJECT_ROOT)
        second = subprocess.check_output(command, cwd=PROJECT_ROOT)

        self.assertEqual(first, second)
        self.assertTrue(first.endswith(b"DEMO OK\n"))
        self.assertNotIn(str(PROJECT_ROOT).encode(), first)
        for heading in (
            b"SCHEMA AND SEED SUMMARY",
            b"INVOICE RECONCILIATION",
            b"ASSIGNMENT HISTORY",
            b"AS-OF ASSET REGISTER",
            b"DISPOSAL GAIN OR LOSS",
        ):
            with self.subTest(heading=heading):
                self.assertIn(heading, first)


class ConstraintTests(BootstrappedDatabaseTestCase):
    def test_every_connection_enables_foreign_keys_and_rejects_orphans(self) -> None:
        other = connect_database()
        self.addCleanup(other.close)
        self.assertEqual(
            self.connection.execute("PRAGMA foreign_keys").fetchone()[0], 1
        )
        self.assertEqual(other.execute("PRAGMA foreign_keys").fetchone()[0], 1)

        self.assert_rejected(
            """
            INSERT INTO employees (
                employee_code, employee_name, department_id, employment_status
            ) VALUES ('SYN-ORPHAN', 'Synthetic Orphan', 999, 'ACTIVE')
            """
        )

    def test_core_foreign_keys_reject_null(self) -> None:
        statements = (
            """
            INSERT INTO employees (
                employee_code, employee_name, department_id, employment_status
            ) VALUES ('SYN-NULL-EMP', 'Synthetic Null', NULL, 'ACTIVE')
            """,
            """
            INSERT INTO supplier_invoices (
                vendor_id, invoice_number, invoice_date, currency,
                net_amount_cents, vat_amount_cents, recoverable_vat_cents
            ) VALUES (NULL, 'SYN-NULL-INV', '2025-01-01', 'CNY', 100, 0, 0)
            """,
            """
            INSERT INTO fixed_assets (
                asset_tag, invoice_id, category_id, asset_name,
                acquisition_cost_cents, residual_value_cents,
                useful_life_months, in_service_date
            ) VALUES (
                'SYN-NULL-ASSET', NULL, 1, 'Synthetic Null',
                100, 0, 1, '2025-01-01'
            )
            """,
            """
            INSERT INTO asset_assignments (
                asset_id, department_id, custodian_employee_id,
                location, effective_from
            ) VALUES (2, NULL, 2, 'Synthetic Null', '2024-01-20')
            """,
            """
            INSERT INTO asset_disposals (
                asset_id, disposal_date, disposal_method,
                proceeds_cents, approved_by_employee_id
            ) VALUES (3, '2026-01-01', 'SCRAP', 0, NULL)
            """,
        )
        for statement in statements:
            with self.subTest(statement=statement.strip().splitlines()[0]):
                self.assert_rejected(statement)

    def test_duplicate_business_keys_are_rejected(self) -> None:
        self.assert_rejected(
            """
            INSERT INTO supplier_invoices (
                vendor_id, invoice_number, invoice_date, currency,
                net_amount_cents, vat_amount_cents, recoverable_vat_cents
            ) VALUES (1, 'SYN-IT-2024-001', '2025-01-01', 'CNY', 100, 0, 0)
            """
        )
        self.assert_rejected(
            """
            INSERT INTO fixed_assets (
                asset_tag, invoice_id, category_id, asset_name,
                acquisition_cost_cents, residual_value_cents,
                useful_life_months, in_service_date
            ) VALUES (
                'SYN-IT-0001', 1, 1, 'Synthetic Duplicate',
                100, 0, 1, '2025-01-01'
            )
            """
        )

    def test_amount_constraints_reject_non_integer_negative_and_invalid_vat(self) -> None:
        invoice_template = """
            INSERT INTO supplier_invoices (
                vendor_id, invoice_number, invoice_date, currency,
                net_amount_cents, vat_amount_cents, recoverable_vat_cents
            ) VALUES (1, ?, '2025-01-01', 'CNY', ?, ?, ?)
        """
        invalid_rows = (
            ("SYN-TEXT-AMOUNT", "not-an-integer", 0, 0),
            ("SYN-NEGATIVE-AMOUNT", -1, 0, 0),
            ("SYN-NEGATIVE-VAT", 100, -1, 0),
            ("SYN-NEGATIVE-RECOVERABLE", 100, 10, -1),
            ("SYN-EXCESS-RECOVERABLE", 100, 10, 11),
        )
        for row in invalid_rows:
            with self.subTest(invoice_number=row[0]):
                self.assert_rejected(invoice_template, row)

        self.assert_rejected(
            """
            INSERT INTO asset_disposals (
                asset_id, disposal_date, disposal_method,
                proceeds_cents, approved_by_employee_id
            ) VALUES (3, '2026-01-01', 'SALE', -1, 5)
            """
        )

    def test_generated_invoice_amounts_reject_integer_overflow(self) -> None:
        self.assert_rejected(
            """
            INSERT INTO supplier_invoices (
                vendor_id, invoice_number, invoice_date, currency,
                net_amount_cents, vat_amount_cents, recoverable_vat_cents
            ) VALUES (
                1, 'SYN-OVERFLOW-INVOICE', '2025-01-01', 'CNY',
                9223372036854775807, 1, 0
            )
            """
        )

    def test_asset_value_and_life_constraints(self) -> None:
        asset_template = """
            INSERT INTO fixed_assets (
                asset_tag, invoice_id, category_id, asset_name,
                acquisition_cost_cents, residual_value_cents,
                useful_life_months, in_service_date
            ) VALUES (?, 1, 1, 'Synthetic Invalid Asset', ?, ?, ?, '2025-01-01')
        """
        invalid_rows = (
            ("SYN-ZERO-COST", 0, 0, 12),
            ("SYN-NEGATIVE-COST", -1, 0, 12),
            ("SYN-NEGATIVE-RESIDUAL", 100, -1, 12),
            ("SYN-EQUAL-RESIDUAL", 100, 100, 12),
            ("SYN-HIGH-RESIDUAL", 100, 101, 12),
            ("SYN-ZERO-LIFE", 100, 0, 0),
            ("SYN-NEGATIVE-LIFE", 100, 0, -1),
        )
        for row in invalid_rows:
            with self.subTest(asset_tag=row[0]):
                self.assert_rejected(asset_template, row)

    def test_in_service_date_cannot_precede_invoice_date(self) -> None:
        self.assert_rejected(
            """
            INSERT INTO fixed_assets (
                asset_tag, invoice_id, category_id, asset_name,
                acquisition_cost_cents, residual_value_cents,
                useful_life_months, in_service_date
            ) VALUES (
                'SYN-EARLY-SERVICE', 1, 1, 'Synthetic Early Asset',
                100, 0, 12, '2024-01-09'
            )
            """
        )
        self.connection.execute(
            """
            INSERT INTO fixed_assets (
                asset_tag, invoice_id, category_id, asset_name,
                acquisition_cost_cents, residual_value_cents,
                useful_life_months, in_service_date
            ) VALUES (
                'SYN-SAME-DAY-SERVICE', 1, 1, 'Synthetic Boundary Asset',
                100, 0, 12, '2024-01-10'
            )
            """
        )

    def test_assignment_lifecycle_boundaries(self) -> None:
        self.assert_rejected(
            """
            INSERT INTO asset_assignments (
                asset_id, department_id, custodian_employee_id,
                location, effective_from
            ) VALUES (2, 2, 2, 'Synthetic Early Location', '2024-01-19')
            """
        )
        self.assert_rejected(
            """
            INSERT INTO asset_assignments (
                asset_id, department_id, custodian_employee_id,
                location, effective_from
            ) VALUES (4, 3, 4, 'Synthetic Late Location', '2026-09-16')
            """
        )
        self.connection.execute(
            """
            INSERT INTO asset_assignments (
                asset_id, department_id, custodian_employee_id,
                location, effective_from
            ) VALUES (4, 3, 4, 'Synthetic Disposal-day Location', '2026-09-15')
            """
        )

    def test_disposal_lifecycle_boundaries(self) -> None:
        self.assert_rejected(
            """
            INSERT INTO asset_disposals (
                asset_id, disposal_date, disposal_method,
                proceeds_cents, approved_by_employee_id
            ) VALUES (3, '2024-06-19', 'SCRAP', 0, 5)
            """
        )
        self.assert_rejected(
            """
            INSERT INTO asset_disposals (
                asset_id, disposal_date, disposal_method,
                proceeds_cents, approved_by_employee_id
            ) VALUES (1, '2025-06-30', 'SALE', 100, 5)
            """
        )
        self.connection.execute(
            """
            INSERT INTO asset_disposals (
                asset_id, disposal_date, disposal_method,
                proceeds_cents, approved_by_employee_id
            ) VALUES (2, '2024-01-20', 'SCRAP', 0, 5)
            """
        )

    def test_update_triggers_preserve_existing_lifecycle(self) -> None:
        invalid_updates = (
            "UPDATE supplier_invoices SET invoice_date = '2024-01-21' WHERE invoice_id = 1",
            "UPDATE fixed_assets SET in_service_date = '2025-07-02' WHERE asset_id = 1",
            "UPDATE asset_assignments SET effective_from = '2024-01-19' WHERE assignment_id = 1",
            "UPDATE asset_disposals SET disposal_date = '2024-07-31' WHERE asset_id = 4",
        )
        for statement in invalid_updates:
            with self.subTest(statement=statement):
                self.assert_rejected(statement)


class ReportingTests(BootstrappedDatabaseTestCase):
    def test_seed_invoices_reconcile_and_an_extra_asset_is_detected(self) -> None:
        reconciliations = run_query(self.connection, "invoice_reconciliation")
        self.assertEqual(len(reconciliations), 3)
        self.assertEqual(
            [row["reconciliation_status"] for row in reconciliations],
            ["MATCH", "MATCH", "MATCH"],
        )
        self.assertEqual(
            [(row["asset_count"], row["difference_cents"]) for row in reconciliations],
            [(2, 0), (1, 0), (1, 0)],
        )

        self.connection.execute(
            """
            INSERT INTO fixed_assets (
                asset_tag, invoice_id, category_id, asset_name,
                acquisition_cost_cents, residual_value_cents,
                useful_life_months, in_service_date
            ) VALUES (
                'SYN-RECON-MISMATCH', 1, 1, 'Synthetic Reconciliation Probe',
                100, 0, 12, '2024-01-20'
            )
            """
        )
        mismatch = self.connection.execute(
            """
            SELECT asset_count, asset_cost_cents, difference_cents,
                   reconciliation_status
            FROM v_invoice_capitalization_reconciliation
            WHERE invoice_id = 1
            """
        ).fetchone()
        self.assertEqual(dict(mismatch), {
            "asset_count": 3,
            "asset_cost_cents": 2_400_100,
            "difference_cents": -100,
            "reconciliation_status": "MISMATCH",
        })

    def test_depreciation_begins_next_month_and_remainder_goes_first(self) -> None:
        first_two = self.connection.execute(
            """
            SELECT depreciation_month, period_number,
                   monthly_depreciation_cents,
                   accumulated_depreciation_cents,
                   net_book_value_cents
            FROM v_depreciation_schedule
            WHERE asset_id = 2
            ORDER BY period_number
            LIMIT 2
            """
        ).fetchall()
        self.assertEqual(
            [tuple(row) for row in first_two],
            [
                ("2024-02-01", 1, 30_001, 30_001, 1_170_000),
                ("2024-03-01", 2, 30_000, 60_001, 1_140_000),
            ],
        )
        january_rows = self.connection.execute(
            """
            SELECT COUNT(*)
            FROM v_depreciation_schedule
            WHERE asset_id = 2 AND depreciation_month = '2024-01-01'
            """
        ).fetchone()[0]
        self.assertEqual(january_rows, 0)

    def test_full_life_schedules_end_exactly_at_residual_value(self) -> None:
        summaries = self.connection.execute(
            """
            SELECT
                asset.asset_id,
                COUNT(schedule.period_number) AS period_count,
                SUM(schedule.monthly_depreciation_cents) AS charge_total,
                MAX(schedule.accumulated_depreciation_cents) AS final_accumulated,
                MIN(schedule.net_book_value_cents) AS minimum_nbv
            FROM fixed_assets AS asset
            JOIN v_depreciation_schedule AS schedule
              ON schedule.asset_id = asset.asset_id
            LEFT JOIN asset_disposals AS disposal
              ON disposal.asset_id = asset.asset_id
            WHERE disposal.asset_id IS NULL
            GROUP BY asset.asset_id
            ORDER BY asset.asset_id
            """
        ).fetchall()
        self.assertEqual(
            [tuple(row) for row in summaries],
            [
                (1, 36, 1_080_000, 1_080_000, 119_999),
                (2, 36, 1_080_001, 1_080_001, 120_000),
                (3, 120, 14_250_000, 14_250_000, 750_000),
            ],
        )

        below_residual = self.connection.execute(
            """
            SELECT COUNT(*)
            FROM v_depreciation_schedule
            WHERE net_book_value_cents < residual_value_cents
            """
        ).fetchone()[0]
        self.assertEqual(below_residual, 0)

    def test_disposal_month_is_charged_and_next_month_is_absent(self) -> None:
        summary = self.connection.execute(
            """
            SELECT
                MIN(depreciation_month) AS first_month,
                MAX(depreciation_month) AS last_month,
                COUNT(*) AS period_count,
                SUM(monthly_depreciation_cents) AS charge_total,
                MAX(accumulated_depreciation_cents) AS final_accumulated,
                MIN(net_book_value_cents) AS final_nbv
            FROM v_depreciation_schedule
            WHERE asset_id = 4
            """
        ).fetchone()
        self.assertEqual(dict(summary), {
            "first_month": "2024-09-01",
            "last_month": "2026-09-01",
            "period_count": 25,
            "charge_total": 8_708_345,
            "final_accumulated": 8_708_345,
            "final_nbv": 13_291_655,
        })
        october_rows = self.connection.execute(
            """
            SELECT COUNT(*)
            FROM v_depreciation_schedule
            WHERE asset_id = 4 AND depreciation_month = '2026-10-01'
            """
        ).fetchone()[0]
        self.assertEqual(october_rows, 0)

    def test_lead_builds_non_overlapping_assignment_intervals(self) -> None:
        rows = run_query(self.connection, "assignment_history")
        asset_one = [row for row in rows if row["asset_id"] == 1]
        self.assertEqual(
            [
                (
                    row["department_code"],
                    row["effective_from"],
                    row["effective_to"],
                )
                for row in asset_one
            ],
            [
                ("IT", "2024-01-20", "2025-06-30"),
                ("FIN", "2025-07-01", None),
            ],
        )
        vehicle = next(row for row in rows if row["asset_id"] == 4)
        self.assertEqual(vehicle["effective_to"], "2026-09-15")

    def test_as_of_register_matches_hand_calculated_balances(self) -> None:
        rows = run_query(self.connection, "as_of_asset_register")
        self.assertEqual(len(rows), 4)
        actual = {
            row["asset_tag"]: (
                row["as_of_date"],
                row["asset_status"],
                row["accumulated_depreciation_cents"],
                row["net_book_value_cents"],
                row["department_code"],
                row["custodian_employee_code"],
                row["location"],
            )
            for row in rows
        }
        self.assertEqual(actual, {
            "SYN-HVAC-0001": (
                "2026-12-31", "ACTIVE", 3_562_500, 11_437_500,
                "OPS", "SYN-OPS-001", "Synthetic HQ - Plant Room",
            ),
            "SYN-IT-0001": (
                "2026-12-31", "ACTIVE", 1_050_000, 149_999,
                "FIN", "SYN-FIN-001", "Synthetic HQ - Finance Analytics",
            ),
            "SYN-IT-0002": (
                "2026-12-31", "ACTIVE", 1_050_001, 150_000,
                "IT", "SYN-IT-002", "Synthetic HQ - IT Lab",
            ),
            "SYN-VEH-0001": (
                "2026-12-31", "DISPOSED", 8_708_345, 13_291_655,
                "OPS", "SYN-OPS-001", "Synthetic HQ - Fleet Bay",
            ),
        })

    def test_as_of_register_excludes_assets_not_yet_in_service(self) -> None:
        self.connection.execute(
            """
            INSERT INTO supplier_invoices (
                invoice_id, vendor_id, invoice_number, invoice_date, currency,
                net_amount_cents, vat_amount_cents, recoverable_vat_cents
            ) VALUES (
                99, 1, 'SYN-FUTURE-INVOICE', '2027-01-01', 'CNY',
                10000, 0, 0
            )
            """
        )
        self.connection.execute(
            """
            INSERT INTO fixed_assets (
                asset_id, asset_tag, invoice_id, category_id, asset_name,
                acquisition_cost_cents, residual_value_cents,
                useful_life_months, in_service_date
            ) VALUES (
                99, 'SYN-FUTURE-ASSET', 99, 1, 'Synthetic Future Asset',
                10000, 0, 12, '2027-01-02'
            )
            """
        )

        asset_tags = {
            row["asset_tag"]
            for row in run_query(self.connection, "as_of_asset_register")
        }
        self.assertNotIn("SYN-FUTURE-ASSET", asset_tags)

    def test_as_of_register_does_not_reveal_a_future_disposal(self) -> None:
        self.connection.execute(
            """
            INSERT INTO asset_disposals (
                asset_id, disposal_date, disposal_method,
                proceeds_cents, approved_by_employee_id, note
            ) VALUES (
                3, '2027-01-15', 'SALE', 1000000, 5,
                'Synthetic future disposal used as an as-of boundary probe'
            )
            """
        )

        row = next(
            row
            for row in run_query(self.connection, "as_of_asset_register")
            if row["asset_id"] == 3
        )
        self.assertEqual(row["asset_status"], "ACTIVE")
        self.assertIsNone(row["disposal_date"])

    def test_disposal_gain_is_hand_calculated(self) -> None:
        rows = run_query(self.connection, "disposal_gain_loss")
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(
            (
                row["asset_tag"],
                row["disposal_date"],
                row["disposal_method"],
                row["acquisition_cost_cents"],
                row["accumulated_depreciation_cents"],
                row["net_book_value_at_disposal_cents"],
                row["proceeds_cents"],
                row["gain_loss_cents"],
                row["approved_by_employee_code"],
            ),
            (
                "SYN-VEH-0001",
                "2026-09-15",
                "SALE",
                22_000_000,
                8_708_345,
                13_291_655,
                15_000_000,
                1_708_345,
                "SYN-FIN-002",
            ),
        )


if __name__ == "__main__":
    unittest.main()
