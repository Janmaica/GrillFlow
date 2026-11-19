import sqlite3
from dataclasses import dataclass

from kivy.logger import Logger
from kivy.metrics import dp, sp
from kivy.uix.anchorlayout import AnchorLayout
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.screenmanager import Screen
from kivy.uix.scrollview import ScrollView

from order_store import CREDIT, PAID, PARTIAL, can_move_to_credit, customer_name, parse_payment_amount
from product_store import format_price
from receipt_data import display_payment_status
from screens.dashboard_screen import (
    AMOUNT, BORDER, CREAM, INK, MUTED, ORANGE, WHITE, BottomSheet, Icon, IconButton,
    build_navigation, label, paint_header_gradient, paint_surface, wrapping_label,
)
from screens.new_order_screen import _Action, _text_field


PEACH = (1, .91, .80, 1)
ACTIVE_ORANGE = (0.78, 0.26, 0.05, 1)
PICKUP_GREEN = (0.20, 0.55, 0.19, 1)
UNPAID_RED = (0.80, 0.20, 0.14, 1)
GREEN_PILL = ((.87, .97, .84, 1), (.11, .38, .12, 1))
RED_PILL = ((1, .89, .87, 1), (.62, .13, .11, 1))
ORANGE_PILL = (PEACH, AMOUNT)
PAYMENT_PILLS = {PAID: GREEN_PILL, PARTIAL: ORANGE_PILL, CREDIT: RED_PILL}


@dataclass(frozen=True)
class OrderSummary:
    active: int = 0
    ready: int = 0
    customers_with_utang: int = 0


@dataclass(frozen=True)
class OrderPreview:
    order_id: str
    customer_name: str
    total_centavos: int
    preparation_status: str
    saved_id: int | None = None
    payment_status: str = CREDIT
    payment_arrangement: str | None = None

    @property
    def order_status(self):
        return "Done" if self.preparation_status == "Ready" else self.preparation_status


class _QuickAction(ButtonBehavior, BoxLayout):
    def __init__(self, title, subtitle, icon, *, primary=False, **kwargs):
        super().__init__(orientation="vertical", padding=(dp(8), dp(9)), spacing=dp(3), **kwargs)
        if primary:
            paint_header_gradient(self, radius=15)
        else:
            paint_surface(self, WHITE, radius=15, border=BORDER)

        holder = AnchorLayout()
        badge = AnchorLayout(size_hint=(None, None), size=(dp(39), dp(39)))
        paint_surface(badge, (1, .79, .57, .30) if primary else PEACH, radius=20)
        badge.add_widget(Icon(icon, WHITE if primary else ORANGE,
                              size_hint=(None, None), size=(dp(24), dp(24))))
        holder.add_widget(badge)
        self.add_widget(holder)
        self.add_widget(label(title, 16, WHITE if primary else INK, bold=True, align="center",
                              size_hint_y=None, height=dp(22)))
        self.add_widget(label(subtitle, 12, WHITE if primary else MUTED, align="center",
                              size_hint_y=None, height=dp(18)))


class _SummaryRow(BoxLayout):
    def __init__(self, title, icon, color, *, icon_color=ORANGE, **kwargs):
        super().__init__(size_hint_y=None, height=dp(49), spacing=dp(10),
                         padding=(dp(9), 0), **kwargs)
        paint_surface(self, WHITE, radius=13, border=BORDER)

        icon_holder = AnchorLayout(size_hint_x=None, width=dp(33))
        badge = AnchorLayout(size_hint=(None, None), size=(dp(32), dp(32)))
        paint_surface(badge, PEACH, radius=16)
        badge.add_widget(Icon(icon, icon_color, size_hint=(None, None), size=(dp(19), dp(19))))
        icon_holder.add_widget(badge)
        self.add_widget(icon_holder)
        self.add_widget(label(title, 15, bold=True))

        count_holder = AnchorLayout(size_hint_x=None, width=dp(32))
        self.count = label("", 13, WHITE, bold=True, align="center",
                           size_hint=(None, None), width=dp(30), height=dp(30), shorten=True)
        paint_surface(self.count, color, radius=15)
        count_holder.add_widget(self.count)
        self.add_widget(count_holder)


