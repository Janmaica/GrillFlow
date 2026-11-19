
import sqlite3
from datetime import datetime, time, timedelta

from kivy.animation import Animation
from kivy.core.text import Label as CoreLabel
from kivy.graphics import Color, Ellipse, Line, Rectangle, RoundedRectangle
from kivy.graphics.texture import Texture
from kivy.metrics import dp, sp
from kivy.logger import Logger
from kivy.properties import NumericProperty
from kivy.uix.anchorlayout import AnchorLayout
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.dropdown import DropDown
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.screenmanager import Screen
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput
from kivy.uix.widget import Widget

from order_store import PHILIPPINE_TIME, history_bounds
from product_store import format_price
from screens.splash_screen import THEME_COLORS, _RoundedButton


ORANGE = THEME_COLORS["bright_orange"]
WHITE = THEME_COLORS["white"]
CREAM = (0.99, 0.95, 0.92, 1)
INK = (0.12, 0.09, 0.08, 1)
MUTED = (0.39, 0.37, 0.36, 1)
BORDER = (0.92, 0.87, 0.83, 1)
AMOUNT = (0.60, 0.17, 0.02, 1)
GREEN = (0.03, 0.40, 0.05, 1)

METRICS = (
    ("Total Sales", "cart"),
    ("Cash Collected", "wallet"),
    ("Unpaid Credit", "bill"),
    ("Expenses", "receipt"),
    ("Net Profit", "trend"),
    ("Family Consumption", "utensils"),
)

# Examples illustrate each metric independently of the dashboard card values.
METRIC_DETAILS = {
    "Total Sales": (
        "Kinatibuk-ang Halin",
        "Ang total nga kantidad sa tanang nahalin nga produkto, apil ang nabayran ug wala pa mabayri.",
        "Cash Sales ₱2,500 + Unpaid Sales ₱500 = Total Sales ₱3,000.",
    ),
    "Cash Collected": (
        "Kwarta nga Nadawat",
        "Ang aktuwal nga kwarta nga nadawat sa negosyo gikan sa mga bayad sa customers.",
        "Total Sales ₱3,000 - Unpaid Credit ₱500 = Cash Collected ₱2,500.",
    ),
    "Unpaid Credit": (
        "Utang nga Wala Pa Mabayri",
        "Ang kantidad sa halin nga wala pa mabayri sa mga customers.",
        "Total Sales ₱3,000 - Cash Collected ₱2,500 = Unpaid Credit ₱500.",
    ),
    "Expenses": (
        "Mga Gasto sa Negosyo",
        "Ang kwarta nga gigasto sa negosyo sama sa karne, uling, panakot, ug uban pang kinahanglanon.",
        "Ingredients ₱1,200 + Other Expenses ₱400 = Total Expenses ₱1,600.",
    ),
    "Net Profit": (
        "Pinal nga Kita sa Negosyo",
        "Ang tinuod nga kita sa negosyo human ibawas ang tanang gasto (puhunan ug ubang expenses).",
        (
            ("Total Sales (Halin)", "₱3,000"),
            ("Total Expenses (Gastos)", "₱1,600"),
            ("Net Profit", "₱1,400"),
        ),
    ),
    "Family Consumption": (
        "Gibanabanang Presyo sa Pagbaligya",
        "Ang Family Consumption mao ang mga produkto sa negosyo nga gigamit sa pamilya imbes ibaligya. "
        "Gibase ang kantidad sa presyo sa pagbaligya. Lahi kini sa halin ug aktuwal nga gasto sa negosyo.",
        "5 ka stick × ₱15 nga presyo sa pagbaligya = ₱75 nga gibanabanang retail value.",
    ),
}

