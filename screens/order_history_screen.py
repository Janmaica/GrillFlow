import sqlite3
from datetime import datetime, timezone

from kivy.logger import Logger
from kivy.metrics import dp, sp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.screenmanager import Screen
from kivy.uix.scrollview import ScrollView
from kivy.uix.spinner import Spinner

from order_store import HISTORY_BALANCE_MESSAGE, HISTORY_PERIODS, PHILIPPINE_TIME, OutstandingBalanceError, history_bounds
from product_store import format_price
from receipt_data import display_payment_status
from screens.add_product_screen import _UnitOption
from screens.dashboard_screen import (
    AMOUNT, BORDER, CREAM, INK, MUTED, ORANGE, WHITE, BottomSheet, IconButton, label,
    paint_header_gradient, paint_surface, wrapping_label,
)
from screens.new_order_screen import _Action, _vertical
from screens.sales_screen import GREEN_PILL, ORANGE_PILL, PAYMENT_PILLS, UNPAID_RED


def _history_card(order, open_receipt, confirm_delete, open_payment):
    card = _vertical(spacing=dp(6), padding=dp(10))
    paint_surface(card, WHITE, radius=12, border=BORDER)
    details = BoxLayout(size_hint_y=None, spacing=dp(4))
    copy = _vertical(spacing=dp(2))
    copy.add_widget(wrapping_label(order["customer_name"], 16, bold=True))
    copy.add_widget(wrapping_label(order["order_number"], 13, MUTED))
    date = datetime.fromisoformat(order["created_at"]).replace(tzinfo=timezone.utc)
    copy.add_widget(wrapping_label(date.astimezone(PHILIPPINE_TIME).strftime("%b %d, %Y · %I:%M %p"), 12, MUTED))
    copy.add_widget(wrapping_label(format_price(order["total_centavos"]), 15, AMOUNT, bold=True))
    copy.bind(height=lambda _, height: setattr(details, "height", max(dp(44), height)))
    details.add_widget(copy)
    for icon, color, action in (("delete", UNPAID_RED, confirm_delete), ("chevron", ORANGE, open_receipt)):
        if action is None:
            continue
        button = IconButton(icon, color, 18, size_hint_x=None, width=dp(44))
        button.bind(on_release=lambda _, action=action: action(order))
        details.add_widget(button)
    card.add_widget(details)

    badges = BoxLayout(size_hint_y=None, height=dp(28), spacing=dp(6))
    prep = order["preparation_status"]
    prep_colors = GREEN_PILL if prep in ("Ready", "Received") else ORANGE_PILL
    for title, (fill, ink) in (
        ("Done" if prep == "Ready" else prep, prep_colors),
        (display_payment_status(order["payment_status"], order["payment_arrangement"]),
         PAYMENT_PILLS[order["payment_status"]]),
    ):
        badge = label(title, 12, ink, bold=True, align="center")
        paint_surface(badge, fill, radius=12)
        badges.add_widget(badge)
    card.add_widget(badges)
    if order["outstanding_balance_centavos"] > 0:
        balance = format_price(order["outstanding_balance_centavos"])
        card.add_widget(wrapping_label(f"Remaining Balance: {balance}", 13, AMOUNT, bold=True))
        pay = _Action("Record Payment", size_hint_y=None, height=dp(42))
        pay.bind(on_release=lambda *_: open_payment(order))
        card.add_widget(pay)
    return card


