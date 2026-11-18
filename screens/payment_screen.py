import sqlite3
from datetime import datetime

from kivy.logger import Logger
from kivy.metrics import dp, sp
from kivy.uix.anchorlayout import AnchorLayout
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.checkbox import CheckBox
from kivy.uix.screenmanager import Screen
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput

from order_draft import OrderDraft
from order_store import CREDIT, PAID, PARTIAL, allocate_payment, customer_name, parse_payment_amount
from product_store import format_price
from screens.dashboard_screen import (
    AMOUNT, BORDER, CREAM, INK, MUTED, ORANGE, WHITE, IconButton, label,
    paint_header_gradient, paint_surface, wrapping_label,
)
from screens.new_order_screen import _Action, _card, _product_details, _text_field, _vertical


class PaymentScreen(Screen):
    def __init__(self, orders, **kwargs):
        super().__init__(**kwargs)
        self.orders = orders
        self.draft = OrderDraft()
        self.customer = ""
        self.mode = PAID
        self.saving = False

        shell = BoxLayout(orientation="vertical")
        paint_surface(shell, CREAM)
        shell.add_widget(self._build_header())
        self.scroll = ScrollView(do_scroll_x=False, bar_width=dp(3))
        content = _vertical(spacing=dp(10), padding=(dp(12), dp(11), dp(12), dp(12)))
        self.details = _card()
        content.add_widget(self.details)
        content.add_widget(self._build_payment())
        content.add_widget(self._build_remarks())
        self.scroll.add_widget(content)
        shell.add_widget(self.scroll)
        footer = _vertical(spacing=dp(4), padding=(dp(12), dp(8)))
        paint_surface(footer, WHITE, border=BORDER)
        self.status = wrapping_label("", 13, AMOUNT)
        self.status.height = 0
        footer.add_widget(self.status)
        self.save_button = _Action("Save Order", primary=True, size_hint_y=None, height=dp(48))
        self.save_button.bind(on_release=self._save)
        footer.add_widget(self.save_button)
        shell.add_widget(footer)
        self.add_widget(shell)
        self._update_amounts()

    def _build_header(self):
        header = BoxLayout(size_hint_y=None, height=dp(57), spacing=dp(5),
                           padding=(dp(5), 0, dp(12), 0))
        paint_header_gradient(header)
        self.back_button = IconButton("back", WHITE, 22, size_hint_x=None, width=dp(44))
        self.back_button.bind(on_release=self._go_back)
        header.add_widget(self.back_button)
        header.add_widget(label("Proceed to Payment", 21, WHITE, bold=True))
        brand = label("GrillFlow", 14, WHITE, bold=True, align="right", size_hint_x=None)

        def layout_brand(_, width):
            brand.width = dp(66) if width >= dp(350) else 0
            brand.opacity = int(brand.width > 0)

        header.bind(width=layout_brand)
        layout_brand(header, header.width)
        header.add_widget(brand)
        return header

    def _build_payment(self):
        card = _card()
        card.add_widget(wrapping_label("Payment", 17, bold=True))
        self.payment_options = {}
        for mode, caption in ((PAID, "Paid"), (PARTIAL, "Partial Payment"), (CREDIT, "Utang (Credit)")):
            row = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(4))
            holder = AnchorLayout(size_hint_x=None, width=dp(44))
            checkbox = CheckBox(
                group=f"grillflow-payment-{id(self)}", allow_no_selection=False,
                active=mode == PAID, color=ORANGE, size_hint=(1, 1),
            )
            checkbox.bind(active=lambda _, active, mode=mode: self._select_mode(mode) if active else None)
            holder.add_widget(checkbox)
            row.add_widget(holder)
            button = _Action(caption)
            button.bind(on_release=lambda _, checkbox=checkbox: setattr(checkbox, "active", True))
            row.add_widget(button)
            card.add_widget(row)
            self.payment_options[mode] = checkbox

        card.add_widget(wrapping_label("Amount Paid (₱)", 14, bold=True))
        amount_field, self.amount_input = _text_field("0.00")
        self.amount_input.bind(text=self._update_amounts)
        card.add_widget(amount_field)
        self.change_label = wrapping_label("", 14)
        self.balance_label = wrapping_label("", 14, AMOUNT, bold=True)
        self.balance_label.height = 0
        card.add_widget(self.change_label)
        card.add_widget(self.balance_label)
        return card

    def _build_remarks(self):
        card = _card()
        card.add_widget(wrapping_label("Remarks (optional)", 15, bold=True))
        field = BoxLayout(size_hint_y=None, height=dp(77))
        paint_surface(field, CREAM, radius=10, border=BORDER)
        self.remarks_input = TextInput(
            hint_text="Add a note", font_size=sp(14), padding=(dp(10), dp(9)),
            foreground_color=INK, hint_text_color=MUTED, cursor_color=ORANGE,
            background_normal="", background_active="", background_color=(0, 0, 0, 0),
        )
        self.remarks_input.bind(text=self._update_remarks)
        field.add_widget(self.remarks_input)
        card.add_widget(field)
        self.remarks_count = wrapping_label("0 / 100", 12, MUTED, align="right")
        card.add_widget(self.remarks_count)
        return card

    def prepare(self, draft, customer, photo_source):
        order_number, guest_name = self.orders.preview()
        self.draft.lines = draft.lines.copy()
        self.customer = customer_name(customer)
        self.details.clear_widgets()
        self.details.add_widget(wrapping_label("Order Details", 17, bold=True))
        self.details.add_widget(wrapping_label(f"{order_number} · Preview", 16, AMOUNT, bold=True))
        self.details.add_widget(wrapping_label(f"Customer: {self.customer or guest_name}", 14))
        self.details.add_widget(wrapping_label(datetime.now().strftime("%b %d, %Y · %I:%M %p"), 13, MUTED))
        for line in self.draft.lines.values():
            product = line.product
            item = _vertical(spacing=dp(2), padding=(dp(5), dp(4)))
            paint_surface(item, CREAM, radius=10)
            item.add_widget(_product_details(
                photo_source(product), product["name"],
                f'{format_price(product["selling_price"])} / {product["unit"]} × {line.quantity}',
            ))
            item.add_widget(wrapping_label(format_price(line.subtotal), 14, bold=True, align="right"))
            self.details.add_widget(item)
        self.details.add_widget(wrapping_label(
            f"Total Amount  {format_price(self.draft.total)}", 18, AMOUNT, bold=True, align="right",
        ))
        self.remarks_input.text = ""
        self.saving = False
        self.save_button.disabled = False
        self.payment_options[PAID].active = True
        self._select_mode(PAID)
        self.scroll.scroll_y = 1

    def _select_mode(self, mode):
        self.mode = mode
        self.amount_input.focus = False
        self.amount_input.disabled = mode == CREDIT
        if mode == PAID:
            pesos, cents = divmod(self.draft.total, 100)
            self.amount_input.text = f"{pesos}.{cents:02d}"
        else:
            self.amount_input.text = "0.00" if mode == CREDIT else ""
        self._update_amounts()

    def _update_amounts(self, *_):
        if hasattr(self, "status"):
            self.status.text = ""
            self.status.height = 0
        change, remaining = 0, self.draft.total if self.mode != PAID else 0
        try:
            tendered = parse_payment_amount(self.amount_input.text)
            payment = allocate_payment(self.mode, self.draft.total, tendered, self.customer)
        except ValueError:
            pass
        else:
            change, remaining = payment.change, payment.outstanding
        self.change_label.text = f"Change (Sukli)  {format_price(change)}"
        self.balance_label.text = f"Remaining Balance  {format_price(remaining)}" if self.mode != PAID else ""
        if not self.balance_label.text:
            self.balance_label.height = 0

    def _update_remarks(self, field, text):
        if len(text) > 100:
            field.text = text[:100]
            return
        self.remarks_count.text = f"{len(text)} / 100"

    def _go_back(self, *_):
        if not self.saving:
            self.manager.current = "new_order"

    def on_pre_leave(self, *_):
        self.amount_input.focus = False
        self.remarks_input.focus = False

    def _save(self, *_):
        if self.saving:
            return
        self.amount_input.focus = self.remarks_input.focus = False
        self.saving = True
        self.save_button.disabled = True
        try:
            if not self.draft.lines:
                raise ValueError("Add at least one product before saving.")
            tendered = parse_payment_amount(self.amount_input.text)
            order = self.orders.save_order(
                self.draft, self.customer, self.mode, tendered, self.remarks_input.text,
            )
        except ValueError as error:
            self.status.text = str(error)
        except (OSError, sqlite3.Error) as error:
            Logger.warning("Payment: Could not save order: %s", error)
            self.status.text = "Could not save the order. Check storage access and try again."
        else:
            self.draft.lines.clear()
            self.manager.get_screen("new_order").reset_after_sale()
            self.manager.get_screen("receipt").open_order(order.id, saved_number=order.order_number)
            return
        self.saving = False
        self.save_button.disabled = False
