import math
import sqlite3

from kivy.graphics import Color, Mesh, Rectangle
from kivy.graphics.opengl import GL_MAX_TEXTURE_SIZE, glGetIntegerv
from kivy.logger import Logger
from kivy.metrics import dp
from kivy.uix.anchorlayout import AnchorLayout
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.image import Image
from kivy.uix.screenmanager import Screen
from kivy.uix.scrollview import ScrollView
from kivy.uix.widget import Widget
from kivy.utils import platform

from product_store import format_price
from receipt_data import local_timestamp
from receipt_export import (
    RECEIPT_FOOTER, RECEIPT_HEADING, RECEIPT_LOGO, ReceiptOutputError, receipt_output,
)
from screens.dashboard_screen import (
    AMOUNT, INK, MUTED, WHITE, BottomSheet, IconButton, label,
    paint_header_gradient, paint_surface, wrapping_label,
)
from screens.new_order_screen import _Action, _vertical


BADGES = {
    "Paid": ((.87, .97, .84, 1), (.11, .38, .12, 1)),
    "Partially Paid": ((1, .90, .75, 1), AMOUNT),
    "Unpaid": ((1, .89, .87, 1), (.62, .13, .11, 1)),
}


def _separator():
    rule = Widget(size_hint_y=None, height=dp(5))
    with rule.canvas:
        Color(.67, .62, .59, 1)
        line = Mesh(mode="lines")

    def update(*_):
        vertices = []
        for index in range(math.ceil(rule.width / dp(6))):
            left = rule.x + index * dp(6)
            right = min(left + dp(3), rule.right)
            vertices.extend((left, rule.center_y, 0, 0, right, rule.center_y, 0, 0))
        line.vertices = vertices
        line.indices = list(range(len(vertices) // 4))

    rule.bind(pos=update, size=update)
    update()
    return rule


def _table_row(cells, *, bold=False):
    row = BoxLayout(size_hint_y=None, spacing=dp(4))

    def fit(*_):
        row.height = max(child.height for child in row.children) + dp(4)

    for text, width, align in cells:
        column = wrapping_label(text, 13, bold=bold, align=align)
        column.size_hint_x = width
        column.bind(height=fit)
        row.add_widget(column)
    fit()
    return row


class _ReceiptPaper(BoxLayout):
    def __init__(self, **kwargs):
        super().__init__(orientation="vertical", size_hint_y=None, spacing=dp(5),
                         padding=(dp(14), dp(17)), **kwargs)
        self.bind(minimum_height=self.setter("height"))
        with self.canvas.before:
            Color(*WHITE)
            self.paper = Rectangle()
            self.edges = Mesh(mode="triangles")
        self.bind(pos=self._draw, size=self._draw)
        self._draw()

    def _draw(self, *_):
        depth = min(dp(6), self.height / 2)
        self.paper.pos = (self.x, self.y + depth)
        self.paper.size = (self.width, max(0, self.height - 2 * depth))
        teeth = max(1, round(self.width / dp(12)))
        pitch = self.width / teeth
        vertices = []
        for tip, base in ((self.y, self.y + depth), (self.top, self.top - depth)):
            for index in range(teeth):
                left = self.x + index * pitch
                vertices.extend((left, base, 0, 0, left + pitch / 2, tip, 0, 0,
                                 left + pitch, base, 0, 0))
        self.edges.vertices = vertices
        self.edges.indices = list(range(len(vertices) // 4))

    def display(self, receipt):
        self.clear_widgets()
        logo_holder = AnchorLayout(size_hint_y=None, height=dp(48))
        logo_holder.add_widget(Image(
            source=str(RECEIPT_LOGO), fit_mode="contain", size_hint=(None, None),
            size=(dp(66), dp(48)),
        ))
        self.add_widget(logo_holder)
        self.add_widget(wrapping_label("GrillFlow", 24, bold=True, align="center"))
        self.add_widget(wrapping_label("BBQ Business Manager", 12, MUTED, align="center"))
        self.add_widget(_separator())
        self.add_widget(wrapping_label(RECEIPT_HEADING, 17, bold=True, align="center"))
        self.add_widget(wrapping_label(f"Order No.: {receipt.order_number}", 13, bold=True))
        self.add_widget(wrapping_label(f"Customer: {receipt.customer_name}", 13))
        self.add_widget(wrapping_label(local_timestamp(receipt.created_at), 13, MUTED))
        self.add_widget(_separator())
        self._add_item_row("Item", "Qty", "Price", "Total", bold=True)
        for item in receipt.items:
            self._add_item_row(
                f"{item.name}\n{item.unit}", str(item.quantity),
                format_price(item.unit_price), format_price(item.subtotal),
            )
        self.add_widget(_separator())
        for caption, amount in receipt.amounts():
            self.add_widget(_table_row(((caption, .61, "left"), (amount, .39, "right")), bold=True))
        self._add_status(receipt.status)
        if len(receipt.payments) > 1:
            self.add_widget(_separator())
            self.add_widget(wrapping_label("Payment History", 13, bold=True))
            for payment in receipt.payments:
                self.add_widget(wrapping_label(
                    f"{local_timestamp(payment.created_at)} · {format_price(payment.applied)} applied",
                    12, MUTED,
                ))
        if receipt.remarks.strip():
            self.add_widget(wrapping_label(f"Remarks: {receipt.remarks}", 13))
        self.add_widget(_separator())
        self.add_widget(wrapping_label(RECEIPT_FOOTER, 12, bold=True, align="center"))

    def _add_item_row(self, name, quantity, price, total, *, bold=False):
        self.add_widget(_table_row(
            ((name, .37, "left"), (quantity, .13, "center"),
             (price, .24, "right"), (total, .26, "right")), bold=bold,
        ))

    def _add_status(self, status):
        row = BoxLayout(size_hint_y=None, height=dp(29), spacing=dp(4))
        row.add_widget(label("Payment Status", 13, bold=True))
        fill, text_color = BADGES[status]
        badge = label(status, 12, text_color, bold=True, align="center",
                      size_hint_x=None, width=dp(110))
        paint_surface(badge, fill, radius=8)
        row.add_widget(badge)
        self.add_widget(row)


class ReceiptScreen(Screen):
    def __init__(self, orders, **kwargs):
        super().__init__(**kwargs)
        self.orders = orders
        self.output = receipt_output(orders.products.data_dir, platform)
        self.receipt = None
        self.sheet = None

        shell = BoxLayout(orientation="vertical")
        paint_header_gradient(shell)
        header = BoxLayout(size_hint_y=None, height=dp(57), spacing=dp(5),
                           padding=(dp(5), 0, dp(12), 0))
        self.back_button = IconButton("back", WHITE, 22, size_hint_x=None, width=dp(44))
        self.back_button.bind(on_release=self._close)
        header.add_widget(self.back_button)
        header.add_widget(label("Receipt", 23, WHITE, bold=True))
        shell.add_widget(header)

        self.scroll = ScrollView(do_scroll_x=False, bar_width=dp(3))
        self.content = _vertical(padding=(dp(12), dp(4), dp(12), dp(8)))
        self.paper = _ReceiptPaper()
        self.content.add_widget(self.paper)
        self.scroll.add_widget(self.content)
        shell.add_widget(self.scroll)

        footer = BoxLayout(size_hint_y=None, height=dp(65), spacing=dp(7), padding=(dp(12), dp(8)))
        self.print_button = _Action("Print")
        self.share_button = _Action("Share")
        self.close_button = _Action("Close")
        for button, action in ((self.print_button, self._print), (self.share_button, self._share),
                               (self.close_button, self._close)):
            button.bind(on_release=action)
            footer.add_widget(button)
        shell.add_widget(footer)
        self.add_widget(shell)
        self.print_button.disabled = self.share_button.disabled = True

    def open_order(self, order_id, *, saved_number=None):
        self.receipt = None
        self.paper.clear_widgets()
        try:
            self.receipt = self.orders.get_receipt(order_id)
            if self.receipt is not None:
                self.paper.display(self.receipt)
        except (OSError, sqlite3.Error, ValueError) as error:
            Logger.warning("Receipt: Could not load order: %s", error)
            self.receipt = None
        if self.receipt is None:
            self.paper.clear_widgets()
            message = (f"{saved_number} was saved. Reopen it from Recent Orders."
                       if saved_number else "This receipt is unavailable. Return to Sales and try again.")
            self.paper.add_widget(wrapping_label("Receipt Unavailable", 18, INK, bold=True))
            self.paper.add_widget(wrapping_label(message, 14))
        self.print_button.disabled = self.share_button.disabled = self.receipt is None
        self.scroll.scroll_y = 1
        self.manager.current = self.name

    def _close(self, *_):
        if self.sheet:
            self.sheet.dismiss()
        self.manager.current = "sales"

    def _print(self, *_):
        if self.receipt is not None:
            self._output_notice("Print Receipt", lambda: self.output.print_receipt(self.receipt))

    def _share(self, *_):
        if self.receipt is not None:
            self._output_notice(
                "Share Receipt", lambda: self.output.share_receipt(self.receipt, self._export_png),
            )

    def _export_png(self, path):
        max_texture = glGetIntegerv(GL_MAX_TEXTURE_SIZE)[0]
        if math.ceil(max(self.paper.size)) > max_texture:
            raise ReceiptOutputError("This receipt is too long for a single image. Use Print / Save as PDF.")
        self.paper.export_to_png(str(path))
        if not path.is_file():
            raise ReceiptOutputError("Could not generate the receipt image.")

    def _output_notice(self, title, action):
        try:
            message = action()
        except ReceiptOutputError as error:
            message = str(error)
        except (OSError, RuntimeError) as error:
            Logger.warning("Receipt: Output failed: %s", error)
            message = "Could not generate the receipt file. Check storage access and try again."
        if self.sheet:
            self.sheet.dismiss()
        self.sheet = BottomSheet(title, message)
        self.add_widget(self.sheet)