# Icon paths use coordinates from 0 to 1 inside each icon.
ICON_PATHS = {
    "cart": ((.04,.86,.20,.86,.32,.34,.82,.34,.95,.72,.24,.72),
             (.38,.63,.43,.44,.73,.44,.80,.63), (.32,.24,.82,.24)),
    "wallet": ((.90,.56,.90,.76,.17,.76,.08,.66,.08,.24,.90,.24,.90,.43),
               (.20,.76,.27,.90,.75,.90,.82,.76),
               (.67,.43,.97,.43,.97,.60,.67,.60,.67,.43)),
    "bill": ((.06,.20,.94,.20,.94,.80,.06,.80,.06,.20),
             (.15,.64,.24,.71,.29,.71), (.85,.36,.76,.29,.71,.29)),
    "receipt": ((.23,.09,.77,.09,.77,.91,.23,.91,.23,.09),
                (.36,.70,.64,.70), (.36,.51,.64,.51), (.36,.32,.57,.32)),
    "trend": ((.07,.47,.39,.58,.57,.71,.91,.94,.70,.94), (.91,.94,.91,.75),
              (.16,.09,.16,.30), (.36,.09,.36,.39), (.57,.09,.57,.51), (.79,.09,.79,.65)),
    "bars": ((.14,.12,.14,.29), (.37,.12,.37,.43),
             (.60,.12,.60,.62), (.83,.12,.83,.89)),
    "home": ((.04,.48,.50,.90,.96,.48), (.20,.58,.20,.10,.41,.10,.41,.39,
             .60,.39,.60,.10,.80,.10,.80,.58)),
    "box": ((.10,.17,.90,.17,.90,.69,.77,.87,.23,.87,.10,.69,.10,.17),
            (.10,.69,.90,.69), (.50,.87,.50,.49)),
    "credit": ((.12,.15,.88,.15,.88,.86,.12,.86,.12,.15),
               (.28,.63,.70,.63,.57,.75), (.70,.63,.57,.51),
               (.70,.37,.28,.37,.41,.49), (.28,.37,.41,.25)),
    "bell": ((.10,.25,.24,.42,.25,.65,.31,.78,.45,.87,.57,.87,.70,.78,
             .77,.65,.77,.42,.90,.25,.10,.25), (.39,.14,.50,.08,.61,.14)),
    "flame": ((.49,.97,.58,.80,.57,.67,.70,.75,.76,.86,.87,.54,.86,.32,
               .71,.14,.53,.07,.34,.12,.17,.29,.14,.48,.29,.70,.30,.52,
               .42,.63,.50,.80,.49,.97),),
    "info": ((.50,.25,.50,.55),),
    "back": ((.88,.50,.13,.50,.45,.82), (.13,.50,.45,.18)),
    "check": ((.15,.49,.39,.25,.85,.76),),
    "mail": ((.08,.25,.92,.25,.92,.75,.08,.75,.08,.25), (.08,.75,.50,.44,.92,.75)),
    "lock": ((.20,.12,.80,.12,.80,.56,.20,.56,.20,.12),
             (.32,.56,.32,.73,.41,.83,.59,.83,.68,.73,.68,.56), (.50,.39,.50,.28)),
    "eye": ((.05,.50,.25,.70,.50,.76,.75,.70,.95,.50,.75,.30,.50,.24,.25,.30,.05,.50),),
    "eye_off": ((.05,.50,.25,.70,.50,.76,.75,.70,.95,.50,.75,.30,.50,.24,.25,.30,.05,.50),
                (.13,.83,.87,.17)),
    "search": ((.63,.37,.90,.10),),
    "plus": ((.20,.50,.80,.50), (.50,.20,.50,.80)),
    "camera": ((.08,.22,.92,.22,.92,.73,.68,.73,.61,.85,.39,.85,.32,.73,.08,.73,.08,.22),),
    "edit": ((.15,.15,.22,.41,.70,.89,.89,.70,.41,.22,.15,.15),
             (.60,.79,.79,.60)),
    "delete": ((.19,.76,.81,.76), (.38,.76,.38,.87,.62,.87,.62,.76),
               (.26,.70,.31,.16,.69,.16,.74,.70), (.43,.61,.43,.30), (.57,.61,.57,.30)),
    "chevron": ((.34,.80,.66,.50,.34,.20),),
    "menu": ((.12,.75,.88,.75), (.12,.50,.88,.50), (.12,.25,.88,.25)),
    "utensils": ((.18,.90,.18,.63,.32,.50,.46,.63,.46,.90),
                 (.32,.90,.32,.12), (.76,.12,.76,.90,.66,.78,.62,.60,.62,.45,.76,.45)),
    "family": ((.35,.72,.40,.82,.50,.85,.60,.82,.65,.72,.60,.62,.50,.59,.40,.62,.35,.72),
               (.23,.16,.25,.32,.34,.43,.66,.43,.75,.32,.77,.16,.23,.16),
               (.24,.74,.16,.77,.09,.70,.09,.61,.16,.55,.25,.58),
               (.76,.74,.84,.77,.91,.70,.91,.61,.84,.55,.75,.58),
               (.17,.43,.09,.39,.05,.27,.05,.20,.14,.20), (.83,.43,.91,.39,.95,.27,.95,.20,.86,.20)),
    "cloche": ((.07,.22,.93,.22), (.13,.36,.17,.50,.27,.64,.39,.73,.61,.73,.73,.64,
                 .83,.50,.87,.36,.13,.36), (.50,.73,.50,.85)),
    "category_grid": (),
    "dots": (),
    "ingredients": ((.10,.53,.90,.53,.82,.31,.67,.17,.33,.17,.18,.31,.10,.53),
                    (.50,.53,.35,.73,.20,.81,.27,.61,.50,.53,.65,.80,.80,.88,.73,.65,.50,.53)),
    "calendar": ((.12,.78,.88,.78,.88,.14,.12,.14,.12,.78),
                 (.12,.57,.88,.57), (.31,.68,.31,.89), (.69,.68,.69,.89)),
    "tag": ((.10,.53,.57,.11,.90,.44,.48,.86,.10,.86,.10,.53),),
    "person": ((.50,.48,.35,.55,.30,.69,.36,.83,.50,.89,.64,.83,.70,.69,.65,.55,.50,.48),
               (.13,.15,.17,.28,.30,.38,.70,.38,.83,.28,.87,.15)),
}


