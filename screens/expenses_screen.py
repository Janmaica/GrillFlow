import sqlite3
from datetime import datetime, timezone

from kivy.logger import Logger
from kivy.metrics import dp, sp
from kivy.uix.anchorlayout import AnchorLayout
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.screenmanager import Screen
from kivy.uix.scrollview import ScrollView
from kivy.uix.spinner import Spinner
from kivy.uix.textinput import TextInput

from expense_store import EXPENSE_CATEGORIES
from order_store import PHILIPPINE_TIME, parse_payment_amount, report_bounds
from product_store import format_price
from receipt_data import local_timestamp
from screens.add_product_screen import _UnitOption
from screens.dashboard_screen import (
    AMOUNT, BORDER, CREAM, INK, MUTED, ORANGE, WHITE, BottomSheet, Icon, IconButton,
    build_navigation, label, paint_header_gradient, paint_surface, wrapping_label,
)
from screens.new_order_screen import _Action, _card, _icon_holder, _text_field, _vertical
from screens.splash_screen import _RoundedButton


PERIODS = ("This Day", "This Week", "This Month")
CATEGORY_ICONS = {"All": "category_grid", "Ingredients": "ingredients", "Charcoal": "flame",
                  "Supplies": "box", "Others": "dots"}
PEACH = (1, .92, .85, 1)


def _dropdown(value, values, **kwargs):
    control = Spinner(
        text=value, values=values, option_cls=_UnitOption, font_size=sp(14), color=AMOUNT, bold=True,
        background_normal="", background_down="", background_color=(0, 0, 0, 0), **kwargs,
    )
    paint_surface(control, WHITE, radius=11, border=BORDER)
    return control


class _CategoryFilter(ButtonBehavior, BoxLayout):
    def __init__(self, name, selected):
        super().__init__(orientation="vertical", padding=(dp(2), dp(7)), spacing=dp(3))
        paint_surface(self, PEACH if selected else WHITE, radius=11, border=ORANGE if selected else BORDER)
        holder = AnchorLayout()
        holder.add_widget(Icon(CATEGORY_ICONS[name], ORANGE, size_hint=(None, None), size=(dp(22), dp(22))))
        self.add_widget(holder)
        self.add_widget(label(name, 11, AMOUNT if selected else INK, bold=selected, align="center",
                              size_hint_y=None, height=dp(18)))


