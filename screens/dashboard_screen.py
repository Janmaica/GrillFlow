from datetime import date, timedelta

from kivy.animation import Animation
from kivy.core.text import Label as CoreLabel
from kivy.graphics import Color, Ellipse, Line, Rectangle, RoundedRectangle
from kivy.graphics.texture import Texture
from kivy.metrics import dp, sp
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
from kivy.uix.widget import Widget

from screens.splash_screen import THEME_COLORS, _RoundedButton


ORANGE = THEME_COLORS["bright_orange"]
WHITE = THEME_COLORS["white"]
CREAM = (0.99, 0.95, 0.92, 1)
INK = (0.12, 0.09, 0.08, 1)
MUTED = (0.39, 0.37, 0.36, 1)
BORDER = (0.92, 0.87, 0.83, 1)
AMOUNT = (0.60, 0.17, 0.02, 1)
GREEN = (0.03, 0.40, 0.05, 1)

# Sample values and hourly totals for the UI preview. No business records are read.
SAMPLE_METRICS = (
    ("Total Sales", 3000, "cart",
     "Kinatibuk-ang kantidad sa imong gibaligya, apil ang giutang.",
     "Kung nakabaligya ka og 60 ka stick sa ₱50 matag usa, ₱3,000 ang halin."),
    ("Cash Collected", 2500, "wallet",
     "Kuwarta nga nadawat na nimo gikan sa mga bayad sa customer.",
     "Kung ₱3,000 ang halin ug ₱500 ang giutang, ₱2,500 ang imong nadawat."),
    ("Unpaid Credit", 500, "bill",
     "Kantidad nga utang pa sa mga customer.",
     "Kung giutang ang 10 ka stick sa ₱50 matag usa, ₱500 pa ang bayran."),
    ("Expenses", 400, "receipt",
     "Kuwarta nga gigasto para sa negosyo.",
     "Kung ₱300 ang karne ug ₱100 ang uling, ₱400 ang gasto."),
    ("Net Profit", 1400, "trend",
     "Kita nga nahibilin human ibawas sa halin ang tanang gasto sa negosyo.",
     "Kung ₱3,000 ang halin ug ₱1,600 ang tanang gasto, ₱1,400 ang kita."),
    ("Available Cash", 2100, "bars",
     "Kuwarta nga naa pa sa imong kaha ug magamit karon.",
     "Kung ₱2,500 ang nadawat ug ₱400 ang gibayad gikan sa kaha, ₱2,100 ang nahibilin."),
)
SAMPLE_SALES = (
    ("8AM", 900), ("10AM", 1500), ("12PM", 1050), ("2PM", 1450),
    ("4PM", 1950), ("6PM", 2500), ("8PM", 3000),
)

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

    @staticmethod
    def _dot(x, y, side, cx, cy):
        diameter = side * .12
        Ellipse(pos=(x + cx * side - diameter / 2, y + cy * side - diameter / 2),
                size=(diameter, diameter))


class IconButton(ButtonBehavior, AnchorLayout):
    def __init__(self, name, color, icon_size, **kwargs):
        super().__init__(**kwargs)
        self.add_widget(Icon(name, color, size_hint=(None, None), size=(dp(icon_size),) * 2))


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


class MetricCard(FloatLayout):
    def __init__(self, metric, show_info, **kwargs):
        super().__init__(**kwargs)
        title, amount, icon, _, _ = metric
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
        content.add_widget(label(
            f"₱{amount:,}", 24, GREEN if profit else AMOUNT, bold=True,
            size_hint_y=None, height=dp(29),
        ))
        self.add_widget(content)
        self.info_button = IconButton(
            "info", ORANGE, 16, size_hint=(None, None), size=(dp(44), dp(44)),
            pos_hint={"right": 1, "top": 1},
        )
        self.info_button.bind(on_release=lambda *_: show_info(metric))
        self.add_widget(self.info_button)


