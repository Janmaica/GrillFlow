from math import cos, pi, sin
from pathlib import Path

from kivy.graphics import Color, Ellipse, Line, Rectangle, RoundedRectangle
from kivy.metrics import dp, sp
from kivy.uix.anchorlayout import AnchorLayout
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.image import Image
from kivy.uix.label import Label
from kivy.uix.screenmanager import Screen
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput
from kivy.uix.widget import Widget

from screens.splash_screen import THEME_COLORS, _RoundedButton, _center_label


_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_LOGIN_BACKGROUND = _PROJECT_ROOT / "assets" / "images" / "login_pic.png"
_LOGO_PATH = _PROJECT_ROOT / "assets" / "images" / "grillflow_logo.png"
_FINGERPRINT_PATH = _PROJECT_ROOT / "assets" / "images" / "fingerprint.png"

_CREAM = (1, 248 / 255, 239 / 255, 1)
_TEXT_COLOR = (48 / 255, 37 / 255, 31 / 255, 1)
_MUTED_COLOR = (130 / 255, 112 / 255, 98 / 255, 1)


def _arc_points(center_x, center_y, radius_x, radius_y, start, end, steps=18):
    points = []
    for step in range(steps + 1):
        angle = (start + (end - start) * step / steps) * pi / 180
        points.extend(
            (
                center_x + radius_x * cos(angle),
                center_y + radius_y * sin(angle),
            )
        )
    return points


class _VectorIcon(Widget):
    def __init__(self, kind, color, slashed=False, **kwargs):
        super().__init__(**kwargs)
        self.kind = kind
        self.icon_color = color
        self.slashed = slashed
        self.bind(size=self._draw_icon, pos=self._draw_icon)
        self._draw_icon()

    def _draw_icon(self, *_):
        self.canvas.clear()
        if self.width <= 0 or self.height <= 0:
            return

        with self.canvas:
            self._draw_instructions()

    def _draw_instructions(self):
        x, y = self.pos
        width, height = self.size
        center_x = x + width / 2
        Color(*self.icon_color)

        if self.kind == "user":
            head_size = min(width, height) * 0.27
            Ellipse(
                pos=(center_x - head_size / 2, y + height * 0.61),
                size=(head_size, head_size),
            )
            Line(
                points=_arc_points(
                    center_x,
                    y + height * 0.2,
                    width * 0.37,
                    height * 0.34,
                    0,
                    180,
                ),
                width=dp(1.5),
            )
        elif self.kind == "lock":
            Line(
                points=[
                    x + width * 0.29, y + height * 0.48,
                    x + width * 0.29, y + height * 0.65,
                    x + width * 0.37, y + height * 0.82,
                    x + width * 0.5, y + height * 0.88,
                    x + width * 0.63, y + height * 0.82,
                    x + width * 0.71, y + height * 0.65,
                    x + width * 0.71, y + height * 0.48,
                ],
                width=dp(1.7),
            )
            RoundedRectangle(
                pos=(x + width * 0.19, y + height * 0.08),
                size=(width * 0.62, height * 0.48),
                radius=[dp(2)],
            )
            Color(*_CREAM)
            Ellipse(
                pos=(center_x - dp(1.7), y + height * 0.25),
                size=(dp(3.4), dp(3.4)),
            )
            Line(
                points=[
                    center_x, y + height * 0.25,
                    center_x, y + height * 0.17,
                ],
                width=dp(1.4),
            )
        elif self.kind == "eye":
            radius_x = width * 0.42
            radius_y = height * 0.32
            for direction in (1, -1):
                points = []
                for step in range(19):
                    fraction = step / 18
                    points.extend(
                        (
                            center_x - radius_x + 2 * radius_x * fraction,
                            y + height / 2
                            + direction * radius_y * sin(pi * fraction),
                        )
                    )
                Line(points=points, width=dp(1.5))
            pupil_size = min(width, height) * 0.22
            Ellipse(
                pos=(
                    center_x - pupil_size / 2,
                    y + height / 2 - pupil_size / 2,
                ),
                size=(pupil_size, pupil_size),
            )
            if self.slashed:
                Line(
                    points=(
                        x + width * 0.12, y + height * 0.12,
                        x + width * 0.88, y + height * 0.88,
                    ),
                    width=dp(1.5),
                )
