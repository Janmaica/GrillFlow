import unittest
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from order_draft import OrderDraft
from order_store import CREDIT, PAID, OrderStore, report_bounds
from product_store import ProductFields, ProductStore
from report_output import write_report
from report_chart_data import axis_caption, axis_ticks, chart_buckets


class ReportTests(unittest.TestCase):
    def setUp(self):
        self.directory = Path(self.enterContext(TemporaryDirectory()))
        self.products = ProductStore(self.directory)
        self.orders = OrderStore(self.products)
        self.orders.initialize()
        self.skewer = self.products.add(ProductFields("Skewer", 1000, 15, "Stick"))
        self.rice = self.products.add(ProductFields("Rice", 500, 2, "Serving"))
        self.now = datetime(2026, 11, 18, 17, tzinfo=timezone.utc)
        self.day = report_bounds("This Day", self.now)

    def save(self, stamp, product_id, quantity, mode, tender):
        draft = OrderDraft()
        draft.add(next(row for row in self.products.list_products() if row["id"] == product_id), quantity)
        saved = self.orders.save_order(draft, "Ana", mode, tender, "")
        with closing(self.products.connect()) as connection, connection:
            connection.execute("UPDATE orders SET created_at = ? WHERE id = ?", (stamp, saved.id))
            connection.execute("UPDATE payments SET created_at = ? WHERE order_id = ?", (stamp, saved.id))
        return saved.id

    def test_manila_boundaries_and_trend_bucket_sizes(self):
        self.assertEqual(self.day, ("2026-11-18 16:00:00", "2026-11-19 16:00:00"))
        week = report_bounds("This Week", self.now)
        month = report_bounds("This Month", self.now)
        self.assertEqual(week, ("2026-11-15 16:00:00", "2026-11-22 16:00:00"))
        self.assertEqual(month, ("2026-10-31 16:00:00", "2026-11-30 16:00:00"))
        self.save(self.day[0], self.skewer, 1, PAID, 1000)
        self.save(self.day[1], self.skewer, 1, PAID, 1000)
        hours = self.orders.sales_trend(*self.day, hourly=True)
        self.assertEqual((len(hours), hours[0], sum(v for _, v in hours)), (24, ("00:00", 1000), 1000))
        self.assertEqual(len(self.orders.sales_trend(*week, hourly=False)), 7)
        self.assertEqual(len(self.orders.sales_trend(*month, hourly=False)), 30)

    def test_chart_period_labels_and_hourly_totals(self):
        self.assertEqual(sum(value for _, value in self.orders.sales_trend(*self.day, hourly=True)), 0)
        for timestamp in ("2026-11-19 00:00:00", "2026-11-19 00:40:00", "2026-11-19 06:29:00"):
            self.save(timestamp, self.skewer, 1, PAID, 1000)
        series = self.orders.sales_trend(*self.day, hourly=True)
        buckets = chart_buckets(series, "This Day", self.day[0])
        self.assertEqual(len(buckets), 24)
        self.assertEqual(buckets[8], ("8 AM", "8:00 AM", 2000))
        self.assertEqual(buckets[14], ("2 PM", "2:00 PM", 1000))
        week = report_bounds("This Week", self.now)
        buckets = chart_buckets(self.orders.sales_trend(*week, hourly=False), "This Week", week[0])
        self.assertEqual([short for short, _, _ in buckets], ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"])
        self.assertEqual(buckets[3], ("Thu", "Thursday, Nov 19", 3000))
        for month, length, first in ((2, 28, "Feb 1"), (11, 30, "Nov 1"), (12, 31, "Dec 1")):
            bounds = report_bounds("This Month", datetime(2026, month, 13, tzinfo=timezone.utc))
            buckets = chart_buckets(self.orders.sales_trend(*bounds, hourly=False), "This Month", bounds[0])
            self.assertEqual(len(buckets), length)
            self.assertEqual(buckets[0][0], first)

    def test_chart_axis_ticks_cover_small_and_large_sales(self):
        self.assertEqual(axis_ticks(0), (0,))
        self.assertEqual([axis_caption(tick) for tick in axis_ticks(88200)], ["₱0", "₱300", "₱600", "₱900"])
        for peak in (1, 5, 17, 9999, 900000000, (1 << 63) - 1):
            with self.subTest(peak=peak):
                ticks = axis_ticks(peak)
                self.assertIn(len(ticks), (4, 5))
                self.assertEqual(ticks[0], 0)
                self.assertGreaterEqual(ticks[-1], peak)
                self.assertTrue(all(axis_caption(tick).startswith("₱") for tick in ticks))
                self.assertEqual(len(set(map(axis_caption, ticks))), len(ticks))

    def test_cash_uses_payment_date_and_deletion_refreshes_shared_totals(self):
        old = self.save("2026-11-17 08:00:00", self.skewer, 3, CREDIT, 0)
        paid = self.save(self.day[0], self.rice, 1, PAID, 1000)
        credit = self.save(self.day[0], self.skewer, 2, CREDIT, 0)
        self.orders.record_credit_payment(old, 1200, expected_paid=0)
        self.orders.record_credit_payment(credit, 2000, expected_paid=0)
        with closing(self.products.connect()) as connection, connection:
            connection.execute("UPDATE payments SET created_at = ? WHERE order_id IN (?, ?)",
                               (self.day[0], old, credit))
        self.assertEqual(self.orders.report_summary(*self.day), (2500, 3700, 0, 2))
        self.assertEqual(self.orders.financial_totals(*self.day), (2500, 3700, 0))
        self.assertTrue(self.orders.delete_order(paid))
        reopened = OrderStore(ProductStore(self.directory))
        self.assertEqual(reopened.report_summary(*self.day), (2000, 3200, 0, 1))
        self.assertEqual(reopened.get_receipt(old).balance, 1800)

    def test_product_ranking_uses_snapshots_independently_of_stock(self):
        self.save(self.day[0], self.skewer, 3, PAID, 3000)
        self.save(self.day[0], self.rice, 2, PAID, 1000)
        with closing(self.products.connect()) as connection, connection:
            connection.execute("UPDATE products SET name = ?, selling_price = ? WHERE id = ?",
                               ("Renamed", 2500, self.skewer))
        self.assertEqual(self.orders.ranked_products(*self.day), [
            ["Skewer", "Stick", 3, 3000, None], ["Rice", "Serving", 2, 1000, None],
        ])
        self.assertEqual({row["name"]: row["stock"] for row in self.products.list_products()},
                         {"Renamed": 12, "Rice": 0})

    def test_windows_output_writes_csv_and_printable_html(self):
        rows = [("GrillFlow", "Report"), ("Product", "=1+1"), ("Sale", "<unsafe>")]
        write_report(self.directory, rows)
        (exported,) = (self.directory / "reports").glob("*.csv")
        self.assertIn("'=1+1", exported.read_text(encoding="utf-8-sig"))
        with patch("report_output.webbrowser.open", return_value=True) as browser:
            write_report(self.directory, rows, print_report=True)
        (printed,) = (self.directory / "reports").glob("*.html")
        browser.assert_called_once_with(printed.resolve().as_uri())
        self.assertIn("&lt;unsafe&gt;", printed.read_text(encoding="utf-8"))