class OrderCard(ButtonBehavior, BoxLayout):
    def __init__(self, order, **kwargs):
        super().__init__(orientation="vertical", size_hint_y=None, height=dp(120), spacing=dp(3),
                         padding=(dp(12), dp(7)), **kwargs)
        paint_surface(self, WHITE, radius=12, border=BORDER)
        details = BoxLayout(spacing=dp(8))
        customer = BoxLayout(orientation="vertical")
        customer.add_widget(label(order.customer_name, 17, bold=True, shorten=True))
        customer.add_widget(label(order.order_id, 12, MUTED, shorten=True))
        details.add_widget(customer)
        amount = AnchorLayout(anchor_y="top", size_hint_x=.74)
        amount.add_widget(label(format_price(order.total_centavos), 15, bold=True,
                                align="right", shorten=True, size_hint_y=None, height=dp(22)))
        details.add_widget(amount)
        arrow = AnchorLayout(anchor_y="top", size_hint_x=None, width=dp(36))
        self.receipt_button = IconButton("chevron", ORANGE, 18, size_hint_y=None, height=dp(34))
        arrow.add_widget(self.receipt_button)
        details.add_widget(arrow)
        self.add_widget(details)

        statuses = BoxLayout(size_hint_y=None, height=dp(59), spacing=dp(8))
        preparation_colors = GREEN_PILL if order.order_status in ("Done", "Received") else ORANGE_PILL
        self.order_selector = self._status_control(
            statuses, "Order Status", order.order_status, preparation_colors,
        )
        self.payment_selector = self._status_control(
            statuses, "Payment Status", display_payment_status(order.payment_status, order.payment_arrangement),
            PAYMENT_PILLS[order.payment_status],
        )
        self.add_widget(statuses)

    @staticmethod
    def _status_control(parent, caption, status, colors):
        column = BoxLayout(orientation="vertical", spacing=dp(1))
        column.add_widget(label(caption, 11, MUTED, align="center", size_hint_y=None, height=dp(17)))
        pill = Button(
            text=f"{status}  v", color=colors[1], font_size=sp(13), bold=True,
            background_normal="", background_down="", background_color=(0, 0, 0, 0),
        )
        paint_surface(pill, colors[0], radius=16)
        column.add_widget(pill)
        parent.add_widget(column)
        return pill


