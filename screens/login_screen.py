"""Shared layouts for the owner authentication screens."""

from pathlib import Path

from kivy.metrics import dp, sp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.image import Image
from kivy.uix.screenmanager import Screen
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput

from screens.dashboard_screen import (
    AMOUNT, BORDER, CREAM, INK, MUTED, ORANGE, WHITE, IconButton, label, paint_surface, wrapping_label,
)
from screens.new_order_screen import _Action, _icon_holder, _vertical
from screens.splash_screen import _RoundedButton


LOGO = Path(__file__).resolve().parents[1] / "assets" / "images" / "grillflow_logo.png"


class _AuthScreen(Screen):
    def __init__(self, auth, title, subtitle, *, back, **kwargs):
        super().__init__(**kwargs)
        self.auth = auth
        self.fields = []
        self.password_fields = []
        self.actions = []
        self.email = None
        shell = BoxLayout(orientation="vertical")
        paint_surface(shell, CREAM)
        header = BoxLayout(size_hint_y=None, height=dp(48), padding=(dp(7), 0))
        arrow = IconButton("back", ORANGE, 22, size_hint_x=None, width=dp(44))
        arrow.bind(on_release=lambda *_: auth.show(back))
        self.actions.append(arrow)
        header.add_widget(arrow)
        shell.add_widget(header)
        self.scroll = ScrollView(do_scroll_x=False, bar_width=dp(3))
        self.form = _vertical(spacing=dp(9), padding=(dp(23), dp(4), dp(23), dp(20)))
        self.form.add_widget(Image(source=str(LOGO), fit_mode="contain", size_hint_y=None, height=dp(74)))
        self.form.add_widget(wrapping_label(title, 26, INK, bold=True, align="center"))
        self.form.add_widget(wrapping_label(subtitle, 14, MUTED, align="center"))
        self.notice = wrapping_label("", 13, AMOUNT, align="center")
        self.scroll.add_widget(self.form)
        shell.add_widget(self.scroll)
        self.add_widget(shell)

    def field(self, caption, icon, *, secret=False, email=False):
        self.form.add_widget(label(caption, 13, INK, bold=True, size_hint_y=None, height=dp(18)))
        row = BoxLayout(size_hint_y=None, height=dp(48), padding=(dp(4), 0))
        paint_surface(row, WHITE, radius=11, border=BORDER)
        row.add_widget(_icon_holder(icon, ORANGE, 33))
        field = TextInput(
            multiline=False, password=secret, hint_text=caption, font_size=sp(15), write_tab=False,
            input_type="mail" if email else "text", keyboard_suggestions=not (secret or email),
            allow_copy=not secret,
            padding=(dp(4), dp(13)),
            background_normal="", background_active="", background_color=(0, 0, 0, 0),
            foreground_color=INK, hint_text_color=MUTED, cursor_color=ORANGE,
        )
        row.add_widget(field)
        if secret:
            toggle = IconButton("eye", ORANGE, 20, size_hint_x=None, width=dp(44))

            def toggle_mask(*_):
                field.password = not field.password
                toggle.set_icon("eye" if field.password else "eye_off")

            toggle.bind(on_release=toggle_mask)
            row.add_widget(toggle)
            self.password_fields.append((field, toggle))
            self.actions.append(toggle)
        self.form.add_widget(row)
        self.fields.append(field)
        if email:
            self.email = field
        return field

    def button(self, caption, callback, *, primary=False):
        button_type = _RoundedButton if primary else _Action
        button = button_type(text=caption, size_hint_y=None, height=dp(47 if primary else 43))
        button.bind(on_release=lambda *_: callback())
        self.form.add_widget(button)
        self.actions.append(button)
        return button

    def on_pre_leave(self, *_):
        for field in self.fields:
            field.focus = False
        self.clear_passwords()

    def clear_passwords(self):
        for field, toggle in self.password_fields:
            field.text = ""
            field.reset_undo()
            field.password = True
            toggle.set_icon("eye")

    def set_busy(self, busy):
        for action in self.actions:
            action.disabled = busy
        for field in self.fields:
            field.readonly = busy

    def message(self, text):
        self.notice.text = text


class LoginScreen(_AuthScreen):
    def __init__(self, auth, **kwargs):
        super().__init__(auth, "Welcome Back!", "Log in to manage your barbecue business.", back="splash", **kwargs)
        self.field("Email Address", "mail", email=True)
        password = self.field("Password", "lock", secret=True)
        self.button("Forgot Password?", lambda: auth.show("forgot", self.email.text))
        self.form.add_widget(self.notice)
        self.button("Log In", lambda: auth.login(self.email.text, password.text), primary=True)
        self.button("Don't have an account? Sign Up", lambda: auth.show("signup", self.email.text))


class SignupScreen(_AuthScreen):
    def __init__(self, auth, **kwargs):
        super().__init__(auth, "Create Account", "Get started with GrillFlow.", back="login", **kwargs)
        name = self.field("Full Name", "person")
        self.field("Email Address", "mail", email=True)
        password = self.field("Password", "lock", secret=True)
        confirmation = self.field("Confirm Password", "lock", secret=True)
        self.form.add_widget(self.notice)
        self.button("Sign Up", lambda: auth.signup(name.text, self.email.text, password.text, confirmation.text),
                    primary=True)
        self.button("Already have an account? Log In", lambda: auth.show("login", self.email.text))


class ForgotPasswordScreen(_AuthScreen):
    def __init__(self, auth, **kwargs):
        super().__init__(auth, "Forgot Password?", "Enter your email address to request a reset link.",
                         back="login", **kwargs)
        self.field("Email Address", "mail", email=True)
        self.form.add_widget(self.notice)
        self.button("Send Reset Link", lambda: auth.send_reset(self.email.text), primary=True)
        self.button("Back to Login", lambda: auth.show("login", self.email.text))


class VerifyEmailScreen(_AuthScreen):
    def __init__(self, auth, **kwargs):
        super().__init__(auth, "Verify Your Email", "Open the verification link in your email before continuing.",
                         back="login", **kwargs)
        self.address = wrapping_label("", 14, INK, bold=True, align="center")
        self.form.add_widget(self.address)
        self.form.add_widget(self.notice)
        self.button("I've Verified My Email", auth.check_verification, primary=True)
        self.resend = self.button("Resend Verification Email", auth.resend_verification)
        self.button("Back to Login", lambda: auth.show("login", self.address.text))
