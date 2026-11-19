import sqlite3

from kivy.clock import Clock
from kivy.core.image import Image as CoreImage
from kivy.logger import Logger
from kivy.metrics import dp, sp
from kivy.uix.anchorlayout import AnchorLayout
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.dropdown import DropDown
from kivy.uix.screenmanager import Screen
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput

from order_draft import OrderDraft
from order_store import customer_name, format_customer_name
from product_photos import DEFAULT_PHOTO, product_photo_path
from product_store import UNITS, format_price, normalized_name
from screens.add_product_screen import ProductImage
from screens.dashboard_screen import (
    AMOUNT, BORDER, CREAM, INK, MUTED, ORANGE, WHITE, BottomSheet, Icon, IconButton,
    label, paint_header_gradient, paint_surface, wrapping_label,
)


def _vertical(**kwargs):
    layout = BoxLayout(orientation="vertical", size_hint_y=None, **kwargs)
    layout.bind(minimum_height=layout.setter("height"))
    return layout


def _card():
    card = _vertical(spacing=dp(7), padding=dp(10))
    paint_surface(card, WHITE, radius=13, border=BORDER)
    return card


class _Action(Button):
    def __init__(self, text, *, primary=False, font=14, **kwargs):
        super().__init__(
            text=text, font_size=sp(font), bold=True, color=WHITE if primary else AMOUNT,
            disabled_color=MUTED, background_normal="", background_down="",
            background_disabled_normal="", background_color=(0, 0, 0, 0), **kwargs,
        )
        paint_surface(self, ORANGE if primary else WHITE, radius=10, border=BORDER)
        self.bind(disabled=self._dim)

    def _dim(self, _, disabled):
        self.opacity = .55 if disabled else 1


def _icon_holder(icon, color, width):
    holder = AnchorLayout(size_hint_x=None, width=dp(width))
    holder.add_widget(Icon(icon, color, size_hint=(None, None), size=(dp(19), dp(19))))
    return holder


def _text_field(hint):
    holder = BoxLayout(size_hint_y=None, height=dp(44))
    paint_surface(holder, (.99, .98, .97, 1), radius=10, border=BORDER)
    field = TextInput(
        hint_text=hint, multiline=False, font_size=sp(15), padding=(dp(10), dp(11)),
        foreground_color=INK, hint_text_color=MUTED, cursor_color=ORANGE,
        background_normal="", background_active="", background_color=(0, 0, 0, 0),
    )
    holder.add_widget(field)
    return holder, field


def _product_details(source, name, description):
    row = BoxLayout(size_hint_y=None, spacing=dp(9))
    holder = AnchorLayout(size_hint_x=None, width=dp(60))
    holder.add_widget(ProductImage(
        source=source, size_hint=(None, None), size=(dp(60), dp(54)),
    ))
    row.add_widget(holder)
    details = _vertical(spacing=dp(2))
    details.add_widget(wrapping_label(name, 15, bold=True))
    details.add_widget(wrapping_label(description, 13, MUTED))
    details.bind(height=lambda _, height: setattr(row, "height", max(dp(56), height)))
    row.add_widget(details)
    return row


class _ProductRow(BoxLayout):
    def __init__(self, product, source, order, **kwargs):
        super().__init__(orientation="vertical", size_hint_y=None, spacing=dp(5),
                         padding=(dp(9), dp(7)), **kwargs)
        self.bind(minimum_height=self.setter("height"))
        self.product = product
        self.order = order
        self.quantity = order.selected_quantities.get(product["id"], 0)
        paint_surface(self, WHITE, radius=12, border=BORDER)
        self.add_widget(_product_details(
            source, product["name"], f'{format_price(product["selling_price"])} / {product["unit"]}',
        ))

        controls = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(4))
        self.stock = label("", 12, MUTED, shorten=True)
        controls.add_widget(self.stock)
        self.minus = _Action("-", size_hint_x=None, width=dp(43))
        self.count = label("0", 13, bold=True, align="center", size_hint_x=None,
                           width=dp(38), shorten=True)
        self.plus = _Action("+", size_hint_x=None, width=dp(43))
        self.add_button = _Action("+ Add", primary=True, size_hint_x=None, width=dp(69))
        self.minus.bind(on_release=lambda *_: self._step(-1))
        self.plus.bind(on_release=lambda *_: self._step(1))
        self.add_button.bind(on_release=lambda *_: order.add_product(self.product, self.quantity))
        for control in (self.minus, self.count, self.plus, self.add_button):
            controls.add_widget(control)
        self.add_widget(controls)
        self.refresh()

    def _step(self, amount):
        self.quantity += amount
        self.refresh()

    def refresh(self):
        available = self.order.draft.available(self.product)
        self.quantity = max(0, min(self.quantity, available))
        self.order.selected_quantities[self.product["id"]] = self.quantity
        self.count.text = str(self.quantity)
        self.minus.disabled = self.quantity == 0
        self.plus.disabled = self.quantity >= available
        self.add_button.disabled = not 0 < self.quantity <= available
        if available:
            self.stock.text = f"Available: {available}"
        else:
            self.stock.text = "All stock in cart" if self.product["stock"] else "Out of stock"


