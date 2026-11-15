
from pathlib import Path

from kivy.graphics import Color, Rectangle, RoundedRectangle
from kivy.metrics import dp, sp
from kivy.uix.anchorlayout import AnchorLayout
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.image import Image
from kivy.uix.label import Label
from kivy.uix.screenmanager import Screen
from kivy.uix.widget import Widget


# ============================================================
# GRILLFLOW THEME COLORS
# ============================================================

THEME_COLORS = {
    "primary_orange": (234 / 255, 88 / 255, 12 / 255, 1),
    "bright_orange": (1, 106 / 255, 0, 1),
    "light_orange": (251 / 255, 146 / 255, 60 / 255, 1),
    "deep_orange": (194 / 255, 65 / 255, 12 / 255, 1),
    "white": (1, 1, 1, 1),
    "dark_background": (23 / 255, 17 / 255, 14 / 255, 1),
}


# ============================================================
# IMAGE PATHS
# ============================================================

_PROJECT_ROOT = Path(__file__).resolve().parents[1]

_BACKGROUND_PATH = (
    _PROJECT_ROOT / "assets" / "images" / "splash_background.png"
)

_LOGO_PATH = (
    _PROJECT_ROOT / "assets" / "images" / "grillflow_logo.png"
)


# ============================================================
# LABEL HELPER
# ============================================================

def _center_label(label):
    label.bind(
        size=lambda instance, size: setattr(
            instance, "text_size", size
        )
    )
    return label


# ============================================================
# BACKGROUND SCREEN
# ============================================================

class _BackdropScreen(Screen):

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        # Full-screen barbecue background
        self.background = Image(
            source=str(_BACKGROUND_PATH),
            fit_mode="cover",
            size_hint=(None, None),
        )

        self.add_widget(self.background)

        # Subtle dark overlay for text readability
        with self.background.canvas.after:
            Color(0, 0, 0, 0.18)
            self._shade = Rectangle()

        self.background.bind(
            pos=self._update_shade,
            size=self._update_shade
        )

        self.bind(
            pos=self._layout_background,
            size=self._layout_background
        )

        self._layout_background()

    def _layout_background(self, *_):
        self.background.pos = self.pos
        self.background.size = self.size
        self._update_shade()

    def _update_shade(self, *_):
        self._shade.pos = self.background.pos
        self._shade.size = self.background.size


# ============================================================
# ROUNDED ORANGE BUTTON
# ============================================================

class _RoundedButton(Button):

    def __init__(self, **kwargs):
        super().__init__(
            background_normal="",
            background_down="",
            background_color=(0, 0, 0, 0),
            border=(0, 0, 0, 0),
            color=THEME_COLORS["white"],
            bold=True,
            font_size=sp(18),
            **kwargs,
        )

        with self.canvas.before:
            self._fill_color = Color(
                *THEME_COLORS["primary_orange"]
            )

            self._shape = RoundedRectangle(
                radius=[dp(22)]
            )

        self.bind(
            pos=self._update_shape,
            size=self._update_shape
        )

        self.bind(
            state=self._update_color
        )

    def _update_shape(self, *_):
        self._shape.pos = self.pos
        self._shape.size = self.size

    def _update_color(self, *_):
        color = (
            THEME_COLORS["bright_orange"]
            if self.state == "down"
            else THEME_COLORS["primary_orange"]
        )

        self._fill_color.rgba = color


# ============================================================
# SPLASH SCREEN
# ============================================================

class SplashScreen(_BackdropScreen):

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        content = BoxLayout(
            orientation="vertical",
            size_hint=(None, None),
            padding=(
                dp(24),
                dp(24),
                dp(24),
                dp(18)
            ),
            spacing=dp(8),
        )

        # ----------------------------------------------------
        # OFFICIAL GRILLFLOW LOGO
        # ----------------------------------------------------

        logo_holder = AnchorLayout(
            anchor_x="center",
            anchor_y="center",
            size_hint=(1, None),
            height=dp(150),
        )

        # Transparent logo - NO background rectangle
        logo = Image(
            source=str(_LOGO_PATH),
            fit_mode="contain",
            size_hint=(None, None),
            size=(dp(170), dp(130)),
        )

        logo_holder.add_widget(logo)

        # ----------------------------------------------------
        # APPLICATION TITLE
        # ----------------------------------------------------

        title = _center_label(
            Label(
                text=(
                    "[b]"
                    "[color=#FFFFFF]Grill[/color]"
                    "[color=#FF6A00]Flow[/color]"
                    "[/b]"
                ),
                markup=True,
                font_size=sp(39),
                size_hint_y=None,
                height=dp(56),
                halign="center",
                valign="middle",
            )
        )

        # ----------------------------------------------------
        # APPLICATION TAGLINE
        # ----------------------------------------------------

        tagline = _center_label(
            Label(
                text="BBQ Business Manager",
                color=THEME_COLORS["white"],
                font_size=sp(16),
                size_hint_y=None,
                height=dp(28),
                halign="center",
                valign="middle",
            )
        )

        # ----------------------------------------------------
        # FOOTER
        # ----------------------------------------------------

        footer = _center_label(
            Label(
                text="Offline • Your BBQ Business, Organized",
                color=THEME_COLORS["white"],
                font_size=sp(12),
                size_hint_y=None,
                height=dp(24),
                halign="center",
                valign="middle",
            )
        )

        # ----------------------------------------------------
        # GET STARTED BUTTON
        # ----------------------------------------------------

        get_started = _RoundedButton(
            text="Get Started",
            size_hint_y=None,
            height=dp(58),
        )

        get_started.bind(
            on_release=self._show_login
        )

        # ----------------------------------------------------
        # ADD COMPONENTS
        # ----------------------------------------------------

        content.add_widget(logo_holder)
        content.add_widget(title)
        content.add_widget(tagline)

        # Flexible empty space
        content.add_widget(Widget())

        content.add_widget(get_started)
        content.add_widget(footer)

        self.add_widget(content)

        self._content = content

        self.bind(
            pos=self._layout_content,
            size=self._layout_content
        )

        self._layout_content()

    def _layout_content(self, *_):
        self._content.pos = self.pos
        self._content.size = self.size

    def _show_login(self, *_):
        if self.manager is None:
            raise RuntimeError(
                "Splash screen must be attached to a ScreenManager"
            )

        self.manager.current = "login"
