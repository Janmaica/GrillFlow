import sqlite3
from datetime import datetime

from kivy.logger import Logger
from kivy.metrics import dp
from kivy.uix.anchorlayout import AnchorLayout
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.screenmanager import Screen
from kivy.uix.scrollview import ScrollView

from order_store import PHILIPPINE_TIME, report_bounds
from product_store import MAX_SQLITE_INTEGER, format_price
from receipt_data import local_timestamp
from screens.dashboard_screen import (
    AMOUNT, BORDER, CREAM, MUTED, ORANGE, WHITE, BottomSheet, Icon, IconButton,
    build_navigation, label, paint_header_gradient, paint_surface, wrapping_label,
)
from screens.expenses_screen import PEACH, PERIODS, _dropdown
from screens.new_order_screen import _Action, _card, _icon_holder, _text_field, _vertical
from screens.splash_screen import _RoundedButton


def _icon_circle(icon):
    holder = AnchorLayout(size_hint_x=None, width=dp(36))
    circle = AnchorLayout(size_hint=(None, None), size=(dp(34), dp(34)))
    paint_surface(circle, PEACH, radius=17)
    circle.add_widget(Icon(icon, ORANGE, size_hint=(None, None), size=(dp(19), dp(19))))
    holder.add_widget(circle)
    return holder


