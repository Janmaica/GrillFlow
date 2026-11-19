import sqlite3
from datetime import datetime, timezone

from kivy.logger import Logger
from kivy.graphics import Color, Line
from kivy.metrics import dp, sp
from kivy.uix.anchorlayout import AnchorLayout
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.screenmanager import Screen
from kivy.uix.scrollview import ScrollView
from kivy.uix.spinner import Spinner
from kivy.uix.widget import Widget

from order_store import HISTORY_PERIODS, PHILIPPINE_TIME, history_bounds, parse_payment_amount
from product_store import format_price, normalized_name
from receipt_data import display_payment_status, local_timestamp
from screens.add_product_screen import _UnitOption
from screens.dashboard_screen import (
    AMOUNT, CREAM, INK, MUTED, ORANGE, WHITE, BottomSheet, Icon, IconButton,
    build_navigation, label, paint_header_gradient, paint_surface, wrapping_label,
)
from screens.new_order_screen import _Action, _text_field, _vertical
from screens.sales_screen import GREEN_PILL, ORANGE_PILL


PEACH = (1, .94, .88, 1)
ORANGE_EDGE = (1, .77, .60, 1)
BALANCE_INK = (.57, .13, .09, 1)
ALL_TIME = "All Time"


def _fixed_icon(kind, color=ORANGE, side=20):
    holder = AnchorLayout(size_hint_x=None, width=dp(side + 4))
    holder.add_widget(Icon(kind, color, size_hint=(None, None), size=(dp(side), dp(side))))
    return holder


class _Chevron(Widget):
    def __init__(self, expanded=False, **kwargs):
        super().__init__(size_hint_x=None, width=dp(18), **kwargs)
        with self.canvas:
            Color(*ORANGE)
            line = Line(width=dp(1.2))

        def draw(*_):
            x, y = self.center
            rise = dp(2.5) if expanded else -dp(2.5)
            line.points = (x - dp(5), y - rise, x, y + rise, x + dp(5), y - rise)

        self.bind(pos=draw, size=draw)
        draw()


class _CreditButton(ButtonBehavior, BoxLayout):
    def __init__(self, text, icon, *, primary=False):
        super().__init__(padding=(dp(7), 0), spacing=dp(3))
        color = WHITE if primary else AMOUNT
        paint_surface(self, ORANGE if primary else WHITE, radius=10, border=ORANGE_EDGE)
        self.add_widget(_fixed_icon(icon, color, 16))
        title = wrapping_label(text, 12, color, bold=True, align="center")
        holder = AnchorLayout()
        holder.add_widget(title)
        self.add_widget(holder)


def _stack(texts):
    column = _vertical(spacing=dp(2))
    for text, size, color, bold, align in texts:
        column.add_widget(wrapping_label(text, size, color, bold=bold, align=align))
    return column


def _order_table_row(cells):
    row = BoxLayout(size_hint_y=None, spacing=dp(3))
    widths = (.21, .25, .075, .155, .135, .175)

    def fit(*_):
        row.height = max(cell.height for cell in cells) + dp(3)

    for width, cell in zip(widths, cells):
        cell.size_hint_x = width
        cell.pos_hint = {"top": 1}
        cell.bind(height=fit)
        row.add_widget(cell)
    fit()
    return row