class ExpensesScreen(Screen):
    def __init__(self, expenses, **kwargs):
        super().__init__(**kwargs)
        self.expenses = expenses
        self.category = "All"
        self.sheet = None

        shell = BoxLayout(orientation="vertical")
        paint_surface(shell, CREAM)
        header = BoxLayout(size_hint_y=None, height=dp(57), spacing=dp(5), padding=(dp(5), 0, dp(10), 0))
        paint_header_gradient(header)
        self.back_button = IconButton("back", WHITE, 22, size_hint_x=None, width=dp(44))
        self.back_button.bind(on_release=self._go_home)
        header.add_widget(self.back_button)
        header.add_widget(label("Expenses", 23, WHITE, bold=True))
        header.add_widget(_icon_holder("trend", WHITE, 30))
        shell.add_widget(header)

        scroll = ScrollView(do_scroll_x=False, bar_width=dp(3))
        self.content = _vertical(spacing=dp(10), padding=(dp(12), dp(11), dp(12), dp(12)))
        self.content.add_widget(self._summary())
        self.add_button = _RoundedButton(text="+  Add Expense", size_hint_y=None, height=dp(49))
        self.add_button.bind(on_release=lambda *_: self._open_form())
        self.content.add_widget(self.add_button)
        self.content.add_widget(wrapping_label("Expense Categories", 17, bold=True))
        self.content.add_widget(self._categories())
        self.content.add_widget(wrapping_label("Expense Records", 17, bold=True))
        holder, self.search_input = _text_field("Search expenses...")
        holder.add_widget(_icon_holder("search", MUTED, 27), index=len(holder.children))
        self.content.add_widget(holder)
        self.notice = wrapping_label("", 13, AMOUNT)
        self.notice.height = 0
        self.content.add_widget(self.notice)
        self.records = _vertical(spacing=dp(8))
        self.content.add_widget(self.records)
        scroll.add_widget(self.content)
        shell.add_widget(scroll)
        navigation, self.tabs = build_navigation(self, None, self._message)
        shell.add_widget(navigation)
        self.add_widget(shell)
        self.period.bind(text=self.refresh)
        self.search_input.bind(text=self.refresh)

    def _summary(self):
        card = BoxLayout(size_hint_y=None, height=dp(87), padding=(dp(10), dp(8)), spacing=dp(5))
        paint_surface(card, WHITE, radius=13, border=BORDER)
        card.add_widget(_icon_holder("receipt", ORANGE, 26))
        text = BoxLayout(orientation="vertical", spacing=dp(2))
        text.add_widget(label("Total Expenses", 14, bold=True))
        self.total = label("—", 21, AMOUNT, bold=True, shorten=True)
        text.add_widget(self.total)
        card.add_widget(text)
        holder = AnchorLayout(size_hint_x=None, width=dp(109))
        self.period = _dropdown(PERIODS[0], PERIODS, size_hint_y=None, height=dp(42))
        holder.add_widget(self.period)
        card.add_widget(holder)
        return card

    def _categories(self):
        scroll = ScrollView(size_hint_y=None, height=dp(61), do_scroll_y=False, bar_width=0)
        self.category_row = BoxLayout(spacing=dp(4), size_hint_x=None, padding=(dp(1), dp(2)))
        scroll.bind(width=lambda _, width: setattr(self.category_row, "width", max(width, dp(333))))
        scroll.add_widget(self.category_row)
        self._render_categories()
        return scroll

    def _render_categories(self):
        self.category_row.clear_widgets()
        for name in CATEGORY_ICONS:
            button = _CategoryFilter(name, name == self.category)
            button.bind(on_release=lambda _, name=name: self._select_category(name))
            self.category_row.add_widget(button)

    def _select_category(self, category):
        self.category = category
        self._render_categories()
        self.refresh()

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
            amount, any_expenses, rows = self.expenses.period_view(
                *report_bounds(self.period.text),
                category=None if self.category == "All" else self.category,
                search=self.search_input.text,
            )
        except (OSError, sqlite3.Error) as error:
            Logger.warning("Expenses: Could not load records: %s", error)
            self.total.text = "—"
            self.records.add_widget(wrapping_label("Could not load expenses. Try again.", 14, MUTED))
            return
        self.total.text = format_price(amount)
        if not rows:
            text = "No expenses found." if any_expenses else "No expenses recorded yet."
            self.records.add_widget(wrapping_label(text, 14, MUTED, align="center"))
        for row in rows:
            self.records.add_widget(self._record_card(row))

    def _record_card(self, expense):
        row = BoxLayout(size_hint_y=None, spacing=dp(6), padding=(dp(8), dp(8), dp(4), dp(8)))
        paint_surface(row, WHITE, radius=12, border=BORDER)
        avatar_holder = AnchorLayout(size_hint_x=None, width=dp(36))
        avatar = AnchorLayout(size_hint=(None, None), size=(dp(34), dp(34)))
        paint_surface(avatar, PEACH, radius=17)
        avatar.add_widget(Icon(CATEGORY_ICONS[expense["category"]], ORANGE,
                               size_hint=(None, None), size=(dp(19), dp(19))))
        avatar_holder.add_widget(avatar)
        row.add_widget(avatar_holder)
        copy = _vertical(spacing=dp(3))
        copy.add_widget(wrapping_label(expense["name"], 15, bold=True))
        for caption, icon in ((expense["category"], "tag"), (local_timestamp(expense["incurred_at"]), "calendar")):
            line = BoxLayout(size_hint_y=None, spacing=dp(3))
            line.add_widget(_icon_holder(icon, ORANGE, 16))
            text = wrapping_label(caption, 12, MUTED)
            text.bind(height=lambda _, height, line=line: setattr(line, "height", max(dp(17), height)))
            line.add_widget(text)
            copy.add_widget(line)
        amount_holder = AnchorLayout(size_hint_x=.62)
        amount = wrapping_label(format_price(expense["amount_centavos"]), 14, AMOUNT, bold=True, align="right")
        amount_holder.add_widget(amount)

        def fit(*_):
            row.height = max(dp(72), max(copy.height, amount.height) + dp(16))

        copy.bind(height=fit)
        amount.bind(height=fit)
        row.add_widget(copy)
        row.add_widget(amount_holder)
        menu = IconButton("dots", ORANGE, 18, size_hint_x=None, width=dp(36))
        menu.bind(on_release=lambda *_: self._record_menu(expense))
        row.add_widget(menu)
        fit()
        return row

    def _record_menu(self, expense):
        sheet = self._message(expense["name"], format_price(expense["amount_centavos"]))
        for title, action in (("Edit Expense", self._open_form), ("Delete Expense", self._confirm_delete)):
            button = _Action(title, size_hint_y=None, height=dp(44))
            button.bind(on_release=lambda _, action=action: action(expense))
            sheet.copy.add_widget(button)

    def _open_form(self, expense=None):
        sheet = self._message("Edit Expense" if expense else "Add Expense", None, confirmation="Cancel")

        def add_field(caption, hint, value):
            sheet.copy.add_widget(wrapping_label(caption, 14, bold=True))
            holder, field = _text_field(hint)
            field.text = value
            sheet.copy.add_widget(holder)
            return field

        name = add_field("Expense Name", "Enter expense name", expense["name"] if expense else "")
        sheet.copy.add_widget(wrapping_label("Category", 14, bold=True))
        category_row = _dropdown(expense["category"] if expense else "Choose category", EXPENSE_CATEGORIES,
                                 size_hint_y=None, height=dp(44))
        sheet.copy.add_widget(category_row)
        pesos, cents = divmod(expense["amount_centavos"], 100) if expense else (0, 0)
        amount = add_field("Amount (₱)", "0.00", f"{pesos}.{cents:02d}" if expense else "")
        stamp = datetime.now(PHILIPPINE_TIME)
        if expense:
            stamp = datetime.fromisoformat(expense["incurred_at"]).replace(tzinfo=timezone.utc)
            stamp = stamp.astimezone(PHILIPPINE_TIME)
        incurred = add_field("Date and Time (Philippine time)", "YYYY-MM-DD HH:MM",
                             stamp.strftime("%Y-%m-%d %H:%M:%S"))
        sheet.copy.add_widget(wrapping_label("Remarks (optional)", 14, bold=True))
        remarks_holder = BoxLayout(size_hint_y=None, height=dp(70))
        paint_surface(remarks_holder, CREAM, radius=10, border=BORDER)
        remarks = TextInput(text=expense["remarks"] if expense else "", multiline=True, font_size=sp(14),
                            padding=(dp(10), dp(8)), background_normal="", background_active="",
                            background_color=(0, 0, 0, 0), foreground_color=INK)
        remarks_holder.add_widget(remarks)
        sheet.copy.add_widget(remarks_holder)
        error = wrapping_label("", 13, AMOUNT)
        error.height = 0
        sheet.copy.add_widget(error)
        save = _Action("Save Expense", primary=True, size_hint_y=None, height=dp(45))
        sheet.copy.add_widget(save)

        def submit(*_):
            if save.disabled or sheet.parent is None:
                return
            save.disabled = True
            try:
                self.expenses.save(
                    name.text, category_row.text, parse_payment_amount(amount.text),
                    incurred.text, remarks.text, expense_id=expense["id"] if expense else None,
                )
            except ValueError as failure:
                error.text = str(failure)
            except (OSError, sqlite3.Error) as failure:
                Logger.warning("Expenses: Could not save: %s", failure)
                error.text = "Could not save the expense. Try again."
            else:
                sheet.dismiss()
                self._changed("Expense updated." if expense else "Expense saved.")
                return
            save.disabled = False

        def dismiss_fields(_, parent):
            if parent is None:
                for field in (name, amount, incurred, remarks):
                    field.focus = False
                category_row.is_open = False

        sheet.bind(parent=dismiss_fields)
        save.bind(on_release=submit)

    def _confirm_delete(self, expense):
        sheet = self._message(
            "Delete Expense?",
            f"{expense['name']} will be removed from the list. Its financial history will be preserved for reports.",
            confirmation="Cancel",
        )
        button = _Action("Delete Record", primary=True, size_hint_y=None, height=dp(44))
        sheet.copy.add_widget(button)

        def delete(*_):
            if button.disabled or sheet.parent is None:
                return
            button.disabled = True
            try:
                self.expenses.delete(expense["id"])
            except (ValueError, OSError, sqlite3.Error) as error:
                Logger.warning("Expenses: Could not delete: %s", error)
                self._message("Delete Expense", "Could not delete the expense. Refresh and try again.")
                self.refresh()
            else:
                sheet.dismiss()
                self._changed("Expense deleted.")

        button.bind(on_release=delete)

    def _changed(self, message):
        self.notice.text = message
        self.refresh()
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