def label(text, size, color=INK, *, bold=False, align="left", **kwargs):
    widget = Label(
        text=text, font_size=sp(size), color=color, bold=bold,
        halign=align, valign="middle", **kwargs,
    )
    widget.bind(size=lambda instance, size: setattr(instance, "text_size", size))
    return widget


class Icon(Widget):
    def __init__(self, name, color, **kwargs):
        super().__init__(**kwargs)
        self.name = name
        self.color = color
        self.bind(pos=self._draw, size=self._draw)
        self._draw()

    def _draw(self, *_):
        self.canvas.clear()
        side = min(self.size)
        x, y = self.center_x - side / 2, self.center_y - side / 2
        with self.canvas:
            Color(*self.color)
            for path in ICON_PATHS[self.name]:
                points = [
                    (x if index % 2 == 0 else y) + coordinate * side
                    for index, coordinate in enumerate(path)
                ]
                Line(points=points, width=dp(1.2))
            if self.name == "info":
                Line(circle=(self.center_x, self.center_y, side * .43), width=dp(1))
                self._dot(x, y, side, .50, .72)
            elif self.name == "cart":
                self._dot(x, y, side, .40, .10)
                self._dot(x, y, side, .75, .10)
            elif self.name == "bill":
                Line(circle=(self.center_x, self.center_y, side * .14), width=dp(1))
            elif self.name == "search":
                Line(circle=(x + side * .43, y + side * .57, side * .29), width=dp(1.2))
            elif self.name == "camera":
                Line(circle=(self.center_x, y + side * .48, side * .16), width=dp(1.2))
            elif self.name == "category_grid":
                for cx, cy in ((.28, .28), (.72, .28), (.28, .72), (.72, .72)):
                    Line(circle=(x + side * cx, y + side * cy, side * .13), width=dp(1.2))
            elif self.name == "dots":
                for cx in (.22, .50, .78):
                    self._dot(x, y, side, cx, .50)
            elif self.name == "tag":
                self._dot(x, y, side, .30, .67)
            elif self.name == "eye":
                Line(circle=(self.center_x, self.center_y, side * .13), width=dp(1))

    @staticmethod
    def _dot(x, y, side, cx, cy):
        diameter = side * .12
        Ellipse(pos=(x + cx * side - diameter / 2, y + cy * side - diameter / 2),
                size=(diameter, diameter))


class IconButton(ButtonBehavior, AnchorLayout):
    def __init__(self, name, color, icon_size, **kwargs):
        super().__init__(**kwargs)
        self.icon = Icon(name, color, size_hint=(None, None), size=(dp(icon_size),) * 2)
        self.add_widget(self.icon)

    def set_icon(self, name):
        self.icon.name = name
        self.icon._draw()


def paint_surface(widget, fill, radius=0, border=None, top_only=False):
    corner = dp(radius)
    corners = [corner, corner, 0, 0] if top_only else [corner]
    with widget.canvas.before:
        if border:
            Color(*border)
            edge = RoundedRectangle(radius=corners)
        Color(*fill)
        background = RoundedRectangle(radius=corners)

    def update(*_):
        background.pos = widget.pos
        background.size = widget.size
        if border:
            edge.pos = (widget.x - dp(.5), widget.y - dp(1))
            edge.size = (widget.width + dp(1), widget.height + dp(1.5))

    widget.bind(pos=update, size=update)
    update()


def paint_header_gradient(header, radius=0):
    gradient = Texture.create(size=(2, 1), colorfmt="rgb")
    gradient.blit_buffer(bytes((222, 79, 0, 255, 126, 0)), colorfmt="rgb", bufferfmt="ubyte")
    gradient.mag_filter = "linear"
    with header.canvas.before:
        Color(*WHITE)
        if radius:
            background = RoundedRectangle(texture=gradient, radius=[dp(radius)])
        else:
            background = Rectangle(texture=gradient)

    def update(*_):
        background.pos, background.size = header.pos, header.size

    header.bind(pos=update, size=update)
    update()


