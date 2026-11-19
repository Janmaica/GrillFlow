import sqlite3
from datetime import datetime, timedelta, timezone

from kivy.logger import Logger
from kivy.metrics import dp, sp
from kivy.uix.anchorlayout import AnchorLayout
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.screenmanager import Screen
from kivy.uix.scrollview import ScrollView
from kivy.uix.spinner import Spinner
from kivy.utils import platform

from order_store import PHILIPPINE_TIME, report_bounds
from product_photos import product_photo_path
from product_store import format_price
from report_chart_data import CHART_TITLES, chart_buckets
from report_output import write_report
from screens.add_product_screen import ProductImage, _UnitOption
from screens.dashboard_screen import (
    AMOUNT, BORDER, CREAM, INK, MUTED, ORANGE, WHITE, BottomSheet, IconButton,
    build_navigation, label, paint_header_gradient, paint_surface, wrapping_label,
)
from screens.new_order_screen import _Action, _card, _vertical
from screens.report_chart import ReportChart


PERIODS = ("This Day", "This Week", "This Month")
SALES_TAB, PRODUCT_TAB = "Sales Report", "Product Report"
EMPTY_PRODUCTS = "No product sales available for this period."


class ReportsScreen(Screen):
    def __init__(self, orders, expenses, **kwargs):
        super().__init__(**kwargs)
        self.orders = orders
        self.expenses = expenses
        self.tab = SALES_TAB
        self.sheet = None
        self.totals, self.series, self.ranking, self.inventory = (0, 0, 0, 0), [], [], []
        self.expense_total = 0
        self.loaded = False

        shell = BoxLayout(orientation="vertical")
        paint_surface(shell, CREAM)
        header = BoxLayout(size_hint_y=None, height=dp(57), spacing=dp(5), padding=(dp(5), 0, dp(12), 0))
        paint_header_gradient(header)
        back = IconButton("back", WHITE, 22, size_hint_x=None, width=dp(44))
        back.bind(on_release=self._go_home)
        header.add_widget(back)
        header.add_widget(label("Reports", 23, WHITE, bold=True))
        shell.add_widget(header)
        shell.add_widget(self._controls())

        self.scroll = ScrollView(do_scroll_x=False, bar_width=dp(3))
        self.content = _vertical(spacing=dp(10), padding=(dp(12), dp(7), dp(12), dp(12)))
        self.scroll.add_widget(self.content)
        shell.add_widget(self.scroll)
        navigation, self.tabs = build_navigation(self, "Reports", self._show_sheet)
        shell.add_widget(navigation)
        self.add_widget(shell)

    def _controls(self):
        controls = _vertical(spacing=dp(7), padding=(dp(12), dp(9), dp(12), dp(2)))
        self.report_tab_row = BoxLayout(size_hint_y=None, height=dp(42), spacing=dp(7))
        self._render_tabs()
        controls.add_widget(self.report_tab_row)
        dates = BoxLayout(size_hint_y=None, height=dp(42), spacing=dp(7))
        self.period = Spinner(
            text=PERIODS[0], values=PERIODS, option_cls=_UnitOption, font_size=sp(14), color=AMOUNT,
            bold=True, size_hint_x=None, width=dp(113), background_normal="", background_down="",
            background_color=(0, 0, 0, 0),
        )
        paint_surface(self.period, WHITE, radius=11, border=BORDER)
        self.period.bind(text=lambda *_: self._refresh())
        dates.add_widget(self.period)
        self.range_label = label("", 12, MUTED, align="right")
        dates.add_widget(self.range_label)
        controls.add_widget(dates)
        return controls

    def on_pre_enter(self, *_):
        self._refresh()

    def on_pre_leave(self, *_):
        self.period.is_open = False
        if self.sheet:
            self.sheet.dismiss()

    def _select_tab(self, tab):
        self.tab = tab
        self._render_tabs()
        self._refresh()

    def _render_tabs(self):
        self.report_tab_row.clear_widgets()
        for title in (SALES_TAB, PRODUCT_TAB):
            button = _Action(title, primary=title == self.tab)
            button.bind(on_release=lambda _, title=title: self._select_tab(title))
            self.report_tab_row.add_widget(button)

    def _refresh(self):
        bounds = report_bounds(self.period.text)
        local = [datetime.fromisoformat(value).replace(tzinfo=timezone.utc).astimezone(PHILIPPINE_TIME)
                 for value in bounds]
        first, last = local[0].date(), local[1].date() - timedelta(days=1)
        start_label = first.strftime("%b %d, %Y" if first.year != last.year else "%b %d")
        self.range_label.text = f"{last:%b %d, %Y}" if first == last else f"{start_label} – {last:%b %d, %Y}"
        self.content.clear_widgets()
        self.scroll.scroll_y = 1
        try:
            self.totals = self.orders.report_summary(*bounds)
            self.expense_total = self.expenses.total(*bounds)
            self.series = self.orders.sales_trend(*bounds, hourly=self.period.text == "This Day")
            self.ranking = self.orders.ranked_products(*bounds)
            self.inventory = self.orders.products.list_products()
        except (OSError, sqlite3.Error) as error:
            Logger.warning("Reports: Could not load data: %s", error)
            self.loaded = False
            self.content.add_widget(wrapping_label("Could not load reports. Return to Reports to try again.", 14, AMOUNT))
            return
        self.loaded = True
        if self.tab == SALES_TAB:
            self.content.add_widget(self._summary_cards())
            trend = _card()
            trend.add_widget(wrapping_label(CHART_TITLES[self.period.text][0], 17, bold=True))
            chart = ReportChart(chart_buckets(self.series, self.period.text, bounds[0]), self.period.text,
                                self._show_bar, size_hint_y=None, height=dp(178))
            trend.add_widget(chart)
            self.content.add_widget(trend)
            self.content.add_widget(self._rank_section("Top Selling Products", self.ranking[:3], view_all=True))
        else:
            self.content.add_widget(self._rank_section("Products Sold", self.ranking))
            self.content.add_widget(self._inventory_section())
        actions = BoxLayout(size_hint_y=None, height=dp(46), spacing=dp(8))
        for text, printer in (("Export Report", False), ("Print Report", True)):
            action = _Action(text, primary=printer)
            action.bind(on_release=lambda _, printer=printer: self._output(printer))
            actions.add_widget(action)
        self.content.add_widget(actions)

    def _summary_entries(self):
        sales, cash, credit, count = self.totals
        return (("Total Sales", format_price(sales)), ("Orders", str(count)),
                ("Cash Collected", format_price(cash)), ("Outstanding Credit", format_price(credit)),
                ("Expenses", format_price(self.expense_total)))

    def _summary_cards(self):
        grid = GridLayout(cols=2, size_hint_y=None, spacing=dp(8), row_default_height=dp(78),
                          row_force_default=True)
        grid.bind(minimum_height=grid.setter("height"))
        for title, value in self._summary_entries():
            card = BoxLayout(orientation="vertical", padding=(dp(10), dp(7)), spacing=dp(2))
            paint_surface(card, WHITE, radius=12, border=BORDER)
            card.add_widget(label(title, 13, INK, bold=True))
            card.add_widget(label(value, 21, AMOUNT, bold=True, shorten=True))
            if title == "Outstanding Credit":
                card.add_widget(label("Orders from this period", 10, MUTED, size_hint_y=None, height=dp(12)))
            grid.add_widget(card)
        return grid

    def _rank_section(self, title, products, *, view_all=False):
        section = _card()
        heading = BoxLayout(size_hint_y=None, height=dp(40))
        heading.add_widget(label(title, 17, bold=True))
        if view_all and products:
            view = _Action("View All", size_hint_x=None, width=dp(82), font=12)
            view.bind(on_release=self._view_all)
            heading.add_widget(view)
        section.add_widget(heading)
        if not products:
            section.add_widget(wrapping_label(EMPTY_PRODUCTS, 14, MUTED))
        for index, (name, unit, quantity, revenue, photo) in enumerate(products, 1):
            row = BoxLayout(size_hint_y=None, spacing=dp(7))
            row.add_widget(label(str(index), 14, AMOUNT, bold=True, align="center",
                                 size_hint_x=None, width=dp(23)))
            holder = AnchorLayout(size_hint_x=None, width=dp(47))
            holder.add_widget(ProductImage(
                source=str(product_photo_path(self.orders.products.data_dir, photo)),
                size_hint=(None, None), size=(dp(44), dp(44)),
            ))
            row.add_widget(holder)
            copy = _vertical(spacing=dp(2))
            copy.add_widget(wrapping_label(name, 14, bold=True))
            copy.add_widget(wrapping_label(f"{quantity:,} sold · {unit}", 12, MUTED))
            copy.add_widget(wrapping_label(format_price(revenue), 13, AMOUNT, bold=True))
            copy.bind(height=lambda _, height, row=row: setattr(row, "height", max(dp(51), height)))
            row.add_widget(copy)
            section.add_widget(row)
        return section

    def _inventory_section(self):
        section = _card()
        out = sum(product["stock"] == 0 for product in self.inventory)
        section.add_widget(wrapping_label("Current Inventory", 17, bold=True))
        section.add_widget(wrapping_label(f"{len(self.inventory)} active products · {out} out of stock", 13, MUTED))
        for product in self.inventory:
            stock = f'{product["stock"]:,} available' if product["stock"] else "Out of stock"
            section.add_widget(wrapping_label(f'{product["name"]} · {stock} · {product["unit"]}', 14))
        return section

    def _view_all(self, *_):
        self._show_sheet("Top Selling Products", self.range_label.text)
        self.sheet.copy.add_widget(self._rank_section("Ranked Products", self.ranking))

    def _show_bar(self, period, amount):
        self._show_sheet(period, f"Total Sales: {format_price(amount)}")

    def _output(self, printer):
        title = "Print Report" if printer else "Export Report"
        if platform != "win":
            self._show_sheet(title, "Coming Soon")
            return
        if not self.loaded:
            self._show_sheet(title, "Could not load report data.")
            return
        rows = [("GrillFlow", self.tab), (self.period.text, self.range_label.text)]
        if self.tab == SALES_TAB:
            rows.extend(self._summary_entries())
            rows.extend([(), ("Sales Trend", "Sales")])
            rows.extend((period, format_price(value)) for period, value in self.series)
        rows.extend([(), ("Rank", "Product", "Unit", "Quantity Sold", "Revenue")])
        rows.extend((index, name, unit, quantity, format_price(revenue))
                    for index, (name, unit, quantity, revenue, _) in enumerate(self.ranking, 1))
        if self.tab == PRODUCT_TAB:
            rows.extend([(), ("Current Inventory", "Unit", "Stock")])
            rows.extend((product["name"], product["unit"], product["stock"]) for product in self.inventory)
        try:
            message = write_report(self.orders.products.data_dir, rows, print_report=printer)
        except OSError as error:
            Logger.warning("Reports: Could not write report: %s", error)
            message = "Could not generate the report. Check storage access and try again."
        self._show_sheet(title, message)

    def _show_sheet(self, title, message):
        if self.sheet:
            self.sheet.dismiss()
        self.sheet = BottomSheet(title, message)
        self.add_widget(self.sheet)

    def _go_home(self, *_):
        self.manager.current = "dashboard"