class OrderHistoryScreen(Screen):
    def __init__(self, orders, **kwargs):
        super().__init__(**kwargs)
        self.orders = orders
        self.rows = []
        self.sheet = None
        self.bounds = None

        shell = BoxLayout(orientation="vertical")
        paint_surface(shell, CREAM)
        header = BoxLayout(size_hint_y=None, height=dp(57), spacing=dp(5), padding=(dp(5), 0, dp(12), 0))
        paint_header_gradient(header)
        self.back_button = IconButton("back", WHITE, 22, size_hint_x=None, width=dp(44))
        self.back_button.bind(on_release=self._go_back)
        header.add_widget(self.back_button)
        header.add_widget(label("Order History", 23, WHITE, bold=True))
        shell.add_widget(header)

        body = BoxLayout(orientation="vertical", padding=dp(12), spacing=dp(8))
        self.period = Spinner(
            text=HISTORY_PERIODS[0], values=HISTORY_PERIODS, option_cls=_UnitOption, color=INK,
            font_size=sp(15), size_hint_y=None, height=dp(44), background_normal="",
            background_down="", background_color=(0, 0, 0, 0),
        )
        paint_surface(self.period, WHITE, radius=12, border=BORDER)
        body.add_widget(self.period)
        self.summary = BoxLayout(size_hint_y=None, height=dp(54), padding=(dp(10), 0), spacing=dp(7))
        paint_surface(self.summary, WHITE, radius=12, border=BORDER)
        self.count_label = label("", 14, bold=True)
        self.sales_label = label("", 14, AMOUNT, bold=True, align="right")
        self.summary.add_widget(self.count_label)
        self.summary.add_widget(self.sales_label)
        body.add_widget(self.summary)
        actions = BoxLayout(size_hint_y=None, height=dp(44))
        actions.add_widget(label("Orders", 18, bold=True))
        self.clear_button = _Action("Clear All", size_hint_x=None, width=dp(94))
        self.clear_button.disabled = True
        self.clear_button.bind(on_release=self._confirm_clear)
        actions.add_widget(self.clear_button)
        body.add_widget(actions)
        self.notice = wrapping_label("", 13, AMOUNT)
        self.notice.height = 0
        body.add_widget(self.notice)
        scroll = ScrollView(do_scroll_x=False, bar_width=dp(3))
        self.list = _vertical(spacing=dp(8), padding=(dp(1), dp(2)))
        scroll.add_widget(self.list)
        body.add_widget(scroll)
        shell.add_widget(body)
        self.add_widget(shell)
        self.period.bind(text=self._change_period)

    def on_pre_enter(self, *_):
        self._refresh()

    def on_pre_leave(self, *_):
        self.period.is_open = False
        if self.sheet:
            self.sheet.dismiss()

    def _change_period(self, *_):
        self._set_notice("")
        self._refresh()

    def _set_notice(self, message):
        self.notice.text = message
        if not message:
            self.notice.height = 0

    def _refresh(self):
        self.bounds = history_bounds(self.period.text)
        self.list.clear_widgets()
        try:
            self.rows = self.orders.history(*self.bounds)
        except (OSError, sqlite3.Error) as error:
            Logger.warning("History: Could not load orders: %s", error)
            self.rows = []
            self.count_label.text = self.sales_label.text = ""
            self.clear_button.disabled = True
            self._set_notice("Could not load order history. Return to Sales and try again.")
            return
        self.count_label.text = f"{len(self.rows)} {'order' if len(self.rows) == 1 else 'orders'}"
        self.sales_label.text = f"Total sales\n{format_price(sum(order['total_centavos'] for order in self.rows))}"
        self.clear_button.disabled = not self.rows
        for order in self.rows:
            self.list.add_widget(_history_card(
                order, self._open_receipt, self._confirm_delete, self._open_payment,
            ))
        if not self.rows:
            self.list.add_widget(wrapping_label("No orders for this period.", 15, MUTED, align="center"))

    def _open_receipt(self, order):
        self.manager.get_screen("receipt").open_order(order["id"], return_screen=self.name)

    def _go_back(self, *_):
        self.manager.current = "sales"

    def _open_payment(self, order):
        self.manager.get_screen("sales").open_payment(order["id"], order["order_number"], host=self)

    def _confirm_delete(self, order):
        if order["outstanding_balance_centavos"] > 0:
            self._show_sheet("Cannot Delete Order",
                             "This order still has an unpaid balance. Settle it before deleting.",
                             confirmation="OK")
            return
        self._confirm(
            "Permanently Delete?",
            "This action will permanently remove the selected record from GrillFlow. It cannot be undone.\n\n"
            f"{order['order_number']} · {order['customer_name']}\n"
            "Its payment history and recorded revenue will also be removed.",
            "Delete Permanently", lambda: self.orders.delete_order(order["id"]),
            "Order permanently deleted.",
        )

    def _confirm_clear(self, *_):
        if not self.rows:
            return
        if any(order["outstanding_balance_centavos"] > 0 for order in self.rows):
            self._show_sheet("Cannot Clear History", HISTORY_BALANCE_MESSAGE, confirmation="OK")
            return
        bounds = self.bounds
        ids = frozenset(order["id"] for order in self.rows)
        self._confirm(
            "Permanently Clear History?",
            f"This will permanently delete {len(ids)} orders and their associated payment records. "
            f"This action cannot be undone.\n\nPeriod: {self.period.text}",
            "Clear Permanently", lambda: self.orders.delete_history(*bounds, ids),
            "Selected orders permanently deleted.",
        )

    def _show_sheet(self, title, message, *, confirmation="Close"):
        if self.sheet:
            self.sheet.dismiss()
        self.sheet = BottomSheet(title, message, confirmation=confirmation)
        self.add_widget(self.sheet)
        return self.sheet

    def _confirm(self, title, message, action_label, action, success):
        sheet = self._show_sheet(title, message, confirmation="Cancel")
        confirm = _Action(action_label, primary=True, size_hint_y=None, height=dp(44))
        sheet.copy.add_widget(confirm)
        self.sheet = sheet

        def submit(*_):
            if confirm.disabled or sheet.parent is None:
                return
            confirm.disabled = sheet.confirm_button.disabled = True
            try:
                changed = action()
            except OutstandingBalanceError as error:
                self._refresh()
                self._show_sheet("Cannot Clear History" if action_label == "Clear Permanently" else "Cannot Delete Order",
                                 str(error), confirmation="OK")
                return
            except ValueError as error:
                notice = str(error)
            except (OSError, sqlite3.Error) as error:
                Logger.warning("History: Permanent deletion failed: %s", error)
                notice = "Could not update order history. Try again."
            else:
                notice = success if changed else "Order is already absent from history."
            sheet.dismiss()
            self._set_notice(notice)
            self._refresh()
            self.manager.get_screen("sales")._refresh_orders()
            self.manager.get_screen("dashboard").refresh_financials()

        confirm.bind(on_release=submit)


