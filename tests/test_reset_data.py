import sqlite3
import unittest
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from consumption_store import ConsumptionStore
from order_draft import OrderDraft
from order_store import PAID, PARTIAL, RESET_TABLES, OrderStore
from product_store import ProductFields, ProductStore


class ResetDataTests(unittest.TestCase):
    def setUp(self):
        self.directory = Path(self.enterContext(TemporaryDirectory()))
        self.products = ProductStore(self.directory)
        self.orders = OrderStore(self.products)
        self.orders.initialize()
        images = self.directory / "product_photos"
        images.mkdir()
        self.photo = images / "uploaded.png"
        self.photo.write_bytes(b"uploaded")
        self.unrelated = images / "unrelated.png"
        self.unrelated.write_bytes(b"unrelated")
        self.asset = self.directory / "splash_background.png"
        self.asset.write_bytes(b"outside the uploaded photos directory")
        self.product_id = self.products.add(ProductFields("Skewer", 1000, 4, "Stick"), self.photo.name)
        self.products.add(ProductFields("Default photo", 1000, 3, "Stick"), "../splash_background.png")
        draft = OrderDraft()
        draft.add(next(row for row in self.products.list_products() if row["id"] == self.product_id), 1)
        self.order = self.orders.save_order(draft, "Ana", PARTIAL, 400, "")
        self.orders.move_to_credit(self.order.id, expected_paid=400)
        consumption = ConsumptionStore(self.products)
        consumed = consumption.save(self.product_id, 1, "2026-11-19 10:00")
        consumption.archive(consumed)
        with closing(self.products.connect()) as connection, connection:
            connection.execute("CREATE TABLE app_settings (theme TEXT NOT NULL)")
            connection.execute("INSERT INTO app_settings VALUES ('light')")

    def contents(self):
        with closing(self.products.connect()) as connection:
            return {table: connection.execute(f"SELECT * FROM {table}").fetchall() for table in RESET_TABLES}

    def test_reset_backs_up_clears_business_tables_and_preserves_schema(self):
        original = self.contents()
        with closing(self.products.connect()) as connection:
            schema = connection.execute("SELECT type, name, sql FROM sqlite_master ORDER BY name").fetchall()
        result = self.orders.reset_all_data()
        self.assertEqual(result.backup_path.parent, self.directory / "backups")
        with closing(sqlite3.connect(result.backup_path)) as backup:
            self.assertEqual({table: backup.execute(f"SELECT * FROM {table}").fetchall()
                              for table in RESET_TABLES}, original)
        self.assertFalse(any(self.contents().values()))
        self.assertFalse(result.photo_cleanup_failed)
        self.assertFalse(self.photo.exists())
        self.assertTrue(self.unrelated.is_file() and self.asset.is_file())
        with closing(self.products.connect()) as connection:
            self.assertEqual(connection.execute("SELECT type, name, sql FROM sqlite_master ORDER BY name").fetchall(),
                             schema)
            self.assertEqual(connection.execute("PRAGMA foreign_key_check").fetchall(), [])
            self.assertEqual(connection.execute("SELECT theme FROM app_settings").fetchall(), [("light",)])
        reopened = OrderStore(ProductStore(self.directory))
        self.assertFalse(reopened.named_customers())
        self.assertIsNone(reopened.get_receipt(self.order.id))
        self.assertEqual(reopened.report_summary("2000", "2100"), (0, 0, 0, 0))
        replacement = self.products.add(ProductFields("Skewer", 1000, 2, "Stick"))
        self.assertGreater(replacement, self.product_id)
        draft = OrderDraft()
        draft.add(self.products.list_products()[0], 1)
        self.assertGreater(reopened.save_order(draft, "", PAID, 1000, "").id, self.order.id)

    def test_backup_failure_leaves_records_and_photos_intact(self):
        original = self.contents()
        with patch.object(self.orders, "_backup_before_reset", side_effect=OSError("test backup failure")):
            with self.assertRaises(OSError):
                self.orders.reset_all_data()
        self.assertEqual(self.contents(), original)
        self.assertTrue(self.photo.exists())

    def test_delete_failure_rolls_back_all_tables(self):
        with closing(self.products.connect()) as connection, connection:
            connection.execute("""
                CREATE TRIGGER fail_test_reset BEFORE DELETE ON products
                BEGIN SELECT RAISE(ABORT, 'test reset failure'); END
            """)
        original = self.contents()
        with self.assertRaisesRegex(sqlite3.IntegrityError, "test reset failure"):
            self.orders.reset_all_data()
        self.assertEqual(self.contents(), original)
        self.assertTrue(self.photo.exists())
        self.assertEqual(len(list((self.directory / "backups").glob("*.sqlite3"))), 1)
