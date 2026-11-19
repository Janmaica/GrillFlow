import sqlite3
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from tempfile import TemporaryDirectory

from order_draft import OrderDraft
from order_store import CREDIT, PAID, PARTIAL, PAY_LATER, OrderStore, parse_payment_amount
from product_store import ProductFields, ProductStore


class OrderStoreTests(unittest.TestCase):
    def test_named_customers_exclude_archives_except_outstanding_credit(self):
        maria = self.orders.save_order(self.draft(), "Maria", PAID, 2550, "")
        duplicate = self.orders.save_order(self.draft(), "MARIA", PAID, 2550, "")
        henry = self.orders.save_order(self.draft(), "Henry", CREDIT, 0, "")
        self.execute("UPDATE orders SET customer_name = ' maria ' WHERE id = ?", (duplicate.id,))
        self.assertEqual(self.orders.named_customers(), ["Henry", "Maria"])
        with self.assertRaisesRegex(ValueError, "unpaid balances"):
            self.orders.delete_history("2000", "2100", {maria.id, duplicate.id, henry.id})
        self.assertEqual(self.orders.named_customers(), ["Henry", "Maria"])
        # Simulate an outstanding credit order archived by an older version.
        self.execute("UPDATE orders SET archived_at = CURRENT_TIMESTAMP WHERE id = ?", (henry.id,))
        self.orders.delete_history("2000", "2100", {maria.id, duplicate.id})
        self.assertEqual(self.orders.named_customers(), ["Henry"])
        self.assertIsNone(self.orders.get_receipt(maria.id))
        self.orders.record_credit_payment(henry.id, 2550, expected_paid=0)
        reopened = OrderStore(ProductStore(self.products.data_dir))
        self.assertEqual(reopened.named_customers(), [])
        self.assertEqual(reopened.get_receipt(henry.id).balance, 0)
        self.orders.save_order(self.draft(), "New customer", PAID, 2550, "")
        self.assertEqual(reopened.named_customers(), ["New customer"])

    def test_named_customers_use_history_and_credit_without_rewriting_existing_records(self):
        self.assertEqual(self.orders.named_customers(), [])
        for name, status, amount in (
            ("mARIA", PAID, 2550), ("  jAKE   CUENCA  ", CREDIT, 0),
            ("maria", CREDIT, 0), ("   ", PAID, 2550),
        ):
            self.orders.save_order(self.draft(), name, status, amount, "")
        self.execute("UPDATE orders SET customer_name = '  MARIA  ' WHERE id = 3")
        before = self.rows("SELECT customer_name, total_centavos, outstanding_balance_centavos FROM orders ORDER BY id")
        self.assertEqual(self.orders.named_customers(), ["Jake cuenca", "Maria"])
        self.assertEqual(self.rows(
            "SELECT customer_name, total_centavos, outstanding_balance_centavos FROM orders ORDER BY id"
        ), before)
        self.assertEqual([row[0] for row in before], ["Maria", "Jake cuenca", "  MARIA  ", "Unknown1"])
        self.orders.save_order(self.draft(), "HENRY", PAID, 2550, "")
        self.assertEqual(self.orders.named_customers(), ["Henry", "Jake cuenca", "Maria"])

    def test_pay_later_guest_can_pay_after_preparation(self):
        self.orders.save(self.draft(), "", PAID, 2550, "")
        with self.assertRaises(ValueError):
            self.orders.save(self.draft(), "", CREDIT, 1, "", arrangement=PAY_LATER)
        order = self.orders.save_order(self.draft(), "", CREDIT, 0, "", arrangement=PAY_LATER)
        self.assertEqual(self.rows("""
            SELECT customer_name, preparation_status, payment_status,
                   outstanding_balance_centavos, payment_arrangement FROM orders WHERE id = 2
        """), [("Unknown2", "Pending", "Unpaid", 2550, "pay_later")])
        receipt = self.orders.get_receipt(order.id)
        self.assertEqual((receipt.applied, receipt.balance, receipt.arrangement_label),
                         (0, 2550, "Pay Later"))
        self.assertEqual(receipt.payments, ())
        self.assertEqual(self.orders.sales_summary()[0]["customers_with_utang"], 0)
        self.orders.set_preparation(order.id, "Done")
        self.assertEqual(self.orders.get_receipt(order.id).status, CREDIT)
        self.orders.record_payment(order.id, PAID, 3000, expected_paid=0)
        with self.assertRaises(ValueError):
            self.orders.record_payment(order.id, PAID, 3000, expected_paid=0)
        reopened = OrderStore(ProductStore(self.products.data_dir))
        receipt = reopened.get_receipt(order.id)
        self.assertEqual((receipt.status, receipt.balance, receipt.payment_arrangement),
                         (PAID, 0, PAY_LATER))
        self.assertEqual((receipt.payments[0].applied, receipt.payments[0].change), (2550, 450))
        self.assertEqual(self.rows("SELECT stock FROM products"), [(6,)])
        self.assertEqual(self.rows("SELECT preparation_status FROM orders WHERE id = 2"), [("Ready",)])
        self.assertEqual(reopened.preview(), ("GF-0003", "Unknown3"))

    def test_migration_does_not_infer_legacy_arrangements(self):
        paid = self.orders.save_order(self.draft(), "", PAID, 2550, "")
        credit = self.orders.save_order(self.draft(), "Ana", CREDIT, 0, "")
        self.execute("DROP INDEX orders_generated_customer")
        self.execute("ALTER TABLE orders DROP COLUMN payment_arrangement")
        orders_before = self.rows("SELECT * FROM orders ORDER BY id")
        payments_before = self.rows("SELECT * FROM payments")
        self.orders.initialize()
        self.orders.initialize()
        self.assertEqual(self.rows("SELECT * FROM orders ORDER BY id"),
                         [row + (None,) for row in orders_before])
        self.assertEqual(self.rows("SELECT * FROM payments"), payments_before)
        self.assertEqual(self.orders.get_receipt(paid.id).status, PAID)
        self.assertEqual(self.orders.get_receipt(credit.id).status, CREDIT)

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
        self.assertEqual(summary, {"active": 1, "ready": 1, "customers_with_utang": 1})
        self.assertEqual([order["order_id"] for order in recent], ["GF-0003"])
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
            ("Done", "Ready", {"active": 0, "ready": 1, "customers_with_utang": 0}),
            ("Pending", "Pending", {"active": 1, "ready": 0, "customers_with_utang": 0}),
        ):
            self.orders.set_preparation(order.id, action)
            reopened = OrderStore(ProductStore(self.products.data_dir))
            summary, recent = reopened.sales_summary()
            self.assertEqual(summary, counts)
            self.assertEqual(recent[0]["preparation_status"], stored)
            history = reopened.history("2000-01-01", "2100-01-01")
            self.assertEqual(history[0]["preparation_status"], stored)
            self.assertEqual(history[0]["payment_status"], PARTIAL)
        self.execute("UPDATE orders SET preparation_status = 'Received'")
        with self.assertRaises(ValueError):
            self.orders.set_preparation(order.id, "Pending")
        self.assertEqual(self.rows("SELECT preparation_status FROM orders"), [("Received",)])
        self.assertEqual(self.rows("SELECT stock FROM products"), [(8,)])
        self.assertEqual(self.rows("SELECT amount_centavos FROM payments"), [(1000,)])

    def test_move_done_partial_to_credit_preserves_ledger_and_groups_balance(self):
        existing = self.orders.save_order(self.draft(), "Ana", CREDIT, 0, "")
        moved = self.orders.save_order(self.draft(), "ANA", PARTIAL, 1000, "")
        self.orders.set_preparation(moved.id, "Done")
        self.assertIn(moved.id, {row["saved_id"] for row in self.orders.sales_summary()[1]})
        before = self.orders.get_receipt(moved.id)
        stock = self.rows("SELECT stock FROM products")
        with self.assertRaisesRegex(ValueError, "balance changed"):
            self.orders.move_to_credit(moved.id, expected_paid=500)
        self.orders.move_to_credit(moved.id, expected_paid=1000)
        with self.assertRaises(ValueError):
            self.orders.move_to_credit(moved.id, expected_paid=1000)
        receipt = self.orders.get_receipt(moved.id)
        self.assertEqual((receipt.total, receipt.balance, receipt.payment_label, receipt.arrangement_label),
                         (2550, 1550, "Partially Paid (Credit)", "Credit (Utang)"))
        self.assertEqual((receipt.items, receipt.payments), (before.items, before.payments))
        self.assertNotIn(moved.id, {row["saved_id"] for row in self.orders.sales_summary()[1]})
        self.assertIn(moved.id, {row["id"] for row in self.orders.history("2000", "2100")})
        grouped = self.orders.credit_customer_groups()
        self.assertEqual(set(grouped), {"ana"})
        self.assertEqual({row["id"] for row in grouped["ana"]}, {existing.id, moved.id})
        self.assertEqual(sum(row["outstanding_balance_centavos"] for row in grouped["ana"]), 4100)
        audit = self.rows("""
            SELECT order_id, previous_arrangement, new_arrangement, remaining_balance_centavos,
                   transferred_at IS NOT NULL FROM order_arrangement_transfers
        """)
        self.assertEqual(audit, [(moved.id, "immediate", "credit", 1550, 1)])
        self.orders.record_credit_payment(moved.id, 500, expected_paid=1000)
        self.orders.record_credit_payment(moved.id, 1050, expected_paid=1500)
        reopened = OrderStore(ProductStore(self.products.data_dir))
        self.assertEqual([row["id"] for row in reopened.active_credit()], [existing.id])
        self.assertEqual([p.applied for p in reopened.get_receipt(moved.id).payments], [1000, 500, 1050])
        self.assertEqual(self.rows("SELECT stock FROM products"), stock)

    def test_move_pending_guest_requires_name_and_rejects_ineligible_orders(self):
        guest = self.orders.save_order(self.draft(), "", PARTIAL, 1000, "")
        with self.assertRaisesRegex(ValueError, "identifiable customer"):
            self.orders.move_to_credit(guest.id, expected_paid=1000, replacement_customer="Unknown 2")
        self.orders.move_to_credit(guest.id, expected_paid=1000, replacement_customer="  Ben  ")
        self.assertEqual(self.orders.get_receipt(guest.id).customer_name, "Ben")
        self.assertIn(guest.id, {row["saved_id"] for row in self.orders.sales_summary()[1]})
        self.assertEqual(self.orders.preview()[1], "Unknown2")
        paid = self.orders.save_order(self.draft(), "", PAID, 2550, "")
        later = self.orders.save_order(self.draft(), "Ben", CREDIT, 0, "", arrangement=PAY_LATER)
        self.orders.record_payment(later.id, PARTIAL, 1000, expected_paid=0)
        for order_id, tender in ((paid.id, 2550), (later.id, 1000)):
            with self.assertRaises(ValueError):
                self.orders.move_to_credit(order_id, expected_paid=tender)

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
        self.orders.record_payment(order.id, PAID, 1550, expected_paid=1000)
        with self.assertRaises(ValueError):
            self.orders.record_payment(order.id, PAID, 1550, expected_paid=1000)
        self.assertEqual(self.rows("""
            SELECT total_centavos, amount_paid_centavos, outstanding_balance_centavos,
                   preparation_status, payment_status FROM orders
        """), [(2550, 2550, 0, "Pending", "Paid")])
        receipt = self.orders.get_receipt(order.id)
        self.assertEqual(receipt.status, PAID)
        self.assertEqual([(payment.applied, payment.change) for payment in receipt.payments],
                         [(1000, 0), (1550, 0)])
        self.assertEqual(self.orders.sales_summary()[0]["customers_with_utang"], 0)
        self.assertEqual(self.rows("SELECT stock FROM products"), [(8,)])