class SalesScreen(Screen):
    def __init__(self, orders, **kwargs):
        super().__init__(**kwargs)
        self.orders = orders
        self.sheet = None
        shell = BoxLayout(orientation="vertical")
        paint_surface(shell, CREAM)
        shell.add_widget(self._build_header())

        scroll = ScrollView(do_scroll_x=False, bar_width=dp(3))
        content = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(9),
                            padding=(dp(12), dp(11), dp(12), dp(10)))
        content.bind(minimum_height=content.setter("height"))
        content.add_widget(self._build_quick_actions())

        self.summary_rows = {
            "active": _SummaryRow("Active Orders", "receipt", ACTIVE_ORANGE),
            "ready": _SummaryRow("Ready for Pickup", "box", PICKUP_GREEN),
            "customers_with_utang": _SummaryRow("Customers With Utang", "credit", UNPAID_RED, icon_color=UNPAID_RED),
        }
        for row in self.summary_rows.values():
            content.add_widget(row)
        content.add_widget(self._build_recent_header())
        self.recent_orders = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(8))
        self.recent_orders.bind(minimum_height=self.recent_orders.setter("height"))
        content.add_widget(self.recent_orders)
        self.show_orders(OrderSummary(), ())

        scroll.add_widget(content)
        shell.add_widget(scroll)
        navigation, self.tabs = build_navigation(self, "Sales", self._show_sheet)
        shell.add_widget(navigation)
        self.add_widget(shell)

    def _build_header(self):
        header = BoxLayout(size_hint_y=None, height=dp(57), spacing=dp(5),
                           padding=(dp(5), 0, dp(12), 0))
        paint_header_gradient(header)
        self.back_button = IconButton("back", WHITE, 22, size_hint_x=None, width=dp(44))
        self.back_button.bind(on_release=self._go_home)
        header.add_widget(self.back_button)
        header.add_widget(label("Sales", 23, WHITE, bold=True))
        return header

    def _build_quick_actions(self):
        actions = BoxLayout(size_hint_y=None, height=dp(109), spacing=dp(10))
        self.new_order = _QuickAction("New Order", "(Create a Sale)", "plus", primary=True)
        self.order_history = _QuickAction("Order History", "(Saved Orders)", "receipt")
        self.new_order.bind(on_release=self._open_new_order)
        self.order_history.bind(on_release=self._open_history)
        actions.add_widget(self.new_order)
        actions.add_widget(self.order_history)
        return actions

    def _build_recent_header(self):
        header = BoxLayout(size_hint_y=None, height=dp(44), padding=(dp(2), 0))
        header.add_widget(label("Recent Orders", 17, bold=True))
        self.view_all = Button(
            text="View All >", color=ACTIVE_ORANGE, font_size=sp(14), bold=True,
            background_normal="", background_down="", background_color=(0, 0, 0, 0),
            size_hint_x=None, width=dp(82),
        )
        self.view_all.bind(on_release=self._open_history)
        header.add_widget(self.view_all)
        return header

    def show_orders(self, summary, orders):
        for key, row in self.summary_rows.items():
            row.count.text = str(getattr(summary, key))
        self.recent_orders.clear_widgets()
        for order in orders:
            card = OrderCard(order)
            if order.saved_id is not None:
                card.bind(on_release=lambda _, order_id=order.saved_id: self._open_receipt(order_id))
                card.receipt_button.bind(on_release=lambda _, order_id=order.saved_id: self._open_receipt(order_id))
                card.order_selector.bind(on_release=lambda _, order=order: self._select_preparation(order))
                card.payment_selector.bind(on_release=lambda _, order=order: self._select_payment(order))
            self.recent_orders.add_widget(card)
        if not self.recent_orders.children:
            empty = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(6),
                              padding=(dp(20), dp(18)))
            empty.bind(minimum_height=empty.setter("height"))
            empty.add_widget(wrapping_label("No Orders Yet", 18, bold=True, align="center"))
            empty.add_widget(wrapping_label(
                "Your latest orders will appear here once you start recording sales.",
                14, MUTED, align="center",
            ))
            self.recent_orders.add_widget(empty)

    def on_pre_enter(self, *_):
        try:
            self.orders.initialize()
        except (OSError, sqlite3.Error) as error:
            Logger.warning("Sales: Could not initialize orders: %s", error)
            return
        self._refresh_orders()

    def _refresh_orders(self):
        try:
            summary, recent = self.orders.sales_summary()
        except (OSError, sqlite3.Error) as error:
            Logger.warning("Sales: Could not load orders: %s", error)
            return
        self.show_orders(OrderSummary(**summary), (OrderPreview(**order) for order in recent))

    def _select_preparation(self, order):
        if order.preparation_status == "Received":
            self._show_sheet("Order Status", "This order has already been received.")
            return
        sheet = self._show_sheet("Order Status", f"{order.order_id} · Current: {order.order_status}")
        for status in ("Pending", "Done"):
            self._sheet_option(sheet, status, order.order_status,
                               lambda status=status: self._save_preparation(order, status))

    def _save_preparation(self, order, status):
        try:
            self.orders.set_preparation(order.saved_id, status)
        except ValueError as error:
            self._show_sheet("Order Status", str(error))
            return
        except (OSError, sqlite3.Error) as error:
            Logger.warning("Sales: Could not update preparation: %s", error)
            self._show_sheet("Order Status", "Could not save the status. Try again.")
            return
        self.sheet.dismiss()
        self._refresh_orders()

    def _select_payment(self, order):
        self.open_payment(order.saved_id, order.order_id)

    def open_payment(self, order_id, order_number, *, host=None):
        host = host or self
        try:
            receipt = self.orders.get_receipt(order_id)
        except (OSError, sqlite3.Error) as error:
            Logger.warning("Sales: Could not load payment history: %s", error)
            receipt = None
        if receipt is None:
            host._show_sheet("Payment Status", "Could not load payment history. Try again.")
            return
        sheet = host._show_sheet(
            "Payment Status",
            f"{order_number} · {receipt.payment_label}\nRemaining: {format_price(receipt.balance)}",
        )
        for status in (PAID, PARTIAL, CREDIT):
            self._sheet_option(sheet, status, receipt.payment_label,
                               lambda status=status: self._payment_choice(order_id, receipt, status, host))
        if can_move_to_credit(receipt.payment_arrangement, receipt.applied, receipt.total):
            self._sheet_option(sheet, "Move to Credit (Utang)", None,
                               lambda: self._confirm_credit_transfer(order_id, receipt, host))

    def _confirm_credit_transfer(self, order_id, receipt, host):
        sheet = host._show_sheet(
            "Move to Credit (Utang)?",
            f"Customer: {receipt.customer_name}\nOrder: {receipt.order_number}\n"
            f"Original Total: {format_price(receipt.total)}\n"
            f"Already Paid: {format_price(receipt.applied)}\n"
            f"Remaining Balance: {format_price(receipt.balance)}\n\n"
            "The remaining balance will be transferred to the customer's Utang account. "
            "Previous payments will be preserved.",
            confirmation="Cancel",
        )
        name_input = None
        if not customer_name(receipt.customer_name):
            sheet.copy.add_widget(wrapping_label("Enter the customer's real name.", 14))
            field, name_input = _text_field("Customer name")
            sheet.copy.add_widget(field)
        error = wrapping_label("", 13, AMOUNT)
        error.height = 0
        sheet.copy.add_widget(error)
        confirm = _Action("Confirm Transfer", primary=True, size_hint_y=None, height=dp(44))
        sheet.copy.add_widget(confirm)

        def submit(*_):
            if confirm.disabled or sheet.parent is None:
                return
            confirm.disabled = True
            try:
                self.orders.move_to_credit(
                    order_id, expected_paid=receipt.applied,
                    replacement_customer=name_input.text if name_input is not None else "",
                )
            except ValueError as failure:
                error.text = str(failure)
            except (OSError, sqlite3.Error) as failure:
                Logger.warning("Sales: Could not move order to credit: %s", failure)
                error.text = "Could not move the order to Utang. Try again."
            else:
                if name_input is not None:
                    name_input.focus = False
                sheet.dismiss()
                self._refresh_orders()
                self.manager.get_screen("order_history")._refresh()
                self.manager.get_screen("utang")._refresh()
                return
            confirm.disabled = False

        confirm.bind(on_release=submit)

    @staticmethod
    def _sheet_option(sheet, status, current, action):
        text = f"{status} (Current)" if status == current else status
        button = _Action(text, primary=status == current, size_hint_y=None, height=dp(44))
        button.bind(on_release=lambda *_: action())
        sheet.copy.add_widget(button)

    def _payment_choice(self, order_id, receipt, status, host):
        if status == CREDIT or not receipt.balance:
            if status == receipt.status:
                host.sheet.dismiss()
            else:
                host._show_sheet("Payment Status",
                                 "A payment has already been recorded. Refunds and reversals are unavailable.")
            return

        sheet = host._show_sheet(
            "Record Payment",
            f"{receipt.order_number}\nAlready paid: {format_price(receipt.applied)}"
            f"\nRemaining: {format_price(receipt.balance)}",
        )
        hint = ("Cash tendered (₱)" if status == PAID else "Additional partial payment (₱)")
        field, amount = _text_field(hint)
        if status == PAID:
            pesos, cents = divmod(receipt.balance, 100)
            amount.text = f"{pesos}.{cents:02d}"
        sheet.copy.add_widget(field)
        error = wrapping_label("", 13, AMOUNT)
        error.height = 0
        sheet.copy.add_widget(error)
        save = _Action("Record Payment", primary=True, size_hint_y=None, height=dp(44))
        sheet.copy.add_widget(save)

        def submit(*_):
            if save.disabled or sheet.parent is None:
                return
            save.disabled = True
            amount.focus = False
            try:
                self.orders.record_payment(
                    order_id, status, parse_payment_amount(amount.text), expected_paid=receipt.applied,
                )
            except ValueError as failure:
                error.text = str(failure)
            except (OSError, sqlite3.Error) as failure:
                Logger.warning("Sales: Could not record payment: %s", failure)
                error.text = "Could not record payment. Try again."
            else:
                sheet.dismiss()
                self._refresh_orders()
                if host is not self:
                    host._refresh()
                return
            save.disabled = False

        save.bind(on_release=submit)

    def _open_receipt(self, order_id):
        self.manager.get_screen("receipt").open_order(order_id)

    def _go_home(self, *_):
        self.manager.current = "dashboard"

    def _open_new_order(self, *_):
        self.manager.current = "new_order"

    def _open_history(self, *_):
        self.manager.current = "order_history"

    def _show_sheet(self, title, message, *, confirmation="Close"):
        if self.sheet and self.sheet.parent:
            self.sheet.dismiss()
        self.sheet = BottomSheet(title, message, confirmation=confirmation)
        self.add_widget(self.sheet)
        return self.sheet