def _order_table(orders):
    table = _vertical(spacing=dp(7), padding=(dp(6), dp(8)))
    paint_surface(table, PEACH, radius=10)
    labels = [wrapping_label(text, 10, AMOUNT, bold=True, align=align) for text, align in (
        ("Order No.", "left"), ("Items", "left"), ("Qty", "center"), ("Total", "right"),
        ("Status", "center"), ("Balance", "right"),
    )]
    table.add_widget(_order_table_row(labels))
    for order in orders:
        stamp = datetime.fromisoformat(order["created_at"]).replace(tzinfo=timezone.utc).astimezone(PHILIPPINE_TIME)
        identity = _stack((
            (order["order_number"], 11, INK, True, "left"),
            (stamp.strftime("%b %d, %Y\n%I:%M %p"), 10, MUTED, False, "left"),
        ))
        items = _vertical(spacing=dp(3))
        quantities = _vertical(spacing=dp(3))
        for name, quantity in order["items"]:
            item = wrapping_label(name, 11)
            qty = label(str(quantity), 11, align="center", size_hint_y=None, height=item.height)
            item.bind(height=qty.setter("height"))
            quantities.add_widget(qty)
            items.add_widget(item)
        prep = order["preparation_status"]
        fill, color = GREEN_PILL if prep in ("Ready", "Received") else ORANGE_PILL
        badge = wrapping_label("Done" if prep == "Ready" else prep, 10, color, bold=True, align="center")
        paint_surface(badge, fill, radius=6)
        status = _vertical(spacing=dp(3))
        status.add_widget(badge)
        status.add_widget(wrapping_label(
            display_payment_status(order["payment_status"], "credit"), 10, AMOUNT, align="center",
        ))
        table.add_widget(_order_table_row((
            identity, items, quantities, wrapping_label(format_price(order["total_centavos"]), 11, align="right"),
            status, wrapping_label(
                format_price(order["outstanding_balance_centavos"]), 11, BALANCE_INK, bold=True, align="right",
            ),
        )))
    return table


class _CustomerHeader(ButtonBehavior, BoxLayout):
    pass


