import sqlite3

from kivy.clock import Clock
from kivy.logger import Logger
from kivy.metrics import dp, sp
from kivy.uix.anchorlayout import AnchorLayout
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.screenmanager import Screen
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput

from product_photos import product_photo_path
from product_store import ProductConflict, format_price, normalized_name
from screens.add_product_screen import ProductImage
from screens.dashboard_screen import (
    AMOUNT,
    BORDER,
    CREAM,
    INK,
    MUTED,
    ORANGE,
    WHITE,
    BottomSheet,
    Icon,
    IconButton,
    build_navigation,
    label,
    paint_header_gradient,
    paint_surface,
    wrapping_label,
)
from screens.splash_screen import _RoundedButton


class _AddProductButton(ButtonBehavior, BoxLayout):
    def __init__(self, **kwargs):
        super().__init__(padding=(dp(10), 0), spacing=dp(5), **kwargs)
        paint_surface(self, ORANGE, radius=12)
        self.add_widget(Icon("plus", WHITE, size_hint_x=None, width=dp(17)))
        self.add_widget(label("Add Product", 14, WHITE, bold=True))


class ProductsScreen(Screen):
    def __init__(self, store, **kwargs):
        super().__init__(**kwargs)
        self.store = store
        self.sheet = None
        self.products = []
        self.load_failed = False
        self.reported_duplicates = []
        shell = BoxLayout(orientation="vertical")
        paint_surface(shell, CREAM)
        shell.add_widget(self._build_header())

        content = BoxLayout(orientation="vertical", padding=(dp(12), dp(12)))
        content.add_widget(self._build_toolbar())
        self.notice = label("", 14, AMOUNT, align="center", size_hint_y=None, height=0)
        self.hide_notice = Clock.create_trigger(self._hide_notice, 4)
        content.add_widget(self.notice)
        self.results = BoxLayout(orientation="vertical")
        content.add_widget(self.results)
        shell.add_widget(content)

        navigation, self.tabs = build_navigation(self, "Products", self._show_sheet)
        shell.add_widget(navigation)
        self.add_widget(shell)
        self.search_input.bind(text=self._render_products)
        self._render_products()

    def _build_header(self):
        header = BoxLayout(size_hint_y=None, height=dp(57), spacing=dp(5),
                           padding=(dp(5), 0, dp(12), 0))
        paint_header_gradient(header)
        self.back_button = IconButton("back", WHITE, 22, size_hint_x=None, width=dp(44))
        self.back_button.bind(on_release=self._go_home)
        header.add_widget(self.back_button)
        header.add_widget(label("Products", 23, WHITE, bold=True))
        return header

    def _build_toolbar(self):
        toolbar = BoxLayout(size_hint_y=None, height=dp(46), spacing=dp(8))
        search = BoxLayout(padding=(dp(10), 0, dp(8), 0), spacing=dp(5))
        paint_surface(search, (.98, .98, .98, 1), radius=12, border=BORDER)
        search.add_widget(Icon("search", MUTED, size_hint_x=None, width=dp(17)))
        self.search_input = TextInput(
            hint_text="Search product...", multiline=False, font_size=sp(14),
            padding=(0, dp(14), 0, 0), background_normal="", background_active="",
            background_color=(0, 0, 0, 0), foreground_color=INK,
            hint_text_color=MUTED, cursor_color=ORANGE,
        )
        search.add_widget(self.search_input)
        toolbar.add_widget(search)
        self.add_button = _AddProductButton(size_hint_x=None, width=dp(126))
        self.add_button.bind(on_release=self._open_add_product)
        toolbar.add_widget(self.add_button)
        return toolbar

    @staticmethod
    def _build_empty_state(title="No Products Available", message="Products you add will appear here."):
        holder = AnchorLayout()
        empty = BoxLayout(
            orientation="vertical", size_hint_y=None, height=dp(132), spacing=dp(8),
        )
        icon_holder = AnchorLayout(size_hint_y=None, height=dp(66))
        badge = AnchorLayout(size_hint=(None, None), size=(dp(64), dp(64)))
        paint_surface(badge, (.97, .90, .85, 1), radius=32)
        badge.add_widget(Icon("box", MUTED, size_hint=(None, None), size=(dp(32), dp(32))))
        icon_holder.add_widget(badge)
        empty.add_widget(icon_holder)
        empty.add_widget(label(title, 19, bold=True, align="center",
                               size_hint_y=None, height=dp(27)))
        empty.add_widget(label(message, 14, MUTED, align="center",
                               size_hint_y=None, height=dp(23)))
        holder.add_widget(empty)
        return holder

    def _go_home(self, *_):
        self.manager.current = "dashboard"

    def _open_add_product(self, *_):
        self.manager.get_screen("add_product").editing = None
        self.manager.current = "add_product"

    def _edit_product(self, product):
        self.manager.get_screen("add_product").editing = product
        self.manager.current = "add_product"

    def on_pre_enter(self, *_):
        try:
            self.store.initialize()
        except (OSError, sqlite3.Error) as error:
            Logger.warning("Products: Could not initialize catalog: %s", error)
            self.load_failed = True
            self._render_products()
            return
        self._refresh_products()

    def _refresh_products(self):
        try:
            self.products = self.store.list_products()
            duplicates = self.store.duplicate_names()
            self.load_failed = False
        except (OSError, sqlite3.Error) as error:
            Logger.warning("Products: Could not load products: %s", error)
            self.load_failed = True
            duplicates = self.reported_duplicates
        self._render_products()
        if duplicates != self.reported_duplicates:
            self.reported_duplicates = duplicates
            if duplicates:
                names = "\n".join(f"{name} ({count} records)" for name, count in duplicates)
                self._show_sheet(
                    "Duplicate Products",
                    f"{names}\n\nExisting records are preserved. Rename active duplicates individually "
                    "after reviewing their stock and order history.",
                )

    def on_pre_leave(self, *_):
        self.search_input.focus = False
        if self.sheet:
            self.sheet.dismiss()
        self.hide_notice.cancel()
        self._hide_notice()

    def show_saved(self):
        self.notice.text = "Product saved successfully."
        self.notice.height = dp(32)
        self.hide_notice()

    def _hide_notice(self, *_):
        self.notice.text = ""
        self.notice.height = 0

    def _render_products(self, *_):
        self.results.clear_widgets()
        if self.load_failed:
            self.results.add_widget(self._build_empty_state(
                "Could Not Load Products", "Return to Products to try again.",
            ))
            return
        if not self.products:
            self.results.add_widget(self._build_empty_state())
            return

        query = normalized_name(self.search_input.text)
        matches = [product for product in self.products if query in normalized_name(product["name"])]
        if not matches:
            self.results.add_widget(self._build_empty_state(
                "No Matching Products", "Try a different product name.",
            ))
            return
        scroll = ScrollView(do_scroll_x=False, bar_width=dp(3))
        rows = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(8),
                         padding=(dp(1), dp(9), dp(1), dp(3)))
        rows.bind(minimum_height=rows.setter("height"))
        for product in matches:
            rows.add_widget(self._product_row(product))
        scroll.add_widget(rows)
        self.results.add_widget(scroll)

    def _product_row(self, product):
        row = BoxLayout(size_hint_y=None, spacing=dp(8), padding=(dp(8), dp(8), dp(4), dp(8)))
        paint_surface(row, WHITE, radius=13, border=BORDER)
        thumbnail = AnchorLayout(size_hint_x=None, width=dp(62))
        thumbnail.add_widget(ProductImage(
            source=str(product_photo_path(self.store.data_dir, product["image_path"])),
            size_hint=(None, None), size=(dp(62), dp(62)),
        ))
        row.add_widget(thumbnail)

        details = BoxLayout(orientation="vertical", spacing=dp(2))
        details.add_widget(wrapping_label(product["name"], 15, bold=True))
        details.add_widget(wrapping_label(f"Price: {format_price(product['selling_price'])}", 13))
        stock = f"Stock: {product['stock']}" if product["stock"] else "Out of Stock"
        details.add_widget(wrapping_label(f"{stock} · {product['unit']}", 13))

        def fit_row(_, height):
            row.height = max(dp(78), height + dp(16))

        details.bind(minimum_height=fit_row)
        fit_row(details, details.minimum_height)
        row.add_widget(details)
        for icon, action, color in (
            ("edit", self._edit_product, ORANGE), ("delete", self._confirm_delete, AMOUNT),
        ):
            button = IconButton(icon, color, 18, size_hint_x=None, width=dp(44))
            button.bind(on_release=lambda _, action=action: action(product))
            row.add_widget(button)
        return row

    def _confirm_delete(self, product):
        sheet = self._show_sheet(
            "Permanently Delete?",
            "This action will permanently remove the selected record from GrillFlow. "
            f"It cannot be undone.\n\nProduct: {product['name']}",
            confirmation="Cancel",
        )
        delete = _RoundedButton(text="Delete Permanently", size_hint_y=None, height=dp(44))
        sheet.copy.add_widget(delete)

        def submit(*_):
            if delete.disabled or sheet.parent is None:
                return
            delete.disabled = sheet.confirm_button.disabled = True
            try:
                self.store.delete(product["id"])
            except ProductConflict as error:
                self._refresh_products()
                self._show_sheet("Delete Product", str(error))
            except (OSError, sqlite3.Error) as error:
                Logger.warning("Products: Could not delete product: %s", error)
                self._show_sheet("Delete Product", "Could not delete the product. Try again.")
            else:
                sheet.dismiss()
                self._refresh_products()
                self.notice.text = "Product permanently deleted."
                self.notice.height = dp(32)
                self.hide_notice()

        delete.bind(on_release=submit)

    def _show_sheet(self, title, message, *, confirmation="Close"):
        self.search_input.focus = False
        if self.sheet and self.sheet.parent:
            self.sheet.dismiss()
        self.sheet = BottomSheet(title, message, confirmation=confirmation)
        self.add_widget(self.sheet)
        return self.sheet