class MetricCard(FloatLayout):
    def __init__(self, metric, show_info, **kwargs):
        super().__init__(**kwargs)
        title, icon = metric
        profit = title == "Net Profit"
        fill = (0.92, 0.99, 0.87, 1) if profit else WHITE
        edge = (0.78, 0.89, 0.71, 1) if profit else BORDER
        paint_surface(self, fill, radius=13, border=edge)

        content = BoxLayout(
            orientation="vertical", padding=(dp(13), dp(8), dp(9), dp(7)),
            pos_hint={"x": 0, "y": 0},
        )
        icon_row = AnchorLayout(anchor_x="left")
        icon_row.add_widget(Icon(icon, GREEN if profit else ORANGE,
                                 size_hint=(None, None), size=(dp(22), dp(22))))
        content.add_widget(icon_row)
        content.add_widget(label(title, 13, bold=True, size_hint_y=None, height=dp(19)))
        self.amount = label(
            "—", 24, GREEN if profit else AMOUNT, bold=True, shorten=True,
            size_hint_y=None, height=dp(29),
        )
        content.add_widget(self.amount)
        self.add_widget(content)
        self.info_button = IconButton(
            "info", ORANGE, 16, size_hint=(None, None), size=(dp(44), dp(44)),
            pos_hint={"right": 1, "top": 1},
        )
        self.info_button.bind(on_release=lambda *_: show_info(metric))
        self.add_widget(self.info_button)


class _ClickableMetricCard(ButtonBehavior, MetricCard):
    def __init__(self, metric, show_info, **kwargs):
        super().__init__(metric=metric, show_info=show_info, **kwargs)
        self.bind(on_release=lambda *_: show_info(metric))


