import sqlite3
import unittest
from contextlib import closing
from datetime import datetime, timezone
from tempfile import TemporaryDirectory

from order_draft import OrderDraft
from order_store import CREDIT, PAID, PARTIAL, PAY_LATER, OrderStore, OutstandingBalanceError, history_bounds
from product_store import ProductFields, ProductStore


class OrderHistoryTests(unittest.TestCase):
    def test_recent_keeps_ready_pay_later_until_ledger_balance_is_settled(self):
        paid = self.save_at(self.today[0])
        later = self.save_at(self.today[0], CREDIT, 0, arrangement=PAY_LATER)
        credit = self.save_at(self.today[0], CREDIT, 0)
        archived = self.save_at(self.today[0])
        received = self.save_at(self.today[0], CREDIT, 0, arrangement=PAY_LATER)

        def recent():
            return {row["saved_id"]: row["payment_status"] for row in self.orders.sales_summary()[1]}

        self.assertEqual(recent(), {paid: PAID, later: CREDIT, credit: CREDIT, archived: PAID, received: CREDIT})
        with closing(self.products.connect()) as connection, connection:
            connection.execute("UPDATE orders SET archived_at = CURRENT_TIMESTAMP WHERE id = ?", (archived,))
            connection.execute("UPDATE orders SET preparation_status = 'Received' WHERE id = ?", (received,))
        paid_receipt = self.orders.get_receipt(paid)
        credit_receipt = self.orders.get_receipt(credit)
        stock = self.products.list_products()[0]["stock"]
        for order_id in (paid, later, credit):
            self.orders.set_preparation(order_id, "Done")

        self.assertEqual(recent(), {later: CREDIT})
        self.orders.record_credit_payment(credit, 4000, expected_paid=0)
        self.assertEqual(recent(), {later: CREDIT})
        self.assertEqual([row["id"] for row in self.orders.active_credit()], [credit])

        self.orders.record_payment(later, PARTIAL, 4000, expected_paid=0)
        self.assertEqual(recent(), {later: PARTIAL})
        self.assertEqual(self.orders.get_receipt(later).balance, 6000)
        self.orders.record_payment(later, PAID, 6000, expected_paid=4000)
        self.assertEqual(recent(), {})
        self.assertEqual(self.ids(self.today), frozenset({paid, later, credit, received}))
        self.assertEqual(self.orders.get_receipt(paid), paid_receipt)
        self.assertEqual(self.orders.get_receipt(credit).items, credit_receipt.items)
        self.assertEqual(self.orders.get_receipt(later).total, 10000)
        self.assertEqual([p.applied for p in self.orders.get_receipt(later).payments], [4000, 6000])
        self.assertEqual(self.products.list_products()[0]["stock"], stock)

    def setUp(self):
        self.directory = self.enterContext(TemporaryDirectory())
        self.products = ProductStore(self.directory)
        self.orders = OrderStore(self.products)
        self.orders.initialize()
        self.products.add(ProductFields("Skewer", 10000, 20, "Stick"))
        now = datetime(2026, 11, 18, 16, 30, tzinfo=timezone.utc)
        self.today = history_bounds("Today", now)
        self.week = history_bounds("This Week", now)

    def save_at(self, timestamp, status=PAID, tendered=10000, *, arrangement=None):
        draft = OrderDraft()
        draft.add(self.products.list_products()[0], 1)
        saved = self.orders.save_order(draft, "Ana", status, tendered, "", arrangement=arrangement)
        with closing(self.products.connect()) as connection, connection:
            connection.execute("UPDATE orders SET created_at = ? WHERE id = ?", (timestamp, saved.id))
            connection.execute("UPDATE payments SET created_at = ? WHERE order_id = ?", (timestamp, saved.id))
        return saved.id

    def ids(self, bounds, repository=None):
        return frozenset(row["id"] for row in (repository or self.orders).history(*bounds))

    def test_philippine_day_and_monday_week_boundaries(self):
        self.assertEqual(self.today, ("2026-11-18 16:00:00", "2026-11-19 16:00:00"))
        self.assertEqual(self.week, ("2026-11-15 16:00:00", "2026-11-22 16:00:00"))
        ids = [self.save_at(timestamp) for timestamp in (
            "2026-11-15 15:59:59", self.week[0], self.today[0], self.today[1], self.week[1],
        )]
        self.assertEqual(self.ids(self.today), frozenset({ids[2]}))
        self.assertEqual(self.ids(self.week), frozenset(ids[1:4]))

    def test_delete_preserves_accounting_receipts_and_stock(self):
        first = self.save_at(self.today[0])
        second = self.save_at(self.today[0])
        receipt = self.orders.get_receipt(second)
        accounting = self.orders.sales_summary()
        stock = self.products.list_products()[0]["stock"]
        trend = self.orders.sales_trend(*self.today, hourly=True)
        ranking = self.orders.ranked_products(*self.today)
        first_receipt = self.orders.get_receipt(first)
        self.assertEqual(self.orders.financial_totals(*self.today), (20000, 20000, 0))
        self.assertTrue(self.orders.delete_order(first))
        self.assertFalse(self.orders.delete_order(first))
        reopened = OrderStore(ProductStore(self.directory))
        reopened.initialize()
        self.assertEqual(self.ids(self.today, reopened), frozenset({second}))
        self.assertEqual(reopened.get_receipt(first), first_receipt)
        self.assertNotIn(first, [order["saved_id"] for order in reopened.sales_summary()[1]])
        self.assertEqual(reopened.get_receipt(second), receipt)
        self.assertEqual(reopened.report_summary(*self.today), (20000, 20000, 0, 2))
        self.assertEqual(reopened.sales_trend(*self.today, hourly=True), trend)
        self.assertEqual(reopened.ranked_products(*self.today), ranking)
        self.assertEqual(reopened.sales_summary()[0]["active"], accounting[0]["active"] - 1)
        self.assertEqual(self.products.list_products()[0]["stock"], stock)
        with closing(self.products.connect()) as connection:
            self.assertEqual(connection.execute(
                "SELECT COUNT(archived_at), COUNT(*), SUM(outstanding_balance_centavos) FROM orders"
            ).fetchone(), (1, 2, 0))
            for table in ("order_items", "payments"):
                self.assertEqual(connection.execute(f"SELECT order_id FROM {table} ORDER BY order_id").fetchall(),
                                 [(first,), (second,)])
            self.assertEqual(connection.execute("PRAGMA foreign_key_check").fetchall(), [])

    def test_clear_today_and_week_without_deleting_new_or_outside_orders(self):
        older = self.save_at(self.week[0])
        outside = self.save_at(self.week[1])
        today = self.save_at(self.today[0])
        preview = self.ids(self.today)
        newer = self.save_at(self.today[0])
        weekly_expected = self.orders.report_summary(*self.week)
        with self.assertRaisesRegex(ValueError, "history changed"):
            self.orders.delete_history(*self.today, preview)
        self.assertEqual(self.ids(self.today), frozenset({today, newer}))
        self.assertEqual(self.orders.delete_history(*self.today, self.ids(self.today)), 2)
        self.assertEqual(self.ids(self.week), frozenset({older}))
        self.assertEqual(self.orders.delete_history(*self.week, self.ids(self.week)), 1)
        with closing(self.products.connect()) as connection:
            self.assertEqual(connection.execute(
                "SELECT id FROM orders WHERE archived_at IS NULL"
            ).fetchall(), [(outside,)])
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM orders").fetchone(), (4,))
        self.assertEqual(self.orders.report_summary(*self.week), weekly_expected)

    def test_delete_history_rolls_back_paid_orders_and_transfer_audit(self):
        first = self.save_at(self.today[0], PARTIAL, 4000)
        self.orders.move_to_credit(first, expected_paid=4000)
        self.orders.record_credit_payment(first, 6000, expected_paid=4000)
        second = self.save_at(self.today[0])
        expected = frozenset({first, second})
        originals = [self.orders.get_receipt(order_id) for order_id in sorted(expected)]
        with closing(self.products.connect()) as connection, connection:
            connection.execute(f"""
                CREATE TRIGGER block_test_delete BEFORE UPDATE OF archived_at ON orders WHEN OLD.id = {second}
                BEGIN SELECT RAISE(ABORT, 'test deletion failure'); END
            """)
        with self.assertRaisesRegex(sqlite3.IntegrityError, "test deletion failure"):
            self.orders.delete_history(*self.today, expected)
        self.assertEqual(self.ids(self.today), expected)
        self.assertEqual([self.orders.get_receipt(order_id) for order_id in sorted(expected)], originals)
        with closing(self.products.connect()) as connection, connection:
            self.assertEqual(connection.execute(
                "SELECT order_id FROM order_arrangement_transfers"
            ).fetchall(), [(first,)])
            connection.execute("DROP TRIGGER block_test_delete")
        self.assertEqual(self.orders.delete_history(*self.today, expected), 2)
        with closing(self.products.connect()) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM order_arrangement_transfers").fetchone(), (1,))
            self.assertEqual(connection.execute("PRAGMA foreign_key_check").fetchall(), [])

    def test_recent_history_credit_and_archive_balance_rules(self):
        paid = self.save_at(self.today[0])
        credit = self.save_at(self.today[0], CREDIT, 0)
        later = self.save_at(self.today[0], CREDIT, 0, arrangement=PAY_LATER)
        partial = self.save_at(self.today[0], PARTIAL, 4000)
        self.assertEqual({row["saved_id"] for row in self.orders.sales_summary()[1]},
                         {paid, credit, later, partial})
        self.assertEqual([row["id"] for row in self.orders.active_credit()], [credit])
        self.orders.set_preparation(paid, "Done")
        self.orders.set_preparation(credit, "Done")
        self.assertEqual({row["saved_id"] for row in self.orders.sales_summary()[1]}, {later, partial})
        self.assertEqual(self.ids(self.today), frozenset({paid, credit, later, partial}))
        stock = self.products.list_products()[0]["stock"]
        with self.assertRaises(OutstandingBalanceError):
            self.orders.delete_history(*self.today, self.ids(self.today))
        self.assertEqual(self.ids(self.today), frozenset({paid, credit, later, partial}))
        for unpaid in (credit, later, partial):
            with self.assertRaises(OutstandingBalanceError):
                self.orders.delete_order(unpaid)
        self.orders.record_payment(credit, PARTIAL, 4000, expected_paid=0)
        receipt = self.orders.get_receipt(credit)
        self.assertEqual((receipt.payment_label, receipt.balance), ("Partially Paid (Credit)", 6000))
        self.orders.record_payment(credit, PAID, 6000, expected_paid=4000)
        self.assertFalse(self.orders.active_credit())
        self.assertEqual(self.orders.get_receipt(credit).payment_label, "Paid")
        credit_receipt = self.orders.get_receipt(credit)
        summary = self.orders.report_summary(*self.today)
        self.assertTrue(self.orders.delete_order(credit))
        self.assertEqual(self.orders.get_receipt(credit), credit_receipt)
        self.assertEqual(self.orders.report_summary(*self.today), summary)
        self.assertEqual(self.orders.get_receipt(later).payment_label, "Unpaid")
        with closing(self.products.connect()) as conn, conn:
            # Historical archives remain included in the outstanding count.
            conn.execute("UPDATE orders SET archived_at = CURRENT_TIMESTAMP WHERE id = ?", (later,))
        reopened = OrderStore(ProductStore(self.directory))
        reopened.initialize()
        self.assertEqual(reopened.sales_summary()[0]["customers_with_utang"], 0)
        self.assertEqual(self.products.list_products()[0]["stock"], stock)

    def test_credit_details_include_item_snapshots_and_customer_history(self):
        old = self.save_at(self.week[0], CREDIT, 0)
        current = self.save_at(self.today[0], CREDIT, 0)
        self.save_at(self.today[0], CREDIT, 0, arrangement=PAY_LATER)
        self.orders.set_preparation(current, "Done")
        self.orders.record_payment(current, PARTIAL, 3500, expected_paid=0)
        self.orders.record_payment(old, PAID, 10000, expected_paid=0)
        with closing(self.products.connect()) as conn, conn:
            conn.execute("UPDATE products SET name = 'Renamed skewer'")
        active = self.orders.credit_details(bounds=self.today)
        self.assertEqual([row["id"] for row in active], [current])
        self.assertEqual(active[0]["items"], [("Skewer", 1)])
        self.assertEqual(active[0]["outstanding_balance_centavos"], 6500)
        self.assertEqual(active[0]["preparation_status"], "Ready")
        history = self.orders.credit_details(customer_key=" ANA ")
        self.assertEqual([row["id"] for row in history], [current, old])
        self.assertEqual(history[1]["payment_status"], PAID)

    def test_credit_installments_keep_separate_transactions_and_balances(self):
        self.products.add(ProductFields("Rice", 4000, 10, "Serving"))
        draft = OrderDraft()
        draft.add(self.products.list_products()[0], 1)
        first = self.orders.save_order(draft, "Ana", CREDIT, 0, "").id
        self.assertEqual(self.orders.sales_summary()[0]["customers_with_utang"], 1)
        draft = OrderDraft()
        draft.add(self.products.list_products()[0], 1)
        second = self.orders.save_order(draft, "ANA", CREDIT, 0, "").id
        stock = self.products.list_products()[0]["stock"]
        self.orders.record_credit_payment(first, 1000, expected_paid=0)
        reopened = OrderStore(ProductStore(self.directory))
        self.assertEqual(reopened.get_receipt(first).balance, 3000)
        self.assertEqual(reopened.sales_summary()[0]["customers_with_utang"], 1)
        for amount in (0, -100, 3001):
            with self.subTest(amount=amount), self.assertRaises(ValueError):
                reopened.record_credit_payment(first, amount, expected_paid=1000)
        with self.assertRaisesRegex(ValueError, "balance changed"):
            reopened.record_credit_payment(first, 1000, expected_paid=0)
        reopened.record_credit_payment(second, 500, expected_paid=0)
        reopened.record_credit_payment(first, 2000, expected_paid=1000)
        self.assertEqual(reopened.get_receipt(first).balance, 1000)
        self.assertEqual(reopened.sales_summary()[0]["customers_with_utang"], 1)
        reopened.record_credit_payment(first, 1000, expected_paid=3000)
        self.assertEqual(reopened.sales_summary()[0]["customers_with_utang"], 1)
        with closing(self.products.connect()) as connection, connection:
            payments = connection.execute("SELECT id, created_at FROM payments ORDER BY id").fetchall()
            self.assertEqual(len(payments), 4)
            for index, (payment_id, stamp) in enumerate(payments, start=19):
                datetime.fromisoformat(stamp)
                # Represent payments on successive days without changing the production clock.
                connection.execute("UPDATE payments SET created_at = ? WHERE id = ?",
                                   (f"2026-11-{index} 16:30:00", payment_id))
        receipt = reopened.get_receipt(first)
        self.assertEqual(receipt.payment_label, "Paid")
        self.assertEqual([(payment.applied, balance) for payment, balance in receipt.payment_steps()],
                         [(1000, 0), (2000, 1000), (1000, 3000)])
        self.assertEqual(reopened.credit_payment_history("ana"), [
            ("GF-0001", 1000, "2026-11-22 16:30:00", 0),
            ("GF-0001", 2000, "2026-11-21 16:30:00", 1000),
            ("GF-0002", 500, "2026-11-20 16:30:00", 3500),
            ("GF-0001", 1000, "2026-11-19 16:30:00", 3000),
        ])
        self.assertEqual([row["id"] for row in reopened.active_credit()], [second])
        self.assertEqual(self.products.list_products()[0]["stock"], stock)
        self.assertEqual(self.ids(("2000", "2100")), frozenset({first, second}))

    def test_sales_credit_count_uses_shared_customer_groups_and_ledger(self):
        settled = self.save_at(self.today[0], CREDIT, 0)
        outstanding = self.save_at(self.today[0], CREDIT, 0)
        self.save_at(self.today[0], CREDIT, 0, arrangement=PAY_LATER)
        self.orders.set_preparation(outstanding, "Done")
        with closing(self.products.connect()) as connection, connection:
            # Simulate legacy cached values that disagree with the ledger.
            connection.execute("""
                INSERT INTO payments (order_id, amount_centavos, cash_tendered_centavos, change_centavos)
                VALUES (?, 10000, 10000, 0)
            """, (settled,))
            connection.execute("""
                UPDATE orders SET archived_at = CURRENT_TIMESTAMP, payment_status = 'Paid',
                    amount_paid_centavos = total_centavos, outstanding_balance_centavos = 0
                WHERE id = ?
            """, (outstanding,))
        self.assertEqual(self.orders.sales_summary()[0]["customers_with_utang"], 1)
        with self.assertRaises(OutstandingBalanceError):
            self.orders.delete_order(outstanding)
        reopened = OrderStore(ProductStore(self.directory))
        self.assertEqual(reopened.sales_summary()[0]["customers_with_utang"], 1)
        reopened.record_payment(outstanding, PAID, 10000, expected_paid=0)
        self.assertEqual(reopened.sales_summary()[0]["customers_with_utang"], 0)
        self.assertEqual(len(reopened.get_receipt(settled).payments), 1)
        self.assertEqual(len(reopened.get_receipt(outstanding).payments), 1)
