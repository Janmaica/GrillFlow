import sqlite3
import unittest
from pathlib import Path
from contextlib import closing
from tempfile import TemporaryDirectory

from order_draft import OrderDraft
from order_store import PAID, OrderStore
from product_store import ProductConflict, ProductStore, validate_product


class ProductManagementTests(unittest.TestCase):
    def setUp(self):
        self.directory = self.enterContext(TemporaryDirectory())
        self.products = ProductStore(self.directory)
        self.products.initialize()

    def fields(self, name="PORK BBQ", price="15.00", stock="120"):
        return validate_product(name, price, stock, "Stick")

    def test_add_and_edit_reject_duplicate_normalized_names(self):
        first_id = self.products.add(self.fields())
        second_id = self.products.add(self.fields("Chicken bbq"))
        for name in ("PORK BBQ", " pork bbq ", "Pork   BBQ"):
            with self.subTest(name=name), self.assertRaisesRegex(sqlite3.IntegrityError, "Product already Exist"):
                self.products.add(self.fields(name))
        original = self.products.list_products()[0]
        self.assertEqual(original["id"], second_id)
        with self.assertRaisesRegex(sqlite3.IntegrityError, "Product already Exist"):
            self.products.update(original, self.fields("Pork   BBQ"), None)
        self.products.update(original, self.fields("Chicken BBQ", "17.50", "80"), "new.png")
        saved = self.products.list_products()[0]
        self.assertEqual(tuple(saved), (second_id, "Chicken bbq", 1750, 80, "Stick", "new.png"))
        self.products.update(saved, self.fields("Chicken thigh", "17.50", "0"), None)
        reopened = ProductStore(self.directory).list_products()
        self.assertEqual((reopened[0]["name"], reopened[0]["stock"], reopened[1]["id"]),
                         ("Chicken thigh", 0, first_id))

    def test_invalid_stock_is_rejected_and_stale_stock_is_not_overwritten(self):
        for stock in ("-1", "2.5", "", "letters"):
            with self.subTest(stock=stock), self.assertRaises(ValueError):
                self.fields(stock=stock)
        self.products.add(self.fields())
        original = self.products.list_products()[0]
        self.products.update(original, self.fields(stock="80"), None)
        with self.assertRaises(ProductConflict):
            self.products.update(original, self.fields(stock="90"), None)
        self.assertEqual(self.products.list_products()[0]["stock"], 80)

    def test_delete_unused_product_and_do_not_reuse_id(self):
        product_id = self.products.add(self.fields())
        self.products.delete(product_id)
        with closing(self.products.connect()) as connection:
            self.assertEqual(connection.execute("SELECT * FROM products").fetchall(), [])
        self.assertNotEqual(self.products.add(self.fields()), product_id)

    def test_product_photo_is_removed_only_when_no_product_shares_it(self):
        images = Path(self.directory) / "product_photos"
        images.mkdir()
        shared = images / "shared.png"
        shared.write_bytes(b"photo")
        first = self.products.add(self.fields(), shared.name)
        second = self.products.add(self.fields("Chicken"), shared.name)
        self.products.delete(first)
        self.assertTrue(shared.is_file())
        self.products.delete(second)
        self.assertFalse(shared.exists())
        outside = Path(self.directory) / "outside.png"
        outside.write_bytes(b"asset")
        product = self.products.add(self.fields(), "../outside.png")
        self.products.delete(product)
        self.assertTrue(outside.is_file())

    def test_sold_product_can_be_removed_without_losing_sales(self):
        orders = OrderStore(self.products)
        orders.initialize()
        product_id = self.products.add(self.fields())
        draft = OrderDraft()
        draft.add(self.products.list_products()[0], 1)
        order = orders.save_order(draft, "", PAID, 1500, "")
        original_receipt = orders.get_receipt(order.id)
        current = self.products.list_products()[0]
        self.products.update(current, self.fields("Pork skewer", "18.00", "80"), None)
        ranking = orders.ranked_products("2000", "2100")
        self.products.delete(product_id)
        self.assertEqual(self.products.list_products(), [])
        self.assertEqual(orders.get_receipt(order.id), original_receipt)
        self.assertTrue(orders.delete_order(order.id))
        self.assertEqual(orders.ranked_products("2000", "2100"), ranking)
        with self.assertRaisesRegex(ValueError, "no longer available"):
            orders.save_order(draft, "", PAID, 1500, "")
        self.assertFalse(self.products.name_exists("  PORK   SKEWER "))
        replacement = self.products.add(self.fields("Pork Skewer", "25", "9"))
        self.assertNotEqual(replacement, product_id)
        self.assertTrue(self.products.name_exists("  PORK   SKEWER "))
        with self.assertRaisesRegex(sqlite3.IntegrityError, "Product already Exist"):
            self.products.add(self.fields("Pork   Skewer"))
        with closing(self.products.connect()) as connection:
            self.assertEqual(connection.execute(
                "SELECT stock, selling_price, is_active FROM products ORDER BY id"
            ).fetchall(), [(80, 1800, 0), (9, 2500, 1)])
            self.assertEqual(connection.execute("PRAGMA foreign_key_check").fetchall(), [])
        self.assertEqual(orders.get_receipt(order.id), original_receipt)

    def test_legacy_duplicates_are_reported_and_preserved(self):
        self.products.add(self.fields())
        with closing(self.products.connect()) as connection, connection:
            connection.execute("DROP TRIGGER products_unique_active_name_insert")
            connection.execute("DROP TRIGGER products_unique_active_name_update")
            connection.execute("""
                INSERT INTO products (name, selling_price, stock, unit)
                VALUES ('PORK   BBQ', 1500, 4, 'Stick')
            """)
            connection.execute("ALTER TABLE products DROP COLUMN is_active")
        self.products.initialize()
        self.assertEqual(self.products.duplicate_names(), [("PORK   BBQ", 2)])
        self.assertEqual(len(self.products.list_products()), 2)
        with self.assertRaisesRegex(sqlite3.IntegrityError, "Product already Exist"):
            self.products.add(self.fields())
        duplicate = self.products.list_products()[0]
        self.products.update(duplicate, self.fields("Pork special", stock="4"), None)
        self.assertEqual(self.products.duplicate_names(), [])

    def test_active_name_migration_preserves_archives_and_supports_reuse_after_reopen(self):
        orders = OrderStore(self.products)
        orders.initialize()
        archived = self.products.add(self.fields())
        draft = OrderDraft()
        draft.add(self.products.list_products()[0], 1)
        saved = orders.save_order(draft, "", PAID, 1500, "")
        receipt = orders.get_receipt(saved.id)
        with closing(self.products.connect()) as connection, connection:
            connection.execute("UPDATE products SET is_active = 0 WHERE id = ?", (archived,))
        with closing(self.products.connect()) as connection, connection:
            connection.execute("""
                CREATE TRIGGER products_unique_name_insert BEFORE INSERT ON products
                WHEN EXISTS (SELECT 1 FROM products
                             WHERE grillflow_name_key(name) = grillflow_name_key(NEW.name))
                BEGIN SELECT RAISE(ABORT, 'Product already Exist'); END
            """)
            connection.execute("""
                CREATE TRIGGER products_unique_name_update BEFORE UPDATE OF name ON products
                WHEN grillflow_name_key(NEW.name) <> grillflow_name_key(OLD.name)
                AND EXISTS (SELECT 1 FROM products
                            WHERE grillflow_name_key(name) = grillflow_name_key(NEW.name))
                BEGIN SELECT RAISE(ABORT, 'Product already Exist'); END
            """)
            before = connection.execute("SELECT * FROM products").fetchall()
        with self.assertRaisesRegex(sqlite3.IntegrityError, "Product already Exist"):
            self.products.add(self.fields())

        reopened = ProductStore(self.directory)
        reopened.initialize()
        with closing(reopened.connect()) as connection:
            self.assertEqual(connection.execute("SELECT * FROM products").fetchall(), before)
        edited = reopened.add(self.fields("Temporary"))
        reopened.update(reopened.list_products()[0], self.fields(), None)
        self.assertEqual(reopened.list_products()[0]["id"], edited)
        self.assertEqual(reopened.duplicate_names(), [])
        with closing(reopened.connect()) as connection, self.assertRaisesRegex(
            sqlite3.IntegrityError, "Product already Exist"
        ):
            connection.execute("UPDATE products SET is_active = 1 WHERE id = ?", (archived,))
        ids = [archived, edited]
        for _ in range(3):
            reopened.delete(ids[-1])
            reopened = ProductStore(self.directory)
            reopened.initialize()
            ids.append(reopened.add(self.fields("  Pork   BBQ ")))
        self.assertEqual(ids, sorted(set(ids)))
        self.assertEqual(OrderStore(reopened).get_receipt(saved.id), receipt)