class _IconButton(ButtonBehavior, FloatLayout):
    def __init__(self, kind, color, **kwargs):
        super().__init__(**kwargs)
        self.icon = _VectorIcon(
            kind,
            color,
            size_hint=(1, 1),
        )
        self.add_widget(self.icon)


class _InputRow(BoxLayout):
    def __init__(self, hint_text, icon, password=False, **kwargs):
        super().__init__(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(46),
            spacing=dp(8),
            padding=(dp(10), 0, dp(7), 0),
            **kwargs,
        )
        with self.canvas.before:
            Color(1, 1, 1, 1)
            self._shape = RoundedRectangle(radius=[dp(13)])
        self.bind(pos=self._update_shape, size=self._update_shape)

        icon_holder = AnchorLayout(
            size_hint=(None, 1),
            width=dp(26),
            anchor_x="center",
            anchor_y="center",
        )
        icon_holder.add_widget(
            _VectorIcon(
                icon,
                THEME_COLORS["deep_orange"],
                size_hint=(None, None),
                size=(dp(20), dp(20)),
            )
        )
        self.add_widget(icon_holder)
        self.input = TextInput(
            hint_text=hint_text,
            multiline=False,
            password=password,
            font_size=sp(16),
            foreground_color=_TEXT_COLOR,
            hint_text_color=_MUTED_COLOR,
            cursor_color=THEME_COLORS["primary_orange"],
            selection_color=(234 / 255, 88 / 255, 12 / 255, 0.35),
            background_normal="",
            background_active="",
            background_color=(0, 0, 0, 0),
            padding=(0, dp(9)),
            size_hint_x=1,
        )
        self.add_widget(self.input)

        self.eye_button = None
        if password:
            eye_holder = AnchorLayout(
                size_hint=(None, 1),
                width=dp(36),
                anchor_x="center",
                anchor_y="center",
            )
            self.eye_button = _IconButton(
                "eye",
                THEME_COLORS["deep_orange"],
                size_hint=(None, None),
                size=(dp(34), dp(34)),
            )
            self.eye_icon = self.eye_button.icon
            self.eye_holder = eye_holder
            eye_holder.add_widget(self.eye_button)
            self.add_widget(eye_holder)

    def _update_shape(self, *_):
        self._shape.pos = self.pos
        self._shape.size = self.size


class _LoginPanel(BoxLayout):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        with self.canvas.before:
            Color(*_CREAM)
            self._shape = RoundedRectangle(radius=[dp(26)])
        self.bind(pos=self._update_shape, size=self._update_shape)

    def _update_shape(self, *_):
        self._shape.pos = self.pos
        self._shape.size = self.size


class _FingerprintButton(ButtonBehavior, BoxLayout):
    def __init__(self, **kwargs):
        super().__init__(
            orientation="vertical",
            size_hint_y=None,
            height=dp(66),
            spacing=dp(1),
            **kwargs,
        )
        image_holder = AnchorLayout(
            size_hint=(1, None),
            height=dp(40),
            anchor_x="center",
            anchor_y="center",
        )
        self.image = Image(
            source=str(_FINGERPRINT_PATH),
            fit_mode="contain",
            size_hint=(None, None),
            size=(dp(40), dp(40)),
        )
        image_holder.add_widget(self.image)
        self.label = _center_label(
            Label(
                text="or Use Fingerprint",
                color=THEME_COLORS["deep_orange"],
                font_size=sp(14),
                size_hint_y=None,
                height=dp(24),
                halign="center",
                valign="middle",
            )
        )
        self.add_widget(image_holder)
        self.add_widget(self.label)


class LoginScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.background = Image(
            source=str(_LOGIN_BACKGROUND),
            fit_mode="cover",
            size_hint=(None, None),
        )
        self.add_widget(self.background)

        self.content = FloatLayout(size_hint=(None, None))
        self.add_widget(self.content)

        self._upper_shade = Widget(size_hint=(None, None))
        with self._upper_shade.canvas:
            Color(0, 0, 0, 0.2)
            self._shade_rect = Rectangle()
        self.content.add_widget(self._upper_shade)

        layout = BoxLayout(
            orientation="vertical",
            size_hint=(1, 1),
            padding=(dp(12), dp(10), dp(12), dp(28)),
        )
        self.content.add_widget(layout)

        back_holder = AnchorLayout(
            size_hint_y=None,
            height=dp(42),
            anchor_x="left",
            anchor_y="center",
        )
        back = Button(
            text="‹  Back",
            size_hint=(None, None),
            size=(dp(96), dp(42)),
            background_normal="",
            background_down="",
            background_color=(0, 0, 0, 0),
            color=THEME_COLORS["white"],
            font_size=sp(16),
            halign="left",
        )
        back.bind(on_release=self._return_to_splash)
        back_holder.add_widget(back)
        layout.add_widget(back_holder)
        self.back_holder = back_holder
        self.back_button = back

        branding = BoxLayout(
            orientation="vertical",
            size_hint=(1, None),
            height=dp(118),
        )
        logo_holder = AnchorLayout(
            size_hint=(1, None),
            height=dp(80),
            anchor_x="center",
            anchor_y="center",
        )
        brand_logo = Image(
            source=str(_LOGO_PATH),
            fit_mode="contain",
            size_hint=(None, None),
            size=(dp(105), dp(80)),
        )
        logo_holder.add_widget(brand_logo)
        title = _center_label(
            Label(
                text=(
                    "[b][color=#FFFFFF]Grill[/color]"
                    "[color=#FF6A00]Flow[/color][/b]"
                ),
                markup=True,
                font_size=sp(28),
                size_hint_y=None,
                height=dp(38),
                halign="center",
                valign="middle",
            )
        )
        branding.add_widget(logo_holder)
        branding.add_widget(title)
        layout.add_widget(branding)
        self.branding = branding
        self.logo_holder = logo_holder
        self.brand_logo = brand_logo
        self.brand_title = title

        self.username_row = _InputRow("Owner username", "user")
        self.pin_row = _InputRow("PIN / password", "lock", password=True)
        self.username_input = self.username_row.input
        self.pin_input = self.pin_row.input
        self.eye_button = self.pin_row.eye_button
        self.eye_icon = self.pin_row.eye_icon
        self.eye_button.bind(on_release=self._toggle_pin_visibility)

        self.status = _center_label(
            Label(
                text="",
                color=THEME_COLORS["deep_orange"],
                font_size=sp(13),
                size_hint_y=None,
                height=0,
                halign="center",
                valign="middle",
            )
        )

        form = BoxLayout(
            orientation="vertical",
            size_hint=(1, None),
            spacing=dp(7),
            padding=(dp(2), dp(10), dp(2), dp(10)),
        )
        form.bind(minimum_height=form.setter("height"))

        heading = _center_label(
            Label(
                text="Owner Login",
                color=_TEXT_COLOR,
                font_size=sp(22),
                bold=True,
                size_hint_y=None,
                height=dp(32),
                halign="center",
                valign="middle",
            )
        )
        login_button = _RoundedButton(
            text="Login",
            size_hint_y=None,
            height=dp(48),
        )
        login_button.bind(on_release=self._show_dashboard)
        self.login_button = login_button

        fingerprint = _FingerprintButton()
        fingerprint.bind(on_release=self._show_fingerprint_message)
        self.fingerprint_button = fingerprint

        for widget in (
            heading,
            self.username_row,
            self.pin_row,
            login_button,
            self.status,
            fingerprint,
        ):
            form.add_widget(widget)

        scroll = ScrollView(
            do_scroll_x=False,
            do_scroll_y=True,
            bar_width=0,
        )
        scroll.add_widget(form)
        panel = _LoginPanel(
            size_hint=(0.96, None),
            height=dp(1),
            padding=(dp(16), dp(12), dp(16), dp(12)),
        )
        panel.add_widget(scroll)
        panel_holder = AnchorLayout(
            size_hint_y=None,
            height=panel.height,
            anchor_x="center",
            anchor_y="center",
        )
        panel_holder.add_widget(panel)
        self.layout_spacer = Widget()
        layout.add_widget(self.layout_spacer)
        layout.add_widget(panel_holder)
        self.bottom_margin = Widget(
            size_hint_y=None,
            height=dp(28),
        )
        layout.add_widget(self.bottom_margin)

        self.layout = layout
        self.form = form
        self.scroll = scroll
        self.panel = panel
        self.panel_holder = panel_holder
        self.minimum_gap = dp(12)

        self.bind(pos=self._layout_content, size=self._layout_content)
        form.bind(minimum_height=self._update_panel_height)
        self._layout_content()
        self._update_panel_height()

    def _layout_content(self, *_):
        self.content.pos = self.pos
        self.content.size = self.size
        self.background.pos = self.pos
        self.background.size = self.size
        if self.height < dp(560):
            self.layout.padding = (dp(12), dp(6), dp(12), dp(14))
            self.back_holder.height = dp(36)
            self.back_button.height = dp(36)
            self.branding.height = dp(96)
            self.logo_holder.height = dp(64)
            self.brand_logo.size = (dp(84), dp(64))
            self.brand_title.height = dp(32)
            self.brand_title.font_size = sp(24)
            self.bottom_margin.height = dp(18)
            self.minimum_gap = dp(8)
        else:
            self.layout.padding = (dp(12), dp(10), dp(12), dp(28))
            self.back_holder.height = dp(42)
            self.back_button.height = dp(42)
            self.branding.height = dp(118)
            self.logo_holder.height = dp(80)
            self.brand_logo.size = (dp(105), dp(80))
            self.brand_title.height = dp(38)
            self.brand_title.font_size = sp(28)
            self.bottom_margin.height = dp(28)
            self.minimum_gap = dp(12)
        shade_height = self.height * 0.52
        self._upper_shade.pos = (self.x, self.y + self.height - shade_height)
        self._upper_shade.size = (self.width, shade_height)
        self._shade_rect.pos = self._upper_shade.pos
        self._shade_rect.size = self._upper_shade.size
        self._update_panel_height()

    def _update_panel_height(self, *_):
        if not hasattr(self, "panel"):
            return
        panel_padding = self.panel.padding
        desired_height = (
            self.form.minimum_height
            + panel_padding[1]
            + panel_padding[3]
        )
        reserved_height = (
            self.layout.padding[1]
            + self.back_holder.height
            + self.branding.height
            + self.layout.padding[3]
            + self.bottom_margin.height
            + self.minimum_gap
        )
        available_height = max(
            dp(180),
            self.height - reserved_height,
        )
        self.panel.height = min(desired_height, available_height)
        self.panel_holder.height = self.panel.height

    def _toggle_pin_visibility(self, *_):
        self.pin_input.password = not self.pin_input.password
        self.eye_icon.slashed = self.pin_input.password
        self.eye_icon._draw_icon()

    def _set_status(self, message):
        self.status.text = message
        self.status.height = dp(34) if message else 0

    def _show_dashboard(self, *_):
        # TODO: Replace this temporary development bypass with secure owner
        # authentication before production release.
        self.manager.current = "dashboard"

    def _show_fingerprint_message(self, *_):
        self._set_status("Fingerprint sign-in is Coming Soon.")

    def _return_to_splash(self, *_):
        if self.manager is None:
            raise RuntimeError(
                "Login screen must be attached to a ScreenManager"
            )
        self.manager.current = "splash"