class SalesChart(Widget):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.bind(pos=self._draw, size=self._draw)

    @staticmethod
    def _caption(text, x, y, centered=False):
        caption = CoreLabel(text=text, font_size=sp(9))
        caption.refresh()
        texture = caption.texture
        Rectangle(texture=texture, size=texture.size,
                  pos=(x - texture.width / 2 if centered else x, y - texture.height / 2))

    def _draw(self, *_):
        self.canvas.clear()
        left, right = self.x + dp(25), self.right - dp(3)
        bottom, top = self.y + dp(18), self.top - dp(9)
        if right <= left or top <= bottom:
            return
        height = top - bottom
        slot = (right - left) / len(SAMPLE_SALES)
        bar_width = slot * .62
        with self.canvas:
            for index, tick in enumerate(("0", "1K", "2K", "3K")):
                y = bottom + height * index / 3
                Color(*BORDER)
                Line(points=(left, y, right, y), width=dp(.65))
                Color(*MUTED)
                self._caption(tick, self.x, y)
            for index, (hour, value) in enumerate(SAMPLE_SALES):
                x = left + slot * (index + .5)
                Color(*ORANGE)
                RoundedRectangle(pos=(x - bar_width / 2, bottom),
                                 size=(bar_width, height * value / 3000),
                                 radius=[dp(3), dp(3), 0, 0])
                Color(*INK)
                self._caption(hour, x, self.y + dp(6), centered=True)


class NavigationTab(ButtonBehavior, BoxLayout):
    def __init__(self, name, icon, active=False, **kwargs):
        super().__init__(orientation="vertical", padding=dp(5), spacing=dp(2), **kwargs)
        color = ORANGE if active else MUTED
        holder = AnchorLayout()
        holder.add_widget(Icon(icon, color, size_hint=(None, None), size=(dp(21), dp(21))))
        self.add_widget(holder)
        self.add_widget(label(name, 11, color, align="center", bold=active,
                              size_hint_y=None, height=dp(17)))


class BottomSheet(FloatLayout):
    def __init__(self, title, message, example=None, **kwargs):
        super().__init__(**kwargs)
        backdrop = Button(
            background_normal="", background_down="",
            background_color=(0, 0, 0, .55),
        )
        backdrop.bind(on_release=self.dismiss)
        self.add_widget(backdrop)

        self.panel = BoxLayout(
            orientation="vertical", size_hint=(1, None),
            padding=(dp(22), dp(15), dp(22), dp(20)), spacing=dp(10),
        )
        paint_surface(self.panel, WHITE, radius=24, top_only=True)

        scroll = ScrollView(do_scroll_x=False, bar_width=dp(2))
        copy = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(10))
        copy.bind(minimum_height=self._fit_panel)
        copy.bind(minimum_height=copy.setter("height"))
        paragraphs = [
            (title, 22, AMOUNT, True),
            (message, 16, INK, False),
        ]
        if example:
            paragraphs.append(("Pananglitan: " + example, 15, AMOUNT, False))
        for text, size, color, bold in paragraphs:
            paragraph = Label(
                text=text, size_hint_y=None, color=color, font_size=sp(size),
                bold=bold, halign="left", valign="top",
            )
            paragraph.bind(width=lambda widget, width: setattr(widget, "text_size", (width, None)))
            paragraph.bind(texture_size=lambda widget, size: setattr(widget, "height", size[1]))
            copy.add_widget(paragraph)
        scroll.add_widget(copy)
        self.panel.add_widget(scroll)
        close = _RoundedButton(text="Close", size_hint_y=None, height=dp(47))
        close.bind(on_release=self.dismiss)
        self.panel.add_widget(close)
        self.add_widget(self.panel)
        self.copy = copy
        self.bind(pos=self._place_panel, size=self._fit_panel)

    def _fit_panel(self, *_):
        self.panel.height = min(self.height, self.copy.minimum_height + dp(101))
        self._place_panel()

    def _place_panel(self, *_):
        self.panel.pos = (self.x, self.y)

    def on_parent(self, _, parent):
        if parent:
            self._fit_panel()
            # Animate from the lower edge without moving the scrim.
            self.panel.y = self.y - self.panel.height
            Animation(y=self.y, duration=.20, t="out_quad").start(self.panel)

    def dismiss(self, *_):
        if self.parent:
            self.parent.remove_widget(self)


class DashboardScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.selected_date = date.today()
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
        self._select_date(self.selected_date)

        self.metrics = GridLayout(cols=2, size_hint_y=None, spacing=dp(9),
                                  row_force_default=True)
        self.metrics.bind(minimum_height=self.metrics.setter("height"))
        for metric in SAMPLE_METRICS:
            self.metrics.add_widget(MetricCard(metric, self._show_metric))
        self.content.add_widget(self.metrics)

        self.trend = BoxLayout(
            orientation="vertical", size_hint_y=None, padding=(dp(12), dp(5), dp(10), dp(7)),
        )
        paint_surface(self.trend, WHITE, radius=13, border=BORDER)
        self.trend.add_widget(label("Sales Trend", 16, bold=True, size_hint_y=None, height=dp(25)))
        self.trend.add_widget(SalesChart())
        self.content.add_widget(self.trend)

        content_scroll.add_widget(self.content)
        shell.add_widget(content_scroll)
        shell.add_widget(self._build_navigation())
        self.add_widget(shell)
        content_scroll.bind(height=self._resize_content)
        self._resize_content(content_scroll, content_scroll.height)

    def _build_header(self):
        header = BoxLayout(size_hint_y=None, height=dp(57), spacing=dp(7),
                           padding=(dp(12), 0, dp(8), 0))
        gradient = Texture.create(size=(2, 1), colorfmt="rgb")
        gradient.blit_buffer(bytes((222, 79, 0, 255, 126, 0)), colorfmt="rgb", bufferfmt="ubyte")
        gradient.mag_filter = "linear"
        with header.canvas.before:
            Color(*WHITE)
            background = Rectangle(texture=gradient)
        def update(*_):
            background.pos, background.size = header.pos, header.size

        header.bind(pos=update, size=update)
        update()

        emblem = AnchorLayout(size_hint_x=None, width=dp(25))
        emblem.add_widget(Icon("flame", WHITE, size_hint=(None, None), size=(dp(24), dp(27))))
        header.add_widget(emblem)
        header.add_widget(label("GrillFlow", 23, WHITE, bold=True))
        self.bell_button = IconButton("bell", WHITE, 21, size_hint_x=None, width=dp(44))
        self.bell_button.bind(on_release=lambda *_: self._show_sheet("Notifications", "Coming Soon"))
        header.add_widget(self.bell_button)
        return header

    def _build_navigation(self):
        navigation = BoxLayout(size_hint_y=None, height=dp(58))
        paint_surface(navigation, WHITE, border=BORDER)
        self.tabs = {}
        for name, icon in (
            ("Home", "home"), ("Sales", "cart"), ("Products", "box"),
            ("Utang", "credit"), ("Reports", "trend"),
        ):
            tab = NavigationTab(name, icon, active=name == "Home")
            if name != "Home":
                tab.bind(on_release=lambda _, title=name: self._show_sheet(title, "Coming Soon"))
            self.tabs[name] = tab
            navigation.add_widget(tab)
        return navigation

    def _resize_content(self, _, height):
        self.metrics.row_default_height = max(dp(86), min(dp(132), height * .19))
        self.trend.height = max(dp(130), min(dp(200), height * .26))

    def on_pre_enter(self, *_):
        if self.selected_date == date.today() or self.date_button.text.startswith("Today"):
            self._select_date(date.today())

    def _select_date(self, selected):
        self.selected_date = selected
        prefix = "Today · " if selected == date.today() else ""
        self.date_button.text = f"{prefix}{selected:%b} {selected.day}, {selected.year}  v"

    def _open_date_selector(self, button):
        menu = DropDown(auto_width=False, width=dp(175))
        today = date.today()
        for title, selected in (("Today", today), ("Yesterday", today - timedelta(days=1))):
            option = Button(text=title, size_hint_y=None, height=dp(43))
            option.bind(on_release=lambda _, value=selected: menu.select(value))
            menu.add_widget(option)
        menu.bind(on_select=lambda _, value: self._select_date(value))
        menu.open(button)

    def _show_metric(self, metric):
        title, _, _, meaning, example = metric
        self._show_sheet(title, meaning, example)

    def _show_sheet(self, title, message, example=None):
        if self.sheet and self.sheet.parent:
            self.sheet.dismiss()
        self.sheet = BottomSheet(title, message, example)
        self.add_widget(self.sheet)
