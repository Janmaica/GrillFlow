import sqlite3
import unittest
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from expense_store import ExpenseStore
from order_draft import OrderDraft
from order_store import PAID, OrderStore, report_bounds
from product_store import ProductFields, ProductStore


class ExpenseTests(unittest.TestCase):
    def setUp(self):
        self.path = self.enterContext(TemporaryDirectory())
        self.products = ProductStore(self.path)
        self.orders = OrderStore(self.products)
        self.orders.initialize()
        self.expenses = ExpenseStore(self.products)
        self.now = datetime(2026, 11, 19, 2, tzinfo=timezone.utc)

    def test_required_validated_amount_category_and_date(self):
        for values in (
            (" ", "Ingredients", 100, "2026-11-19 13:21"),
            ("Tocino", "All", 100, "2026-11-19 13:21"),
            ("Tocino", "Capital", 100, "2026-11-19 13:21"),
            ("Tocino", "Ingredients", 0, "2026-11-19 13:21"),
            ("Tocino", "Ingredients", -1, "2026-11-19 13:21"),
            ("Tocino", "Ingredients", 2.5, "2026-11-19 13:21"),
            ("Tocino", "Ingredients", 100, "2026-02-30 13:21"),
        ):
            with self.subTest(values=values), self.assertRaises(ValueError):
                self.expenses.save(*values, "")
        self.assertEqual(self.expenses.period_view(*report_bounds("This Day", self.now)), (0, False, []))

    def test_persistence_filters_and_shared_period_total(self):
        first = self.expenses.save("  Tocino Mix  ", "Ingredients", 125050, "2026-11-19 00:00", "  note  ")
        self.expenses.save("Charcoal", "Charcoal", 3500, "2026-11-19 12:30", "")
        self.expenses.save("Tocino", "Ingredients", 5000, "2026-11-18 23:59", "")
        self.expenses.save("Bags", "Supplies", 2000, "2026-11-01 00:00", "")
        self.expenses.save("Unrelated", "Others", 1000, "2026-12-01 00:00", "")
        reopened = ExpenseStore(ProductStore(self.path))
        day = report_bounds("This Day", self.now)
        total, has_any, rows = reopened.period_view(*day, category="Ingredients", search=" toCIN ")
        self.assertEqual((total, has_any, [row["id"] for row in rows]), (128550, True, [first]))
        self.assertEqual(rows[0]["name"], "Tocino Mix")
        self.assertEqual(rows[0]["remarks"], "note")
        self.assertEqual(rows[0]["incurred_at"], "2026-11-18 16:00:00")
        self.assertEqual(reopened.total(*day), total)
        self.assertEqual(reopened.total(*report_bounds("This Week", self.now)), 133550)
        self.assertEqual(reopened.total(*report_bounds("This Month", self.now)), 135550)

    def test_edit_and_delete_keep_financial_history_and_order_records_safe(self):
        self.products.add(ProductFields("Skewer", 1500, 2, "Stick"))
        draft = OrderDraft()
        draft.add(self.products.list_products()[0], 1)
        order = self.orders.save_order(draft, "Ana", PAID, 1500, "")
        receipt = self.orders.get_receipt(order.id)
        target = self.expenses.save("Bags", "Supplies", 2000, "2026-11-19 10:00", "")
        other = self.expenses.save("Rice", "Ingredients", 1250, "2026-11-19 10:10", "")
        self.expenses.save("Plastic bags", "Supplies", 2200, "2026-11-19 10:00", "", expense_id=target)
        day = report_bounds("This Day", self.now)
        self.assertEqual(self.expenses.total(*day), 3450)
        self.expenses.delete(target)
        reopened = ExpenseStore(ProductStore(self.path))
        self.assertEqual([row["id"] for row in reopened.period_view(*day)[2]], [other])
        for period in ("This Day", "This Week", "This Month"):
            self.assertEqual(reopened.total(*report_bounds(period, self.now)), 3450)
        with self.assertRaises(ValueError):
            reopened.save("Bags", "Supplies", 1, "2026-11-19 10:00", "", expense_id=target)
        with closing(self.products.connect()) as connection:
            self.assertEqual(connection.execute("""
                SELECT expense_id, previous_amount_centavos FROM expense_corrections
            """).fetchall(), [(target, 2000)])
            self.assertEqual(connection.execute("PRAGMA foreign_key_check").fetchall(), [])
        self.assertEqual(self.orders.get_receipt(order.id), receipt)
        self.assertEqual(self.products.list_products()[0]["stock"], 1)

    def test_migration_backs_up_legacy_expenses_and_preserves_values(self):
        self.expenses.save("Bags", "Supplies", 2000, "2026-11-19 10:00", "")
        with closing(self.products.connect()) as connection, connection:
            connection.execute("DROP TRIGGER audit_expense_correction")
            connection.execute("DROP TABLE expense_corrections")
            connection.execute("ALTER TABLE expenses DROP COLUMN archived_at")
        self.orders.initialize()
        self.orders.initialize()
        (backup,) = (Path(self.path) / "backups").glob("grillflow-before-financial-history-*.sqlite3")
        with closing(sqlite3.connect(backup)) as connection:
            self.assertEqual(connection.execute("PRAGMA quick_check").fetchone(), ("ok",))
            self.assertEqual(connection.execute("SELECT name, amount_centavos FROM expenses").fetchall(),
                             [("Bags", 2000)])
            self.assertNotIn("archived_at", [row[1] for row in connection.execute("PRAGMA table_info(expenses)")])
        day = report_bounds("This Day", self.now)
        self.assertEqual(self.expenses.total(*day), 2000)
        self.expenses.save("Rice", "Ingredients", 100, "2026-11-19 10:00", "")
        self.assertEqual(self.expenses.total(*day), 2100)
