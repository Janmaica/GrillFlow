import sqlite3
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from tempfile import TemporaryDirectory

from order_draft import OrderDraft
from order_store import CREDIT, PAID, PARTIAL, OrderStore, parse_payment_amount
from product_store import ProductFields, ProductStore


class OrderStoreTests(unittest.TestCase):
    def setUp(self):
        data_dir = self.enterContext(TemporaryDirectory())
        self.products = ProductStore(data_dir)
        self.orders = OrderStore(self.products)
        self.orders.initialize()
        self.products.add(ProductFields("Skewer", 1275, 10, "Stick"))

    def draft(self):
        draft = OrderDraft()
        draft.add(self.products.list_products()[0], 2)
        return draft

    def rows(self, query):
        with closing(self.products.connect()) as connection:
            return connection.execute(query).fetchall()

    def execute(self, statement, args=()):
        with closing(self.products.connect()) as connection, connection:
            connection.execute(statement, args)

    def test_paid_partial_credit_and_change(self):
        for status, tender, customer, expected in (
            (PAID, 2550, "", (2550, 0)),
            (PAID, 3000, "", (2550, 0)),
            (PARTIAL, 1000, "Ana", (1000, 1550)),
            (CREDIT, 0, "Ben", (0, 2550)),
        ):
            with self.subTest(status=status, tender=tender):
                self.orders.save(self.draft(), customer, status, tender, "Test remarks")
                self.assertEqual(self.rows("""
                    SELECT amount_paid_centavos, outstanding_balance_centavos
                    FROM orders ORDER BY id DESC LIMIT 1
                """), [expected])
        self.assertEqual(self.rows("""
            SELECT amount_centavos, cash_tendered_centavos, change_centavos
            FROM payments ORDER BY id
        """), [(2550, 2550, 0), (2550, 3000, 450), (1000, 1000, 0)])
        self.assertEqual(self.rows("""
            SELECT product_name_snapshot, unit_snapshot, unit_price_centavos,
                   quantity, line_total_centavos FROM order_items ORDER BY id
        """), [("Skewer", "Stick", 1275, 2, 2550)] * 4)
        self.assertEqual(self.rows("SELECT total_centavos, preparation_status FROM orders"),
                         [(2550, "Pending")] * 4)
        self.assertEqual(self.rows("SELECT stock FROM products"), [(2,)])
        self.assertEqual(self.rows("SELECT order_number, customer_name FROM orders ORDER BY id"),
                         [("GF-0001", "Unknown1"), ("GF-0002", "Unknown2"),
                          ("GF-0003", "Ana"), ("GF-0004", "Ben")])

    def test_invalid_payments_do_not_write(self):
        for text in ("", "-1", "1e2", "4.999", "abc"):
            with self.subTest(text=text), self.assertRaises(ValueError):
                parse_payment_amount(text)
        self.assertEqual(parse_payment_amount(".05"), 5)
        for status, tender, customer in (
            (PAID, 2549, "Ana"), (PARTIAL, 0, "Ana"), (PARTIAL, 2550, "Ana"),
            (CREDIT, 0, "Unknown1"), (CREDIT, 1, "Ana"),
        ):
            with self.subTest(status=status, tender=tender), self.assertRaises(ValueError):
                self.orders.save(self.draft(), customer, status, tender, "")
        self.assertEqual(self.rows("SELECT * FROM orders"), [])
        self.assertEqual(self.rows("SELECT stock FROM products"), [(10,)])
        self.assertEqual(self.orders.preview(), ("GF-0001", "Unknown1"))

    def test_stock_price_and_missing_product_are_rechecked(self):
        draft = self.draft()
        self.execute("UPDATE products SET stock = 1")
        with self.assertRaisesRegex(ValueError, "Only 1 available"):
            self.orders.save(draft, "", PAID, 2550, "")
        self.assertEqual(self.rows("SELECT stock FROM products"), [(1,)])
        self.execute("UPDATE products SET stock = 10, selling_price = 5000")
        with self.assertRaisesRegex(ValueError, "price .* changed"):
            self.orders.save(draft, "", PAID, 2550, "")
        self.assertEqual(self.rows("SELECT stock FROM products"), [(10,)])
        self.execute("DELETE FROM products")
        with self.assertRaisesRegex(ValueError, "no longer available"):
            self.orders.save(draft, "", PAID, 2550, "")
        self.assertEqual(self.rows("SELECT * FROM orders"), [])

    def test_failure_after_stock_update_rolls_back_everything(self):
        self.execute("""
            CREATE TRIGGER fail_payment BEFORE INSERT ON payments
            BEGIN SELECT RAISE(ABORT, 'test failure'); END
        """)
        with self.assertRaises(sqlite3.IntegrityError):
            self.orders.save(self.draft(), "", PAID, 2550, "")
        for table in ("orders", "order_items", "payments"):
            self.assertEqual(self.rows(f"SELECT * FROM {table}"), [])
        self.assertEqual(self.rows("SELECT stock FROM products"), [(10,)])
        self.assertEqual(self.orders.preview(), ("GF-0001", "Unknown1"))

    def test_persisted_summary_uses_preparation_and_balance(self):
        self.orders.save(self.draft(), "", PAID, 2550, "")
        self.orders.save(self.draft(), "Ana", PARTIAL, 1000, "")
        self.orders.save(self.draft(), "Ben", CREDIT, 0, "")
        self.execute("UPDATE orders SET preparation_status = 'Ready' WHERE id = 1")
        self.execute("UPDATE orders SET preparation_status = 'Received' WHERE id = 2")
        reopened = OrderStore(ProductStore(self.products.data_dir))
        summary, recent = reopened.sales_summary()
        self.assertEqual(summary, {"active": 1, "ready": 1, "unpaid": 2})
        self.assertEqual([order["order_id"] for order in recent], ["GF-0003", "GF-0002", "GF-0001"])
        self.assertEqual(reopened.preview(), ("GF-0004", "Unknown2"))

    def test_concurrent_checkouts_allocate_unique_numbers(self):
        drafts = [self.draft(), self.draft()]
        self.assertEqual(self.orders.preview(), ("GF-0001", "Unknown1"))
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(
                lambda draft: self.orders.save(draft, "", PAID, 2550, ""), drafts,
            ))
        self.assertCountEqual(results, ["GF-0001", "GF-0002"])
        self.assertEqual(self.rows("SELECT customer_name FROM orders ORDER BY id"),
                         [("Unknown1",), ("Unknown2",)])
        self.assertEqual(self.rows("SELECT stock FROM products"), [(6,)])

    def test_preparation_changes_preserve_payments_and_stock(self):
        order = self.orders.save_order(self.draft(), "Ana", PARTIAL, 1000, "")
        for action, stored, counts in (
            ("Done", "Ready", {"active": 0, "ready": 1, "unpaid": 1}),
            ("Pending", "Pending", {"active": 1, "ready": 0, "unpaid": 1}),
        ):
            self.orders.set_preparation(order.id, action)
            reopened = OrderStore(ProductStore(self.products.data_dir))
            summary, recent = reopened.sales_summary()
            self.assertEqual(summary, counts)
            self.assertEqual(recent[0]["preparation_status"], stored)
            self.assertEqual(recent[0]["payment_status"], PARTIAL)
        self.execute("UPDATE orders SET preparation_status = 'Received'")
        with self.assertRaises(ValueError):
            self.orders.set_preparation(order.id, "Pending")
        self.assertEqual(self.rows("SELECT preparation_status FROM orders"), [("Received",)])
        self.assertEqual(self.rows("SELECT stock FROM products"), [(8,)])
        self.assertEqual(self.rows("SELECT amount_centavos FROM payments"), [(1000,)])

    def test_additional_payments_and_duplicate_prevention(self):
        order = self.orders.save_order(self.draft(), "Ana", CREDIT, 0, "")
        self.orders.record_payment(order.id, PARTIAL, 1000, expected_paid=0)
        for status, tender, expected_paid in (
            (PARTIAL, 1000, 0), (PAID, 1549, 1000), (CREDIT, 0, 1000),
            (PARTIAL, 1550, 1000),
        ):
            with self.assertRaises(ValueError):
                self.orders.record_payment(order.id, status, tender, expected_paid=expected_paid)
        self.assertEqual(self.orders.get_receipt(order.id).balance, 1550)
        self.orders.record_payment(order.id, PAID, 1600, expected_paid=1000)
        with self.assertRaises(ValueError):
            self.orders.record_payment(order.id, PAID, 1600, expected_paid=1000)
        self.assertEqual(self.rows("""
            SELECT total_centavos, amount_paid_centavos, outstanding_balance_centavos,
                   preparation_status, payment_status FROM orders
        """), [(2550, 2550, 0, "Pending", "Paid")])
        receipt = self.orders.get_receipt(order.id)
        self.assertEqual(receipt.status, PAID)
        self.assertEqual([(payment.applied, payment.change) for payment in receipt.payments],
                         [(1000, 0), (1550, 50)])
        self.assertEqual(self.orders.sales_summary()[0]["unpaid"], 0)
        self.assertEqual(self.rows("SELECT stock FROM products"), [(8,)])