class SalesChart(Widget):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.series = []
        self.bind(pos=self._draw, size=self._draw)

    def set_series(self, series):
        self.series = series
        self._draw()

    @staticmethod
    def _caption(text, x, y, centered=False):
        caption = CoreLabel(text=text, font_size=sp(9))
        caption.refresh()
        texture = caption.texture
        Rectangle(texture=texture, size=texture.size,
                  pos=(x - texture.width / 2 if centered else x, y - texture.height / 2))

    def _draw(self, *_):
        self.canvas.clear()
        left, right = self.x + dp(46), self.right - dp(10)
        bottom, top = self.y + dp(18), self.top - dp(9)
        if right <= left or top <= bottom:
            return
        height = top - bottom
        peak = max((amount for _, amount in self.series), default=0)
        if not peak:
            with self.canvas:
                Color(*MUTED)
                self._caption("No sales for this period.", self.center_x, self.center_y, centered=True)
            return
        ceiling = ((peak + 299) // 300) * 300
        slot = (right - left) / len(self.series)
        bar_width = slot * .62
        label_every = max(1, int(dp(44) / slot + .99))
        with self.canvas:
            for index in range(4):
                y = bottom + height * index / 3
                Color(*BORDER)
                Line(points=(left, y, right, y), width=dp(.65))
                Color(*MUTED)
                pesos = ceiling * index // 300
                tick = f"{pesos / 1000:.1f}k" if pesos >= 1000 else str(pesos)
                self._caption(tick, self.x, y)
            for index, (hour, value) in enumerate(self.series):
                x = left + slot * (index + .5)
                if value:
                    Color(*ORANGE)
                    Rectangle(pos=(x - bar_width / 2, bottom),
                              size=(bar_width, height * value / ceiling))
                if index % label_every == 0:
                    Color(*INK)
                    self._caption(hour, x, self.y + dp(6), centered=True)


class _DashboardAction(ButtonBehavior, BoxLayout):
    def __init__(self, title, subtitle, icon):
        super().__init__(orientation="vertical", padding=(dp(10), dp(8)), spacing=dp(3))
        paint_surface(self, WHITE, radius=13, border=BORDER)
        holder = AnchorLayout(anchor_x="left", size_hint_y=None, height=dp(24))
        holder.add_widget(Icon(icon, ORANGE, size_hint=(None, None), size=(dp(22), dp(22))))
        self.add_widget(holder)
        self.add_widget(label(title, 14, bold=True, size_hint_y=None, height=dp(22)))
        self.add_widget(label(subtitle, 12, MUTED))
        self.bind(state=self._show_press)

    def _show_press(self, _, state):
        self.opacity = .8 if state == "down" else 1


class NavigationTab(ButtonBehavior, BoxLayout):
    def __init__(self, name, icon, active=False, **kwargs):
        super().__init__(orientation="vertical", padding=dp(5), spacing=dp(2), **kwargs)
        color = ORANGE if active else MUTED
        holder = AnchorLayout()
        holder.add_widget(Icon(icon, color, size_hint=(None, None), size=(dp(21), dp(21))))
        self.add_widget(holder)
        self.add_widget(label(name, 11, color, align="center", bold=active,
                              size_hint_y=None, height=dp(17)))


def build_navigation(screen, active, show_message):
    navigation = BoxLayout(size_hint_y=None, height=dp(58))
    paint_surface(navigation, WHITE, border=BORDER)
    tabs = {}
    routes = {"Home": "dashboard", "Sales": "sales", "Products": "products", "Utang": "utang",
              "Reports": "reports"}

    def select(_, name):
        if name in routes:
            screen.manager.current = routes[name]
        else:
            show_message(name, "Coming Soon")

    for name, icon in (
        ("Home", "home"), ("Sales", "cart"), ("Products", "box"),
        ("Utang", "credit"), ("Reports", "trend"),
    ):
        tab = NavigationTab(name, icon, active=name == active)
        if name != active:
            tab.bind(on_release=lambda button, name=name: select(button, name))
        tabs[name] = tab
        navigation.add_widget(tab)
    return navigation, tabs


def wrapping_label(text, size, color=INK, *, bold=False, align="left"):
    widget = Label(
        text=text, size_hint_y=None, color=color, font_size=sp(size),
        bold=bold, halign=align,
    )
    widget.bind(width=lambda instance, width: setattr(instance, "text_size", (width, None)))
    widget.bind(texture_size=lambda instance, size: setattr(instance, "height", size[1]))
    return widget


class BottomSheet(FloatLayout):
    reveal = NumericProperty(0)

    def __init__(self, title, message, *, confirmation="Close", **kwargs):
        super().__init__(**kwargs)
        self.backdrop = Button(
            background_normal="", background_down="",
            background_color=(0, 0, 0, .55), pos_hint={"x": 0, "y": 0},
        )
        self.backdrop.bind(on_release=self.dismiss)
        self.add_widget(self.backdrop)

        self.panel = BoxLayout(
            orientation="vertical", size_hint=(1, None),
            padding=(dp(22), dp(15), dp(22), dp(20)), spacing=dp(10),
        )
        paint_surface(self.panel, WHITE, radius=24, top_only=True)

        scroll = ScrollView(do_scroll_x=False, bar_width=dp(2))
        self.copy = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(10))
        self.copy.bind(minimum_height=self.copy.setter("height"))
        self.copy.bind(minimum_height=self._fit_panel)
        if title:
            self.copy.add_widget(wrapping_label(title, 22, AMOUNT, bold=True))
        if message:
            self.copy.add_widget(wrapping_label(message, 16))
        scroll.add_widget(self.copy)
        self.panel.add_widget(scroll)
        self.confirm_button = _RoundedButton(text=confirmation, size_hint_y=None, height=dp(47))
        self.confirm_button.bind(on_release=self.dismiss)
        self.panel.add_widget(self.confirm_button)
        self.add_widget(self.panel)
        self.bind(pos=self._place_panel, size=self._fit_panel, reveal=self._place_panel)

    def _fit_panel(self, *_):
        _, top, _, bottom = self.panel.padding
        reserved = top + bottom + self.confirm_button.height
        reserved += self.panel.spacing * (len(self.panel.children) - 1)
        if hasattr(self, "handle_row"):
            reserved += self.handle_row.height
        self.panel.height = min(max(0, self.height - dp(12)), self.copy.minimum_height + reserved)
        self._place_panel()

    def _place_panel(self, *_):
        self.panel.pos = (self.x, self.y - self.panel.height * (1 - self.reveal))

    def on_parent(self, _, parent):
        if parent:
            self._fit_panel()
            Animation(reveal=1, duration=.24, t="out_cubic").start(self)

    def on_touch_down(self, touch):
        if self.panel.collide_point(*touch.pos):
            self.panel.on_touch_down(touch)
        elif not touch.is_mouse_scrolling:
            self.backdrop.on_touch_down(touch)
        return True

    def on_touch_move(self, touch):
        super().on_touch_move(touch)
        return True

    def on_touch_up(self, touch):
        super().on_touch_up(touch)
        return True

    def dismiss(self, *_):
        if self.parent:
            Animation.cancel_all(self, "reveal")
            self.parent.remove_widget(self)


