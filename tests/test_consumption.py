import sqlite3
import unittest
from contextlib import closing
from datetime import datetime, timezone
from tempfile import TemporaryDirectory

from consumption_store import ConsumptionStore
from expense_store import ExpenseStore
from order_store import RESET_TABLES, OrderStore, history_bounds, report_bounds
from product_store import ProductFields, ProductStore


class ConsumptionTests(unittest.TestCase):
    def setUp(self):
        self.directory = self.enterContext(TemporaryDirectory())
        self.products = ProductStore(self.directory)
        self.orders = OrderStore(self.products)
        self.orders.initialize()
        self.consumption = ConsumptionStore(self.products)
        self.product = self.products.add(ProductFields("Pork bbq", 1500, 12, "Stick"))
        self.now = datetime(2026, 11, 19, 2, tzinfo=timezone.utc)
        self.day = report_bounds("This Day", self.now)

    def test_reporting_filters_stock_and_persistence(self):
        rice = self.products.add(ProductFields("Rice", 500, 6, "Serving"))
        self.assertEqual(self.consumption.period_view(*self.day), (0, []))
        first = self.consumption.save(self.product, 5, "2026-11-19 00:00", "Dinner")
        latest = self.consumption.save(rice, 2, "2026-11-19 18:20")
        self.consumption.save(rice, 1, "2026-11-18 23:59")
        self.consumption.save(rice, 1, "2026-11-01 06:00")
        reopened_products = ProductStore(self.directory)
        OrderStore(reopened_products).initialize()
        reopened = ConsumptionStore(reopened_products)
        total, rows = reopened.period_view(*self.day)
        self.assertEqual((total, [row["id"] for row in rows]), (8500, [latest, first]))
        self.assertEqual(rows[1]["consumed_at"], "2026-11-18 16:00:00")
        self.assertEqual(rows[1]["remarks"], "Dinner")
        self.assertEqual(reopened.total(*history_bounds("Today", self.now)), total)
        self.assertEqual(reopened.period_view(*self.day, search="  PORK   BbQ ")[1][0]["id"], first)
        self.assertEqual(reopened.total(*report_bounds("This Week", self.now)), 9000)
        self.assertEqual(reopened.total(*report_bounds("This Month", self.now)), 9500)
        self.assertEqual({p["id"]: p["stock"] for p in reopened_products.list_products()},
                         {self.product: 7, rice: 2})

    def test_failed_save_leaves_inventory_unchanged(self):
        for units in (0, -1, 1.5, 13):
            with self.subTest(units=units), self.assertRaises(ValueError):
                self.consumption.save(self.product, units, "2026-11-19 10:00")
        with self.assertRaisesRegex(ValueError, "selling price changed"):
            self.consumption.save(self.product, 1, "2026-11-19 10:00", expected_price=1000)
        with self.assertRaises(ValueError):
            self.consumption.save(self.product, 1, "2026-02-30 10:00")
        with closing(self.products.connect()) as connection, connection:
            connection.execute("""
                CREATE TRIGGER reject_test_consumption BEFORE INSERT ON family_consumption
                BEGIN SELECT RAISE(ABORT, 'test rollback'); END
            """)
        with self.assertRaisesRegex(sqlite3.IntegrityError, "test rollback"):
            self.consumption.save(self.product, 3, "2026-11-19 10:00")
        self.assertEqual(self.products.list_products()[0]["stock"], 12)
        self.assertEqual(self.consumption.period_view(*self.day), (0, []))

    def test_archive_keeps_value_stock_and_financial_isolation(self):
        record = self.consumption.save(self.product, 5, "2026-11-19 10:00")
        product = self.products.list_products()[0]
        self.products.update(product, ProductFields("New name", 2500, 7, "Pack"), None)
        _, rows = self.consumption.period_view(*self.day)
        self.assertEqual(tuple(rows[0][column] for column in (
            "product_name_snapshot", "unit_snapshot", "selling_price_centavos", "retail_value_centavos",
        )), ("Pork bbq", "Stick", 1500, 7500))
        self.consumption.archive(record)
        self.assertEqual(self.consumption.period_view(*self.day), (7500, []))
        self.assertEqual(self.products.list_products()[0]["stock"], 7)
        self.products.delete(self.product)
        self.assertEqual(self.products.list_products(), [])
        with self.assertRaisesRegex(ValueError, "active product"):
            self.consumption.save(self.product, 1, "2026-11-19 10:00")
        self.assertEqual(self.orders.report_summary(*self.day), (0, 0, 0, 0))
        self.assertEqual(self.orders.ranked_products(*self.day), [])
        self.assertEqual(self.orders.credit_customer_groups(), {})
        self.assertEqual(ExpenseStore(self.products).total(*self.day), 0)
        self.assertLess(RESET_TABLES.index("family_consumption"), RESET_TABLES.index("products"))
        with closing(self.products.connect()) as connection:
            self.assertEqual(connection.execute("PRAGMA foreign_key_check").fetchall(), [])
            self.assertEqual(connection.execute("SELECT stock FROM products").fetchone(), (7,))
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM family_consumption").fetchone(), (1,))