class ConsumptionScreen(Screen):
    def __init__(self, consumption, **kwargs):
        super().__init__(**kwargs)
        self.consumption = consumption
        self.sheet = None

        shell = BoxLayout(orientation="vertical")
        paint_surface(shell, CREAM)
        header = BoxLayout(size_hint_y=None, height=dp(57), spacing=dp(5), padding=(dp(5), 0, dp(10), 0))
        paint_header_gradient(header)
        self.back_button = IconButton("back", WHITE, 22, size_hint_x=None, width=dp(44))
        self.back_button.bind(on_release=self._go_home)
        header.add_widget(self.back_button)
        header.add_widget(label("Family Consumption", 21, WHITE, bold=True))
        header.add_widget(_icon_holder("family", WHITE, 30))
        shell.add_widget(header)

        self.scroll = ScrollView(do_scroll_x=False, bar_width=dp(3))
        content = _vertical(spacing=dp(10), padding=(dp(12), dp(11), dp(12), dp(12)))
        content.add_widget(self._summary())
        self.add_button = _RoundedButton(text="+  Add Consumption", size_hint_y=None, height=dp(49))
        self.add_button.bind(on_release=self._open_form)
        content.add_widget(self.add_button)
        content.add_widget(wrapping_label("Consumption Records", 17, bold=True))
        search, self.search_input = _text_field("Search product...")
        search.add_widget(_icon_holder("search", MUTED, 28), index=len(search.children))
        content.add_widget(search)
        self.notice = wrapping_label("", 13, AMOUNT)
        self.notice.height = 0
        content.add_widget(self.notice)
        self.records = _vertical(spacing=dp(8))
        content.add_widget(self.records)
        info = _vertical(spacing=dp(4), padding=dp(12))
        paint_surface(info, PEACH, radius=12)
        info.add_widget(wrapping_label("What is Family Consumption?", 15, AMOUNT, bold=True))
        info.add_widget(wrapping_label(
            "Items taken or used by the family from the business (e.g., barbecue, rice, drinks). "
            "These are recorded separately from customer sales.", 13,
        ))
        content.add_widget(info)
        self.scroll.add_widget(content)
        shell.add_widget(self.scroll)
        navigation, self.tabs = build_navigation(self, None, self._message)
        shell.add_widget(navigation)
        self.add_widget(shell)
        self.period.bind(text=self.refresh)
        self.search_input.bind(text=self.refresh)

    def _summary(self):
        row = BoxLayout(size_hint_y=None, height=dp(96), spacing=dp(7), padding=(dp(8), dp(7)))
        paint_surface(row, WHITE, radius=13, border=BORDER)
        row.add_widget(_icon_circle("utensils"))
        copy = BoxLayout(orientation="vertical")
        copy.add_widget(wrapping_label("Total Family Consumption", 13, bold=True))
        self.total = label("—", 20, AMOUNT, bold=True, shorten=True)
        copy.add_widget(self.total)
        copy.add_widget(wrapping_label("Estimated retail value", 11, MUTED))
        row.add_widget(copy)
        holder = AnchorLayout(size_hint_x=None, width=dp(97))
        self.period = _dropdown(PERIODS[0], PERIODS, size_hint_y=None, height=dp(42))
        holder.add_widget(self.period)
        row.add_widget(holder)
        return row

    def on_pre_enter(self, *_):
        self.refresh()

    def on_pre_leave(self, *_):
        self.search_input.focus = False
        self.period.is_open = False
        if self.sheet:
            self.sheet.dismiss()

    def refresh(self, *_):
        self.records.clear_widgets()
        try:
            total, records = self.consumption.period_view(
                *report_bounds(self.period.text), search=self.search_input.text,
            )
        except (OSError, sqlite3.Error) as error:
            Logger.warning("Consumption: Could not load records: %s", error)
            self.total.text = "—"
            self.records.add_widget(wrapping_label("Could not load consumption records.", 14, MUTED))
            return
        self.total.text = format_price(total)
        if not records:
            self.records.add_widget(wrapping_label("No family consumption recorded yet.", 14, MUTED, align="center"))
        for record in records:
            self.records.add_widget(self._record_card(record))

    @staticmethod
    def _record_title(record):
        unit = record["unit_snapshot"].lower()
        if record["quantity"] != 1:
            unit += "s"
        return f"{record['product_name_snapshot']} ({record['quantity']} {unit})"

    def _record_card(self, record):
        row = BoxLayout(size_hint_y=None, spacing=dp(6), padding=(dp(8), dp(8), dp(4), dp(8)))
        paint_surface(row, WHITE, radius=12, border=BORDER)
        row.add_widget(_icon_circle("cloche"))
        copy = _vertical(spacing=dp(3))
        copy.add_widget(wrapping_label(self._record_title(record), 14, bold=True))
        copy.add_widget(wrapping_label("Family Use", 12, AMOUNT))
        copy.add_widget(wrapping_label(local_timestamp(record["consumed_at"]), 12, MUTED))
        row.add_widget(copy)
        amount_holder = AnchorLayout(size_hint_x=.56)
        amount = wrapping_label(format_price(record["retail_value_centavos"]), 14, AMOUNT, bold=True, align="right")
        amount_holder.add_widget(amount)
        row.add_widget(amount_holder)
        menu = IconButton("dots", ORANGE, 18, size_hint_x=None, width=dp(38))
        menu.bind(on_release=lambda *_: self._record_menu(record))
        row.add_widget(menu)

        def fit(*_):
            row.height = max(dp(76), max(copy.height, amount.height) + dp(16))

        copy.bind(height=fit)
        amount.bind(height=fit)
        fit()
        return row

    def _record_menu(self, record):
        sheet = self._message(self._record_title(record), None)
        for title, callback in (("View Details", self._view_details), ("Delete Record", self._confirm_delete)):
            action = _Action(title, size_hint_y=None, height=dp(44))
            action.bind(on_release=lambda _, callback=callback: callback(record))
            sheet.copy.add_widget(action)

    def _view_details(self, record):
        message = (
            f"Family Use\n{local_timestamp(record['consumed_at'])}\n\n"
            f"Selling price per unit: {format_price(record['selling_price_centavos'])}\n"
            f"Estimated retail value: {format_price(record['retail_value_centavos'])}"
        )
        if record["remarks"]:
            message += f"\n\nRemarks\n{record['remarks']}"
        self._message(self._record_title(record), message)

    def _open_form(self, *_):
        try:
            products = self.consumption.products.list_products()
        except (OSError, sqlite3.Error) as error:
            Logger.warning("Consumption: Could not load products: %s", error)
            self._message("Add Consumption", "Could not load products. Try again.")
            return
        if not products:
            self._message("Add Consumption", "Add an active product before recording family consumption.")
            return
        prompt = "Choose product"
        options = {}
        for product in products:
            caption = product["name"]
            while caption == prompt or caption in options:
                caption += f" (#{product['id']})"
            options[caption] = product
        sheet = self._message("Add Consumption", None, confirmation="Cancel")

        def field(title, hint, value=""):
            sheet.copy.add_widget(wrapping_label(title, 14, bold=True))
            holder, control = _text_field(hint)
            control.text = value
            sheet.copy.add_widget(holder)
            return control

        sheet.copy.add_widget(wrapping_label("Product", 14, bold=True))
        choose = _dropdown(prompt, tuple(options), size_hint_y=None, height=dp(44), shorten=True)
        choose.bind(size=lambda widget, size: setattr(widget, "text_size", size))
        sheet.copy.add_widget(choose)
        quantity = field("Quantity", "0", "0")
        quantity.input_filter = "int"
        stamp = field("Date and Time (Philippine time)", "YYYY-MM-DD HH:MM",
                      datetime.now(PHILIPPINE_TIME).strftime("%Y-%m-%d %H:%M"))
        remarks = field("Remarks (optional)", "Enter remarks")
        preview = _card()
        summary = wrapping_label("", 13, AMOUNT)
        preview.add_widget(summary)
        sheet.copy.add_widget(preview)
        error = wrapping_label("", 13, AMOUNT)
        error.height = 0
        sheet.copy.add_widget(error)
        save = _Action("Save Consumption", primary=True, size_hint_y=None, height=dp(45))
        sheet.copy.add_widget(save)

        def selection():
            text = quantity.text.lstrip("0")
            units = int(text) if text.isascii() and text.isdecimal() and len(text) <= 19 else 0
            return options.get(choose.text), units

        def update(*_):
            product, units = selection()
            if product is None:
                summary.text = "Choose a product to preview consumption."
                save.disabled = True
                return
            stock = product["stock"]
            value = units * product["selling_price"]
            valid = 0 < units <= stock and value <= MAX_SQLITE_INTEGER
            caption = format_price(value) if units == 0 or valid else "—"
            summary.text = (
                f"{product['name']}\nQuantity: {units} · Available stock: {stock}\n"
                f"Estimated retail value: {caption}"
            )
            if units > stock:
                summary.text += "\nQuantity exceeds available stock."
            save.disabled = not valid

        def select_product(*_):
            if choose.text in options:
                quantity.text = "0"
            update()

        def submit(*_):
            if save.disabled or sheet.parent is None:
                return
            save.disabled = True
            product, units = selection()
            try:
                self.consumption.save(product["id"], units, stamp.text, remarks.text,
                                      expected_price=product["selling_price"])
            except ValueError as failure:
                error.text = str(failure)
            except (OSError, sqlite3.Error) as failure:
                Logger.warning("Consumption: Could not save: %s", failure)
                error.text = "Could not save consumption. Try again."
            else:
                sheet.dismiss()
                self.manager.get_screen("products")._refresh_products()
                self._changed("Consumption saved.")
                return
            update()

        def dismiss_fields(_, parent):
            if parent is None:
                choose.is_open = False
                for control in (quantity, stamp, remarks):
                    control.focus = False

        choose.bind(text=select_product)
        quantity.bind(text=update)
        sheet.bind(parent=dismiss_fields)
        save.bind(on_release=submit)
        update()

    def _confirm_delete(self, record):
        sheet = self._message(
            "Delete Record?",
            "This record will be removed from the list. Its estimated retail value and stock deduction will remain.",
            confirmation="Cancel",
        )
        action = _Action("Delete Record", primary=True, size_hint_y=None, height=dp(44))
        sheet.copy.add_widget(action)

        def submit(*_):
            if action.disabled or sheet.parent is None:
                return
            action.disabled = True
            try:
                self.consumption.archive(record["id"])
            except (ValueError, OSError, sqlite3.Error) as error:
                Logger.warning("Consumption: Could not archive record: %s", error)
                self._message("Delete Record", "Could not delete the record. Refresh and try again.")
                self.refresh()
            else:
                sheet.dismiss()
                self._changed("Consumption record removed.")

        action.bind(on_release=submit)

    def _changed(self, message):
        self.notice.text = message
        self.refresh()
        self.scroll.scroll_y = 1
        self.manager.get_screen("dashboard").refresh_financials()

    def _message(self, title, text, *, confirmation="Close"):
        self.search_input.focus = False
        if self.sheet:
            self.sheet.dismiss()
        self.sheet = BottomSheet(title, text, confirmation=confirmation)
        self.add_widget(self.sheet)
        return self.sheet

    def _go_home(self, *_):
        self.manager.current = "dashboard"