class FinancialInfoBottomSheet(BottomSheet):
    def __init__(self, title, icon, subtitle, explanation, example, **kwargs):
        super().__init__(None, None, confirmation="Nasabtan na nako", **kwargs)
        self.panel.padding = (dp(20), dp(10), dp(20), dp(20))
        self.handle_row = AnchorLayout(size_hint_y=None, height=dp(8))
        handle = Widget(size_hint=(None, None), size=(dp(42), dp(4)))
        paint_surface(handle, (0.72, 0.70, 0.70, 1), radius=2)
        self.handle_row.add_widget(handle)
        self.panel.add_widget(self.handle_row, index=len(self.panel.children))

        heading = BoxLayout(size_hint_y=None, height=dp(55), spacing=dp(12))
        icon_holder = AnchorLayout(size_hint_x=None, width=dp(54))
        circle = AnchorLayout(size_hint=(None, None), size=(dp(50), dp(50)))
        paint_surface(circle, (1, .91, .78, 1), radius=25)
        circle.add_widget(Icon(icon, ORANGE, size_hint=(None, None), size=(dp(26), dp(26))))
        icon_holder.add_widget(circle)
        heading.add_widget(icon_holder)
        heading.add_widget(label(title, 23, INK, bold=True))
        self.copy.add_widget(heading)

        badge = BoxLayout(size_hint_y=None, padding=(dp(10), dp(6)))
        paint_surface(badge, (1, .89, .75, 1), radius=10)
        badge.bind(minimum_height=badge.setter("height"))
        badge.add_widget(wrapping_label(subtitle, 15, AMOUNT, bold=True, align="center"))
        self.copy.add_widget(badge)
        self.copy.add_widget(wrapping_label(explanation, 16))
        self.copy.add_widget(self._example_box(example))

    @staticmethod
    def _example_box(example):
        box = BoxLayout(
            orientation="vertical", size_hint_y=None, spacing=dp(4),
            padding=(dp(12), dp(10)),
        )
        paint_surface(box, (1, .92, .80, 1), radius=13)
        box.bind(minimum_height=box.setter("height"))
        box.add_widget(wrapping_label("Pananglitan:", 16, AMOUNT, bold=True))
        if isinstance(example, str):
            box.add_widget(wrapping_label(example, 14))
            return box

        for index, (caption, amount) in enumerate(example):
            total = index == len(example) - 1
            if total:
                divider = Widget(size_hint_y=None, height=dp(1))
                paint_surface(divider, (.91, .76, .59, 1))
                box.add_widget(divider)
            row = BoxLayout(size_hint_y=None, height=dp(21))
            row.add_widget(label(caption, 14, bold=total))
            row.add_widget(label(
                amount, 16 if total else 14, AMOUNT if total else INK,
                bold=total, align="right", size_hint_x=.34,
            ))
            box.add_widget(row)
        return box