class NewOrderScreen(Screen):
    def __init__(self, store, orders, **kwargs):
        super().__init__(**kwargs)
        self.store = store
        self.orders = orders
        self.draft = OrderDraft()
        self.products = {}
        self.product_rows = {}
        self.selected_quantities = {}
        self.photo_sources = {}
        self.load_failed = False
        self.unit = "All"
        self.sheet = None

        shell = BoxLayout(orientation="vertical")
        paint_surface(shell, CREAM)
        shell.add_widget(self._build_header())
        self.scroll = ScrollView(do_scroll_x=False, bar_width=dp(3))
        content = _vertical(spacing=dp(10), padding=(dp(12), dp(11), dp(12), dp(12)))
        content.add_widget(self._build_customer())
        content.add_widget(self._build_catalog())
        content.add_widget(self._build_cart())
        self.scroll.add_widget(content)
        shell.add_widget(self.scroll)
        shell.add_widget(self._build_actions())
        self.add_widget(shell)
        self._refresh_cart()

    def _build_header(self):
        header = BoxLayout(size_hint_y=None, height=dp(57), spacing=dp(5),
                           padding=(dp(5), 0, dp(12), 0))
        paint_header_gradient(header)
        self.back_button = IconButton("back", WHITE, 22, size_hint_x=None, width=dp(44))
        self.back_button.bind(on_release=self._go_back)
        header.add_widget(self.back_button)
        header.add_widget(label("New Order", 23, WHITE, bold=True))
        header.add_widget(label("GrillFlow", 15, WHITE, bold=True, align="right",
                                size_hint_x=None, width=dp(72)))
        return header

    def _build_customer(self):
        card = _card()
        heading = BoxLayout(size_hint_y=None, height=dp(23), spacing=dp(5))
        heading.add_widget(_icon_holder("person", ORANGE, 22))
        heading.add_widget(label("Customer", 17, bold=True))
        card.add_widget(heading)
        customer_row = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(7))
        field, self.customer_input = _text_field(self.draft.default_customer)
        self.customer_input.bind(focus=self._format_customer)
        self.customer_dropdown = None
        customer_row.add_widget(field)
        self.choose_customer = _Action("Choose Customer", font=12, size_hint_x=None, width=dp(124))
        self.choose_customer.bind(on_release=self._open_customers)
        customer_row.add_widget(self.choose_customer)
        card.add_widget(customer_row)
        return card

    def _format_customer(self, field, focused):
        if not focused:
            field.text = format_customer_name(field.text)

    def _open_customers(self, button):
        if self.customer_dropdown is not None:
            return
        self._clear_focus()
        try:
            names = self.orders.named_customers()
        except (OSError, sqlite3.Error) as error:
            Logger.warning("New Order: Could not load customers: %s", error)
            self._show_message("Choose Customer", "Could not load customer names. Try again.")
            return

        dropdown = DropDown(auto_width=False, width=min(dp(300), self.width - dp(20)),
                            max_height=dp(280), do_scroll_x=False)
        panel = _card()
        search_holder, search = _text_field("Search customer...")
        panel.add_widget(search_holder)
        results = _vertical(spacing=dp(4))
        panel.add_widget(results)
        dropdown.add_widget(panel)

        def render(*_):
            results.clear_widgets()
            query = normalized_name(search.text)
            matches = [name for name in names if query in normalized_name(name)]
            if not names:
                results.add_widget(wrapping_label("No customers available.", 15, bold=True))
            elif not matches:
                results.add_widget(wrapping_label("No matching customers found", 14, MUTED))
            for name in matches:
                option = _Action(name, size_hint_y=None, height=dp(44),
                                 primary=normalized_name(name) == normalized_name(self.customer_input.text),
                                 shorten=True, padding=(dp(8), 0))
                option.bind(size=lambda widget, size: setattr(widget, "text_size", size))
                option.bind(on_release=lambda _, name=name: dropdown.select(name))
                results.add_widget(option)
            dropdown.scroll_y = 1

        def selected(_, name):
            self.customer_input.text = format_customer_name(name)
            search.focus = False

        def refresh(_):
            nonlocal names
            try:
                latest = self.orders.named_customers()
            except (OSError, sqlite3.Error) as error:
                Logger.warning("New Order: Could not refresh customers: %s", error)
                dropdown.dismiss()
                return False
            if latest != names:
                names = latest
                render()

        def dismissed(*_):
            refresh_event.cancel()
            search.focus = False
            self.customer_dropdown = None

        search.bind(text=render)
        dropdown.bind(on_select=selected, on_dismiss=dismissed)
        render()
        self.customer_dropdown = dropdown
        dropdown.open(button)
        refresh_event = Clock.schedule_interval(refresh, 1)

    def _build_catalog(self):
        catalog = _vertical(spacing=dp(7))
        catalog.add_widget(label("Select Products", 17, bold=True, size_hint_y=None, height=dp(25)))
        search, self.search_input = _text_field("Search product...")
        self.search_input.bind(text=self._render_products)
        catalog.add_widget(search)
        filters = BoxLayout(size_hint_y=None, height=dp(42), spacing=dp(5))
        self.filters = {}
        for unit in ("All", *UNITS):
            button = _Action(unit, font=12)
            button.bind(on_release=lambda _, unit=unit: self._select_unit(unit))
            self.filters[unit] = button
            filters.add_widget(button)
        catalog.add_widget(filters)
        self.catalog_rows = _vertical(spacing=dp(8))
        catalog.add_widget(self.catalog_rows)
        self._select_unit(self.unit)
        return catalog

    def _build_cart(self):
        card = _card()
        heading = BoxLayout(size_hint_y=None, height=dp(44))
        heading.add_widget(label("Order Items", 17, bold=True))
        self.clear_button = _Action("Clear All", font=12, size_hint_x=None, width=dp(75))
        self.clear_button.bind(on_release=self._confirm_clear)
        heading.add_widget(self.clear_button)
        card.add_widget(heading)
        self.cart_rows = _vertical(spacing=dp(8))
        card.add_widget(self.cart_rows)
        self.subtotal_label = wrapping_label("", 14, align="right")
        self.total_label = wrapping_label("", 18, AMOUNT, bold=True, align="right")
        card.add_widget(self.subtotal_label)
        card.add_widget(self.total_label)
        return card

    def _build_actions(self):
        footer = BoxLayout(size_hint_y=None, height=dp(64), spacing=dp(8), padding=(dp(12), dp(8)))
        paint_surface(footer, WHITE, border=BORDER)
        self.receipt_button = _Action("View Receipt")
        self.receipt_button.bind(on_release=self._view_receipt)
        self.payment_button = _Action("Proceed to Payment", primary=True)
        self.payment_button.bind(on_release=self._proceed)
        footer.add_widget(self.receipt_button)
        footer.add_widget(self.payment_button)
        return footer

    def on_pre_enter(self, *_):
        self._reload_products(initialize=True)
        try:
            _, self.customer_input.hint_text = self.orders.preview()
        except (OSError, sqlite3.Error):
            self.customer_input.hint_text = self.draft.default_customer
        self._refresh_cart()
        self.scroll.scroll_y = 1

    def on_pre_leave(self, *_):
        self._clear_focus()
        if self.customer_dropdown is not None:
            self.customer_dropdown.dismiss()
        if self.sheet:
            self.sheet.dismiss()

    def _go_back(self, *_):
        self.manager.current = "sales"

    def _reload_products(self, *, initialize=False):
        try:
            if initialize:
                self.store.initialize()
            self.products = {product["id"]: product for product in self.store.list_products()}
            self.load_failed = False
        except (OSError, sqlite3.Error) as error:
            Logger.warning("New Order: Could not load products: %s", error)
            self.products = {}
            self.load_failed = True
        self.photo_sources.clear()
        if not self.load_failed:
            self.selected_quantities = {
                product_id: min(quantity, self.draft.available(self.products[product_id]))
                for product_id, quantity in self.selected_quantities.items()
                if product_id in self.products
            }
        self._render_products()

    def _photo_source(self, product):
        image_path = product["image_path"]
        if image_path not in self.photo_sources:
            source = DEFAULT_PHOTO
            try:
                candidate = product_photo_path(self.store.data_dir, image_path)
                if candidate != DEFAULT_PHOTO and CoreImage(str(candidate), nocache=True).texture:
                    source = candidate
            except Exception:
                # Kivy image providers also raise bare Exception for corrupt files.
                Logger.warning("New Order: Could not read product photo, using default")
            self.photo_sources[image_path] = str(source)
        return self.photo_sources[image_path]

    def _select_unit(self, unit):
        self.unit = unit
        for name, button in self.filters.items():
            button.color = AMOUNT if name == unit else MUTED
            button.bold = name == unit
        self._render_products()

    def _render_products(self, *_):
        self.catalog_rows.clear_widgets()
        self.product_rows.clear()
        query = self.search_input.text.strip().casefold()
        for product_id, product in self.products.items():
            if query in product["name"].casefold() and self.unit in ("All", product["unit"]):
                row = _ProductRow(product, self._photo_source(product), self)
                self.product_rows[product_id] = row
                self.catalog_rows.add_widget(row)
        if not self.product_rows:
            if self.load_failed:
                title, message = "Could Not Load Products", "Return to New Order to try again."
            elif not self.products:
                title, message = "No Products Available", "Add products first before creating an order."
            else:
                title, message = "No Matching Products", "Try another name or unit."
            empty = _card()
            empty.add_widget(wrapping_label(title, 15, bold=True, align="center"))
            empty.add_widget(wrapping_label(message, 13, MUTED, align="center"))
            self.catalog_rows.add_widget(empty)

    def add_product(self, product, quantity):
        if quantity <= 0:
            return
        try:
            self.draft.add(product, quantity)
        except ValueError as error:
            self._show_message("Cannot Add Product", str(error))
            return
        product_id = product["id"]
        self.selected_quantities[product_id] = 0
        if product_id in self.product_rows:
            self.product_rows[product_id].quantity = 0
        self._refresh_cart()

    def _remove_product(self, product_id):
        self.draft.lines.pop(product_id, None)
        self._refresh_cart()

    def _confirm_clear(self, *_):
        if self.draft.lines:
            sheet = self._show_message("Clear Order Items?", "Remove all items from this draft order.")
            clear = _Action("Clear All", primary=True, size_hint_y=None, height=dp(44))
            clear.bind(on_release=self._clear_cart)
            sheet.copy.add_widget(clear)

    def _clear_cart(self, *_):
        self.sheet.dismiss()
        self.draft.lines.clear()
        self._refresh_cart()

    def _refresh_cart(self):
        self.cart_rows.clear_widgets()
        for product_id, line in self.draft.lines.items():
            product = line.product
            row = _vertical(spacing=dp(4), padding=(dp(5), dp(6)))
            paint_surface(row, CREAM, radius=10)
            row.add_widget(_product_details(
                self._photo_source(product), product["name"],
                f'{format_price(product["selling_price"])} x {line.quantity}',
            ))
            totals = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(5))
            totals.add_widget(label(format_price(line.subtotal), 15, AMOUNT, bold=True))
            remove = _Action("Remove", font=12, size_hint_x=None, width=dp(76))
            remove.bind(on_release=lambda _, product_id=product_id: self._remove_product(product_id))
            totals.add_widget(remove)
            row.add_widget(totals)
            self.cart_rows.add_widget(row)

        empty = not self.draft.lines
        if empty:
            self.cart_rows.add_widget(wrapping_label("No items added yet.", 14, MUTED))
        self.clear_button.disabled = self.receipt_button.disabled = self.payment_button.disabled = empty
        total = format_price(self.draft.total)
        self.subtotal_label.text = f"Subtotal  {total}"
        self.total_label.text = f"Total  {total}"
        for row in self.product_rows.values():
            row.refresh()

    def _view_receipt(self, *_):
        if not self.draft.lines:
            return
        customer = format_customer_name(customer_name(self.customer_input.text)) or self.customer_input.hint_text
        receipt = self._show_message("Draft Receipt", f"Customer: {customer}")
        for line in self.draft.lines.values():
            item = _card()
            item.add_widget(wrapping_label(line.product["name"], 15, bold=True))
            item.add_widget(wrapping_label(
                f'{line.quantity} x {format_price(line.product["selling_price"])}', 14, MUTED,
            ))
            item.add_widget(wrapping_label(format_price(line.subtotal), 15, bold=True, align="right"))
            receipt.copy.add_widget(item)
        receipt.copy.add_widget(wrapping_label(
            f"Grand Total  {format_price(self.draft.total)}", 17, AMOUNT, bold=True, align="right",
        ))

    def _proceed(self, *_):
        if not self.draft.lines:
            return
        self._reload_products()
        if self.load_failed:
            self._show_message("Could Not Check Stock", "Try again before proceeding.")
            return
        try:
            self.draft.validate_stock(self.products)
        except ValueError as error:
            self._show_message("Check Order Items", str(error))
            return
        payment = self.manager.get_screen("payment")
        try:
            payment.prepare(self.draft, self.customer_input.text, self._photo_source)
        except (OSError, sqlite3.Error) as error:
            Logger.warning("New Order: Could not prepare payment: %s", error)
            self._show_message("Could Not Open Payment", "Check storage access and try again.")
            return
        self._clear_focus()
        self.manager.current = "payment"

    def reset_after_sale(self):
        self.draft.lines.clear()
        self.customer_input.text = ""
        self.product_rows.clear()
        self.selected_quantities.clear()
        self.search_input.text = ""
        self._select_unit("All")
        self._refresh_cart()

    def _clear_focus(self):
        self.search_input.focus = self.customer_input.focus = False

    def _show_message(self, title, message):
        self._clear_focus()
        if self.sheet:
            self.sheet.dismiss()
        self.sheet = BottomSheet(title, message)
        self.add_widget(self.sheet)
        return self.sheet
