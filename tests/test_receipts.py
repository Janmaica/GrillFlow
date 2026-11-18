import unittest
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from order_draft import OrderDraft
from order_store import CREDIT, PAID, PARTIAL, OrderStore
from product_store import ProductFields, ProductStore
from receipt_export import DesktopReceiptOutput


class ReceiptTests(unittest.TestCase):
    def setUp(self):
        self.path = Path(self.enterContext(TemporaryDirectory()))
        self.products = ProductStore(self.path)
        self.orders = OrderStore(self.products)
        self.orders.initialize()
        self.products.add(ProductFields("Skewer <special>", 1275, 10, "Stick"))

    def save(self, mode, tender):
        draft = OrderDraft()
        draft.add(self.products.list_products()[0], 2)
        return self.orders.save_order(draft, "Ana & Co", mode, tender, "Use <paper>")

    def state(self):
        with closing(self.products.connect()) as connection:
            return tuple(connection.execute(query).fetchall() for query in (
                "SELECT stock FROM products",
                "SELECT * FROM orders ORDER BY id",
                "SELECT * FROM order_items ORDER BY id",
                "SELECT * FROM payments ORDER BY id",
            ))

    def test_paid_partial_and_unpaid_receipts(self):
        for mode, tender, status, balances, expected_details in (
            (PAID, 3000, "Paid", (2550, 0), ("Cash Received / Tendered", "₱30.00")),
            (PARTIAL, 1200, "Partially Paid", (1200, 1350), ("Remaining Balance", "₱13.50")),
            (CREDIT, 0, "Unpaid", (0, 2550), ("Amount Paid", "₱0.00")),
        ):
            with self.subTest(mode=mode):
                saved = self.save(mode, tender)
                before = self.state()
                receipt = self.orders.get_receipt(saved.id)
                self.assertEqual(receipt.status, status)
                self.assertEqual((receipt.applied, receipt.balance), balances)
                self.assertEqual((receipt.total, receipt.items[0].quantity, receipt.items[0].subtotal),
                                 (2550, 2, 2550))
                self.assertIn(expected_details, receipt.amounts())
                if mode == PAID:
                    self.assertIn(("Change (Sukli)", "₱4.50"), receipt.amounts())
                self.assertEqual(self.state(), before)
        self.assertIsNone(self.orders.get_receipt(999))

    def test_reopened_receipt_uses_item_snapshots_and_latest_payment_history(self):
        saved = self.save(PARTIAL, 1000)
        with closing(self.products.connect()) as connection, connection:
            connection.execute("UPDATE products SET name = 'Renamed', selling_price = 9900")
            connection.execute("""
                INSERT INTO payments (order_id, amount_centavos, cash_tendered_centavos, change_centavos)
                VALUES (?, 1550, 2000, 450)
            """, (saved.id,))
        before = self.state()
        receipt = OrderStore(ProductStore(self.path)).get_receipt(saved.id)
        self.assertEqual((receipt.items[0].name, receipt.items[0].unit_price), ("Skewer <special>", 1275))
        self.assertEqual([(p.applied, p.tendered, p.change) for p in receipt.payments],
                         [(1000, 1000, 0), (1550, 2000, 450)])
        self.assertEqual(receipt.status, "Paid")
        self.assertEqual(receipt.balance, 0)
        self.assertEqual(self.state(), before)

    def test_print_contains_only_selected_receipt_and_escapes_input(self):
        saved = self.save(PAID, 3000)
        other = self.save(CREDIT, 0)
        receipt = self.orders.get_receipt(saved.id)
        with patch("receipt_export.webbrowser.open", return_value=True) as browser:
            DesktopReceiptOutput(self.path).print_receipt(receipt)
        (output,) = (self.path / "receipts").glob("*.html")
        browser.assert_called_once_with(output.resolve().as_uri())
        text = output.read_text(encoding="utf-8")
        self.assertIn("SALES RECEIPT", text)
        self.assertIn("Print / Save as PDF", text)
        self.assertIn("Skewer &lt;special&gt;", text)
        self.assertIn("Ana &amp; Co", text)
        self.assertIn("Use &lt;paper&gt;", text)
        self.assertNotIn(other.order_number, text)