class DashboardScreen(Screen):
    def __init__(self, orders, expenses, consumption, **kwargs):
        super().__init__(**kwargs)
        self.orders = orders
        self.expenses = expenses
        self.consumption = consumption
        self.selected_date = datetime.now(PHILIPPINE_TIME).date()
        self.sheet = None

        shell = BoxLayout(orientation="vertical")
        paint_surface(shell, CREAM)
        shell.add_widget(self._build_header())

        content_scroll = ScrollView(do_scroll_x=False, bar_width=0)
        self.content = BoxLayout(
            orientation="vertical", size_hint_y=None, spacing=dp(9),
            padding=(dp(12), dp(4), dp(12), dp(10)),
        )
        self.content.bind(minimum_height=self.content.setter("height"))
        self.date_button = Button(
            size_hint_y=None, height=dp(36), background_color=(0, 0, 0, 0),
            color=INK, bold=True, font_size=sp(13), halign="left", valign="middle",
            padding=(dp(7), 0),
        )
        self.date_button.bind(size=lambda widget, size: setattr(widget, "text_size", size))
        self.date_button.bind(on_release=self._open_date_selector)
        self.content.add_widget(self.date_button)

        self.metrics = GridLayout(cols=2, size_hint_y=None, spacing=dp(9),
                                  row_force_default=True)
        self.metrics.bind(minimum_height=self.metrics.setter("height"))
        self.metric_cards = {}
        for metric in METRICS:
            card_type = _ClickableMetricCard if metric[0] == "Family Consumption" else MetricCard
            card = card_type(metric, self._show_metric)
            self.metric_cards[metric[0]] = card
            self.metrics.add_widget(card)
        self.content.add_widget(self.metrics)
        self.content.add_widget(self._build_quick_actions())

        self.trend = BoxLayout(
            orientation="vertical", size_hint_y=None, padding=(dp(12), dp(5), dp(10), dp(7)),
        )
        paint_surface(self.trend, WHITE, radius=13, border=BORDER)
        self.trend.add_widget(label("Sales Trend", 16, bold=True, size_hint_y=None, height=dp(25)))
        self.chart = SalesChart()
        self.trend.add_widget(self.chart)
        self.content.add_widget(self.trend)

        content_scroll.add_widget(self.content)
        shell.add_widget(content_scroll)
        navigation, self.tabs = build_navigation(self, "Home", self._show_sheet)
        shell.add_widget(navigation)
        self.add_widget(shell)
        content_scroll.bind(height=self._resize_content)
        self._resize_content(content_scroll, content_scroll.height)

    def _build_header(self):
        header = BoxLayout(size_hint_y=None, height=dp(57), spacing=dp(7),
                           padding=(dp(12), 0, dp(8), 0))
        paint_header_gradient(header)

        emblem = AnchorLayout(size_hint_x=None, width=dp(25))
        emblem.add_widget(Icon("flame", WHITE, size_hint=(None, None), size=(dp(24), dp(27))))
        header.add_widget(emblem)
        header.add_widget(label("GrillFlow", 23, WHITE, bold=True))
        self.menu_button = IconButton("menu", WHITE, 21, size_hint_x=None, width=dp(44))
        self.menu_button.bind(on_release=self._open_owner_menu)
        header.add_widget(self.menu_button)
        return header

    def _build_quick_actions(self):
        section = BoxLayout(orientation="vertical", size_hint_y=None, height=dp(119), spacing=dp(5))
        section.add_widget(label("Quick Actions", 16, bold=True, size_hint_y=None, height=dp(23)))
        row = BoxLayout(spacing=dp(9))
        for title, subtitle, icon in (
            ("Record Expense", "Business spending", "receipt"),
            ("Family Consumption", "Items for family use", "utensils"),
        ):
            action = _DashboardAction(title, subtitle, icon)
            if title == "Record Expense":
                action.bind(on_release=self._open_expenses)
            else:
                action.bind(on_release=self._open_consumption)
            row.add_widget(action)
        section.add_widget(row)
        return section

    def _open_expenses(self, *_):
        self.manager.current = "expenses"

    def _open_consumption(self, *_):
        self.manager.current = "family_consumption"

    def _open_owner_menu(self, *_):
        sheet = BottomSheet("Menu", None)
        for text, action in (
            ("My Profile", self._open_profile),
            ("Reset All Data", self._confirm_reset),
        ):
            button = _RoundedButton(text=text, size_hint_y=None, height=dp(44))
            button.bind(on_release=action)
            sheet.copy.add_widget(button)
        self._open_sheet(sheet)

    def _open_profile(self, *_):
        if self.sheet:
            self.sheet.dismiss()
        self.manager.current = "profile"

    def _confirm_reset(self, *_):
        sheet = BottomSheet(
            "Reset GrillFlow?",
            "This will permanently delete all products, orders, order history, customers, payments, "
            "credit balances, expenses, family consumption, and reporting records. This action cannot be undone.\n\n"
            "Type RESET to continue. A local SQLite backup will be saved before any records are deleted.",
            confirmation="Cancel",
        )
        field_holder = BoxLayout(size_hint_y=None, height=dp(44))
        paint_surface(field_holder, CREAM, radius=10, border=BORDER)
        phrase = TextInput(
            hint_text="RESET", multiline=False, font_size=sp(16), padding=(dp(10), dp(10)),
            background_normal="", background_active="", background_color=(0, 0, 0, 0),
            foreground_color=INK,
        )
        field_holder.add_widget(phrase)
        sheet.copy.add_widget(field_holder)
        confirm = _RoundedButton(text="Confirm Reset", size_hint_y=None, height=dp(46))
        confirm.disabled = True
        sheet.copy.add_widget(confirm)
        phrase.bind(text=lambda _, value: setattr(confirm, "disabled", value != "RESET"))
        sheet.bind(parent=lambda _, parent: setattr(phrase, "focus", False) if parent is None else None)

        def submit(*_):
            if confirm.disabled or sheet.parent is None or phrase.text != "RESET":
                return
            confirm.disabled = sheet.confirm_button.disabled = True
            phrase.disabled = True
            phrase.focus = False
            try:
                result = self.orders.reset_all_data()
            except (OSError, sqlite3.Error) as error:
                Logger.warning("Dashboard: Reset failed: %s", error)
                self._show_sheet("Reset Failed", "No business records were cleared. Check storage access and try again.")
                return
            sheet.dismiss()
            self._refresh_after_reset()
            message = f"Business data cleared.\n\nSQLite backup: {result.backup_path}"
            if result.photo_cleanup_failed:
                message += "\n\nSome uploaded photos could not be removed."
            self._show_sheet("Reset Complete", message)

        confirm.bind(on_release=submit)
        self._open_sheet(sheet)

    def _refresh_after_reset(self):
        for name in ("products", "sales", "new_order", "receipt", "order_history", "utang",
                     "reports", "expenses", "family_consumption"):
            screen = self.manager.get_screen(name)
            if screen.sheet:
                screen.sheet.dismiss()
                screen.sheet = None
        products = self.manager.get_screen("products")
        products.search_input.text = ""
        products.hide_notice.cancel()
        products._hide_notice()
        products._refresh_products()
        self.manager.get_screen("sales")._refresh_orders()
        draft = self.manager.get_screen("new_order")
        if draft.customer_dropdown is not None:
            draft.customer_dropdown.dismiss()
        draft.reset_after_sale()
        draft._reload_products()
        edit = self.manager.get_screen("add_product")
        edit.editing = None
        edit.on_pre_enter()
        payment = self.manager.get_screen("payment")
        payment.draft.lines.clear()
        payment.customer = ""
        payment.details.clear_widgets()
        payment.remarks_input.text = ""
        payment.amount_input.text = ""
        payment.save_button.disabled = True
        receipt = self.manager.get_screen("receipt")
        receipt.receipt = None
        receipt.paper.clear_widgets()
        receipt.print_button.disabled = receipt.share_button.disabled = True
        history = self.manager.get_screen("order_history")
        history._set_notice("")
        history._refresh()
        utang = self.manager.get_screen("utang")
        utang.expanded.clear()
        utang.search.text = ""
        utang._refresh()
        self.manager.get_screen("reports")._refresh()
        self.manager.get_screen("expenses").refresh()
        consumption = self.manager.get_screen("family_consumption")
        consumption.notice.text = ""
        consumption.search_input.text = ""
        consumption.period.text = "This Day"
        consumption.refresh()
        self._select_date(datetime.now(PHILIPPINE_TIME).date())

    def _resize_content(self, _, height):
        self.metrics.row_default_height = max(dp(86), min(dp(132), height * .19))
        self.trend.height = max(dp(130), min(dp(200), height * .26))

    def on_pre_enter(self, *_):
        today = datetime.now(PHILIPPINE_TIME).date()
        try:
            self.orders.initialize()
        except (OSError, sqlite3.Error) as error:
            Logger.warning("Dashboard: Could not initialize financial records: %s", error)
        self._select_date(today if self.date_button.text.startswith("Today") or not self.date_button.text
                          else self.selected_date)

    def _select_date(self, selected):
        self.selected_date = selected
        prefix = "Today · " if selected == datetime.now(PHILIPPINE_TIME).date() else ""
        self.date_button.text = f"{prefix}{selected:%b} {selected.day}, {selected.year}  v"
        self.refresh_financials()

    def refresh_financials(self):
        date_in_manila = datetime.combine(self.selected_date, time.min, tzinfo=PHILIPPINE_TIME)
        titles = ("Total Sales", "Cash Collected", "Unpaid Credit")
        try:
            bounds = history_bounds("Today", date_in_manila)
            totals = self.orders.financial_totals(*bounds)
            series = self.orders.sales_trend(*bounds, hourly=True)
        except (OSError, sqlite3.Error) as error:
            Logger.warning("Dashboard: Could not load financial totals: %s", error)
            totals = (None,) * len(titles)
            series = []
        for title, value in zip(titles, totals):
            self.metric_cards[title].amount.text = "—" if value is None else format_price(value)
        try:
            expense_text = format_price(self.expenses.total(*bounds))
        except (OSError, sqlite3.Error) as error:
            Logger.warning("Dashboard: Could not load expenses: %s", error)
            expense_text = "—"
        self.metric_cards["Expenses"].amount.text = expense_text
        try:
            consumption_text = format_price(self.consumption.total(*bounds))
        except (OSError, sqlite3.Error) as error:
            Logger.warning("Dashboard: Could not load family consumption: %s", error)
            consumption_text = "—"
        self.metric_cards["Family Consumption"].amount.text = consumption_text
        self.chart.set_series(series)

    def _open_date_selector(self, button):
        menu = DropDown(auto_width=False, width=dp(175))
        today = datetime.now(PHILIPPINE_TIME).date()
        for title, selected in (("Today", today), ("Yesterday", today - timedelta(days=1))):
            option = Button(text=title, size_hint_y=None, height=dp(43))
            option.bind(on_release=lambda _, value=selected: menu.select(value))
            menu.add_widget(option)
        menu.bind(on_select=lambda _, value: self._select_date(value))
        menu.open(button)

    def _show_metric(self, metric):
        title, icon = metric
        self._open_sheet(FinancialInfoBottomSheet(title, icon, *METRIC_DETAILS[title]))

    def _show_sheet(self, title, message):
        self._open_sheet(BottomSheet(title, message))

    def _open_sheet(self, sheet):
        if self.sheet and self.sheet.parent:
            self.sheet.dismiss()
        self.sheet = sheet
        self.add_widget(sheet)