class UtangScreen(Screen):
    def __init__(self, orders, **kwargs):
        super().__init__(**kwargs)
        self.orders = orders
        self.expanded = set()
        self.rows = []
        self.customer_groups = {}
        self.filtered_groups = {}
        self.sheet = None
        self.load_failed = False

        shell = BoxLayout(orientation="vertical")
        paint_surface(shell, CREAM)
        shell.add_widget(self._header())
        scroll = ScrollView(do_scroll_x=False, bar_width=dp(3))
        content = _vertical(spacing=dp(10), padding=(dp(12), dp(11), dp(12), dp(12)))
        summary = BoxLayout(size_hint_y=None, height=dp(87), spacing=dp(8))
        customers, self.customer_count = self._summary_card("Customers with Utang", "person")
        outstanding, self.outstanding = self._summary_card("Total Outstanding", "credit")
        summary.add_widget(customers)
        summary.add_widget(outstanding)
        content.add_widget(summary)
        content.add_widget(self._filters())
        self.cards = _vertical(spacing=dp(9))
        content.add_widget(self.cards)
        note = _vertical(padding=dp(9))
        paint_surface(note, PEACH, radius=10, border=ORANGE_EDGE)
        note_row = BoxLayout(size_hint_y=None, spacing=dp(5))
        note_row.add_widget(_fixed_icon("info"))
        message = wrapping_label(
            "Note: Utang (Credit) are orders given on credit. They will remain here until fully paid.", 12, AMOUNT,
        )
        message.bind(height=lambda _, height: setattr(note_row, "height", max(dp(23), height)))
        note_row.add_widget(message)
        note.add_widget(note_row)
        content.add_widget(note)
        scroll.add_widget(content)
        shell.add_widget(scroll)
        navigation, self.tabs = build_navigation(self, "Utang", self._show_sheet)
        shell.add_widget(navigation)
        self.add_widget(shell)
        self.search.bind(text=lambda *_: self._render())
        self.period.bind(text=lambda *_: self._refresh())
        self._render()

    def _header(self):
        header = BoxLayout(size_hint_y=None, height=dp(83), spacing=dp(5), padding=(dp(5), dp(7), dp(12), dp(7)))
        paint_header_gradient(header)
        back = IconButton("back", WHITE, 22, size_hint_x=None, width=dp(44))
        back.bind(on_release=self._go_home)
        header.add_widget(back)
        copy = BoxLayout(orientation="vertical")
        copy.add_widget(label("Utang (Credit)", 23, WHITE, bold=True, size_hint_y=None, height=dp(33)))
        copy.add_widget(label("List of customers with unpaid or partially paid orders.", 12, WHITE))
        header.add_widget(copy)
        return header

    @staticmethod
    def _summary_card(caption, icon):
        card = BoxLayout(orientation="vertical", padding=(dp(9), dp(8)), spacing=dp(3))
        paint_surface(card, WHITE, radius=13, border=ORANGE_EDGE)
        heading = BoxLayout(size_hint_y=None, height=dp(32), spacing=dp(3))
        heading.add_widget(_fixed_icon(icon))
        heading.add_widget(label(caption, 12, AMOUNT, bold=True))
        card.add_widget(heading)
        value = label("", 20, BALANCE_INK, bold=True, align="center")
        card.add_widget(value)
        return card, value

    def _filters(self):
        row = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(7))
        field, self.search = _text_field("Search customer...")
        search_box = BoxLayout()
        paint_surface(search_box, WHITE, radius=10, border=ORANGE_EDGE)
        search_box.add_widget(_fixed_icon("search"))
        field.remove_widget(self.search)
        search_box.add_widget(self.search)
        row.add_widget(search_box)
        self.period = Spinner(
            text=ALL_TIME, values=(ALL_TIME, *HISTORY_PERIODS), option_cls=_UnitOption,
            font_size=sp(13), color=AMOUNT, bold=True, pos_hint={"x": 0, "y": 0},
            halign="left", valign="middle", padding=(dp(10), 0),
            background_normal="", background_down="", background_color=(0, 0, 0, 0),
        )
        self.period.bind(size=lambda control, size: setattr(control, "text_size", size))
        paint_surface(self.period, WHITE, radius=10, border=ORANGE_EDGE)
        dropdown = FloatLayout(size_hint_x=None, width=dp(100))
        dropdown.add_widget(self.period)
        dropdown.add_widget(_Chevron(pos_hint={"right": .97, "y": 0}))
        row.add_widget(dropdown)
        return row

    def on_pre_enter(self, *_):
        self._refresh(initialize=True)

    def on_pre_leave(self, *_):
        self.search.focus = False
        self.period.is_open = False
        if self.sheet:
            self.sheet.dismiss()

    def _refresh(self, *, initialize=False):
        bounds = None if self.period.text == ALL_TIME else history_bounds(self.period.text)
        try:
            if initialize:
                self.orders.initialize()
            self.customer_groups = self.orders.credit_customer_groups()
            self.load_failed = False
        except (OSError, sqlite3.Error) as error:
            Logger.warning("Utang: Could not load credit orders: %s", error)
            self.customer_groups = {}
            self.load_failed = True
        self.filtered_groups = {}
        for key, orders in self.customer_groups.items():
            visible = orders if bounds is None else [
                order for order in orders if bounds[0] <= order["created_at"] < bounds[1]
            ]
            if visible:
                self.filtered_groups[key] = visible
        self.rows = [order for orders in self.filtered_groups.values() for order in orders]
        self._render()

    def _render(self):
        self.cards.clear_widgets()
        query = normalized_name(self.search.text)
        customers = {key: orders for key, orders in self.filtered_groups.items() if query in key}
        self.customer_count.text = str(len(self.customer_groups))
        self.outstanding.text = format_price(sum(
            order["outstanding_balance_centavos"] for group in self.customer_groups.values() for order in group
        ))
        for key, orders in customers.items():
            self.cards.add_widget(self._customer_card(key, orders))
        if not customers:
            if self.load_failed:
                heading, message = "Could Not Load Utang", "Return to Utang to try again."
            elif self.rows:
                heading, message = "No Matching Customers", "Try a different customer name."
            else:
                heading, message = "No Outstanding Utang", "Customers with unpaid credit will appear here."
            empty = _vertical(padding=dp(14), spacing=dp(5))
            paint_surface(empty, WHITE, radius=12)
            empty.add_widget(wrapping_label(heading, 16, bold=True, align="center"))
            empty.add_widget(wrapping_label(message, 13, MUTED, align="center"))
            self.cards.add_widget(empty)

    def _customer_card(self, key, orders):
        customer = orders[0]["customer_name"]
        balance = sum(order["outstanding_balance_centavos"] for order in orders)
        card = _vertical(padding=dp(8), spacing=dp(8))
        paint_surface(card, WHITE, radius=13, border=ORANGE_EDGE)
        header = _CustomerHeader(size_hint_y=None, height=dp(60), spacing=dp(6))
        avatar_box = AnchorLayout(size_hint_x=None, width=dp(38))
        avatar = label(customer[0].upper(), 16, AMOUNT, bold=True, align="center",
                       size_hint=(None, None), width=dp(36), height=dp(36))
        paint_surface(avatar, PEACH, radius=18)
        avatar_box.add_widget(avatar)
        header.add_widget(avatar_box)
        name = BoxLayout(orientation="vertical")
        name.add_widget(label(customer, 15, bold=True, shorten=True))
        name.add_widget(label(f"{len(orders)} unpaid {'order' if len(orders) == 1 else 'orders'}", 12, MUTED))
        header.add_widget(name)
        totals = BoxLayout(orientation="vertical", size_hint_x=.85)
        totals.add_widget(label(format_price(balance), 16, BALANCE_INK, bold=True, align="right"))
        totals.add_widget(label("Total Balance", 11, MUTED, align="right"))
        header.add_widget(totals)
        header.add_widget(_Chevron(key in self.expanded))
        header.bind(on_release=lambda *_: self._toggle_customer(key))
        card.add_widget(header)
        if key in self.expanded:
            card.add_widget(_order_table(orders))
            actions = BoxLayout(size_hint_y=None, height=dp(43), spacing=dp(7))
            view = _CreditButton("View All Orders", "receipt")
            pay = _CreditButton("Record Payment", "credit", primary=True)
            view.bind(on_release=lambda *_: self._view_customer(key, customer))
            pay.bind(on_release=lambda *_: self._choose_payment(customer, orders))
            actions.add_widget(view)
            actions.add_widget(pay)
            card.add_widget(actions)
        return card

    def _toggle_customer(self, key):
        self.expanded.symmetric_difference_update({key})
        self._render()

    def _view_customer(self, key, customer):
        try:
            orders = self.orders.credit_details(customer_key=key)
        except (OSError, sqlite3.Error) as error:
            Logger.warning("Utang: Could not load customer history: %s", error)
            self._show_sheet(customer, "Could not load credit order history. Try again.")
            return
        sheet = self._show_sheet(customer, "Credit Orders")
        self._add_history_button(sheet, customer)
        for order in orders:
            sheet.copy.add_widget(_order_table([order]))
            status = display_payment_status(order["payment_status"], "credit")
            receipt = _Action(f'{order["order_number"]} · {status} · View Receipt',
                              size_hint_y=None, height=dp(43), font=12)
            receipt.bind(on_release=lambda _, order_id=order["id"]: self._open_receipt(order_id))
            sheet.copy.add_widget(receipt)

    def _choose_payment(self, customer, orders):
        if len(orders) == 1:
            self._open_payment(orders[0])
            return
        sheet = self._show_sheet("Record Payment", f"Select an order for {customer}.")
        for order in orders:
            caption = f'{order["order_number"]} · {format_price(order["outstanding_balance_centavos"])} due'
            option = _Action(caption, size_hint_y=None, height=dp(44))
            option.bind(on_release=lambda _, order=order: self._open_payment(order))
            sheet.copy.add_widget(option)

    def _open_payment(self, order):
        try:
            receipt = self.orders.get_receipt(order["id"])
        except (OSError, sqlite3.Error) as error:
            Logger.warning("Utang: Could not read balance: %s", error)
            receipt = None
        if receipt is None or receipt.balance == 0:
            self._refresh()
            self._show_sheet("Record Payment", "This order has no outstanding payment or is unavailable.")
            return
        sheet = self._show_sheet(
            "Record Payment",
            f"{receipt.customer_name} · {receipt.order_number}\n"
            f"Original Total: {format_price(receipt.total)}\n"
            f"Already Paid: {format_price(receipt.applied)}\n"
            f"Remaining Balance: {format_price(receipt.balance)}",
        )
        field, amount = _text_field("Payment amount (₱)")
        sheet.copy.add_widget(field)
        preview = wrapping_label("", 14, BALANCE_INK, bold=True)
        sheet.copy.add_widget(preview)
        confirm = _Action("Confirm Payment", primary=True, size_hint_y=None, height=dp(44))
        sheet.copy.add_widget(confirm)
        self._add_history_button(sheet, receipt.customer_name)

        def entered_amount():
            value = parse_payment_amount(amount.text)
            if not 0 < value <= receipt.balance:
                raise ValueError("Enter a payment greater than zero and no more than the remaining balance.")
            return value

        def update_preview(*_):
            try:
                paid = entered_amount()
            except ValueError as error:
                preview.text = str(error) if amount.text.strip() else "Enter a payment to preview the new balance."
                confirm.disabled = True
            else:
                preview.text = f"New Remaining Balance: {format_price(receipt.balance - paid)}"
                confirm.disabled = False

        def submit(*_):
            if confirm.disabled or sheet.parent is None:
                return
            confirm.disabled = True
            amount.focus = False
            try:
                self.orders.record_credit_payment(
                    order["id"], entered_amount(), expected_paid=receipt.applied,
                )
            except ValueError as error:
                preview.text = str(error)
            except (OSError, sqlite3.Error) as error:
                Logger.warning("Utang: Could not record payment: %s", error)
                preview.text = "Could not record payment. Try again."
                confirm.disabled = False
            else:
                sheet.dismiss()
                self._refresh()
                self.manager.get_screen("sales")._refresh_orders()
                self._show_sheet("Payment Recorded", f"{receipt.order_number} · {format_price(entered_amount())}")
                self._add_history_button(self.sheet, receipt.customer_name)

        amount.bind(text=update_preview)
        confirm.bind(on_release=submit)
        update_preview()

    def _add_history_button(self, sheet, customer):
        history = _Action("Payment History", size_hint_y=None, height=dp(43))
        history.bind(on_release=lambda *_: self._view_payments(customer))
        sheet.copy.add_widget(history)

    def _view_payments(self, customer):
        try:
            history = self.orders.credit_payment_history(customer)
        except (OSError, sqlite3.Error) as error:
            Logger.warning("Utang: Could not load payment history: %s", error)
            self._show_sheet("Payment History", "Could not load payment history. Try again.")
            return
        sheet = self._show_sheet("Payment History", customer)
        if not history:
            sheet.copy.add_widget(wrapping_label("No payments recorded yet.", 14, MUTED))
        for number, paid, stamp, balance in history:
            entry = _vertical(spacing=dp(4), padding=dp(9))
            paint_surface(entry, PEACH, radius=10)
            entry.add_widget(wrapping_label(f"{format_price(paid)} · {number}", 15, AMOUNT, bold=True))
            entry.add_widget(wrapping_label(local_timestamp(stamp), 12, MUTED))
            entry.add_widget(wrapping_label(f"Balance after payment: {format_price(balance)}", 13))
            sheet.copy.add_widget(entry)

    def _open_receipt(self, order_id):
        self.manager.get_screen("receipt").open_order(order_id, return_screen=self.name)

    def _show_sheet(self, title, message):
        self.search.focus = False
        if self.sheet:
            self.sheet.dismiss()
        self.sheet = BottomSheet(title, message)
        self.add_widget(self.sheet)
        return self.sheet

    def _go_home(self, *_):
        self.manager.current = "dashboard"
