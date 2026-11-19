from kivy.core.image import Image as CoreImage
from kivy.graphics import Color, Ellipse
from kivy.metrics import dp
from kivy.uix.anchorlayout import AnchorLayout
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.screenmanager import Screen
from kivy.uix.scrollview import ScrollView

from firebase_auth import clean_display_name
from product_photos import PhotoPickerError, create_photo_picker
from profile_photo import avatar_path, save_avatar
from screens.dashboard_screen import (
    AMOUNT, CREAM, GREEN, INK, MUTED, ORANGE, WHITE, BottomSheet, Icon, IconButton,
    build_navigation, paint_header_gradient, paint_surface, wrapping_label,
)
from screens.new_order_screen import _Action, _card, _icon_holder, _text_field, _vertical


class _Avatar(AnchorLayout):
    def __init__(self):
        super().__init__(size_hint=(None, None), size=(dp(88), dp(88)))
        with self.canvas.before:
            self.tint = Color(1, .9, .81, 1)
            self.circle = Ellipse(pos=self.pos, size=self.size)
        self.placeholder = Icon("person", ORANGE, size_hint=(None, None), size=(dp(40), dp(40)))
        self.add_widget(self.placeholder)
        self.bind(pos=self._place, size=self._place)

    def _place(self, *_):
        self.circle.pos, self.circle.size = self.pos, self.size

    def show_photo(self, texture):
        self.circle.texture = texture
        self.tint.rgba = (1, 1, 1, 1) if texture else (1, .9, .81, 1)
        self.placeholder.opacity = 0 if texture else 1


class ProfileScreen(Screen):
    def __init__(self, app, directory, **kwargs):
        super().__init__(**kwargs)
        self.app = app
        self.directory = directory
        self.picker = create_photo_picker(title="Choose profile photo")
        self.sheet = None
        self.busy = False
        shell = BoxLayout(orientation="vertical")
        paint_surface(shell, CREAM)
        header = BoxLayout(size_hint_y=None, height=dp(57), padding=(dp(5), 0, dp(12), 0), spacing=dp(4))
        paint_header_gradient(header)
        back = IconButton("back", WHITE, 22, size_hint_x=None, width=dp(44))
        back.bind(on_release=lambda *_: setattr(self.manager, "current", "dashboard"))
        header.add_widget(back)
        title = wrapping_label("My Profile", 21, WHITE, bold=True)
        middle = AnchorLayout(anchor_x="left")
        middle.add_widget(title)
        header.add_widget(middle)
        header.add_widget(_icon_holder("person", WHITE, 32))
        shell.add_widget(header)

        scroll = ScrollView(do_scroll_x=False, bar_width=dp(3))
        content = _vertical(spacing=dp(10), padding=(dp(12), dp(11), dp(12), dp(13)))
        profile = _card()
        avatar_row = AnchorLayout(size_hint_y=None, height=dp(92))
        self.avatar = _Avatar()
        avatar_row.add_widget(self.avatar)
        profile.add_widget(avatar_row)
        photo = _Action("Change Photo", size_hint_y=None, height=dp(40))
        photo.bind(on_release=self._choose_photo)
        profile.add_widget(photo)
        self.display_name = wrapping_label("", 20, INK, bold=True, align="center")
        self.email = wrapping_label("", 14, MUTED, align="center")
        profile.add_widget(self.display_name)
        profile.add_widget(self.email)
        content.add_widget(profile)

        personal = _card()
        personal.add_widget(wrapping_label("Personal Information", 17, bold=True))
        self.full_name = wrapping_label("", 14)
        self.edit_name = IconButton("edit", ORANGE, 19, size_hint_x=None, width=dp(44))
        self.edit_name.bind(on_release=self._edit)
        personal.add_widget(self._row("Full Name", self.full_name, self.edit_name))
        self.email_address = wrapping_label("", 14)
        personal.add_widget(self._row("Email Address", self.email_address, _icon_holder("lock", MUTED, 44)))
        content.add_widget(personal)

        security = _card()
        security.add_widget(wrapping_label("Account & Security", 17, bold=True))
        self.status = wrapping_label("", 14, MUTED)
        self.status_icon = IconButton("info", GREEN, 18, size_hint_x=None, width=dp(44), disabled=True)
        security.add_widget(self._row("Email Verification Status", self.status, self.status_icon))
        self.reset = _Action("Change Password", size_hint_y=None, height=dp(44))
        self.reset.bind(on_release=self._confirm_password_reset)
        security.add_widget(self.reset)
        content.add_widget(security)
        self.notice = wrapping_label("", 13, AMOUNT, align="center")
        content.add_widget(self.notice)
        logout = _Action("Log Out", size_hint_y=None, height=dp(45))
        logout.color = (.57, .15, .12, 1)
        logout.bind(on_release=self._confirm_logout)
        content.add_widget(logout)
        scroll.add_widget(content)
        shell.add_widget(scroll)
        navigation, _ = build_navigation(self, None, self._message)
        shell.add_widget(navigation)
        self.add_widget(shell)

    @staticmethod
    def _row(caption, value, accessory):
        row = BoxLayout(size_hint_y=None, spacing=dp(4))
        copy = _vertical(spacing=dp(3))
        copy.add_widget(wrapping_label(caption, 12, MUTED))
        copy.add_widget(value)
        copy.bind(height=lambda _, height: setattr(row, "height", max(height, dp(44))))
        row.add_widget(copy)
        row.add_widget(accessory)
        return row

    def on_pre_enter(self, *_):
        self.render(self.app.session)
        self._reload_photo()
        self.app.refresh_profile()

    def on_pre_leave(self, *_):
        if self.sheet:
            self.sheet.dismiss()

    def render(self, session):
        profile = session.profile
        self.display_name.text = self.full_name.text = profile.name or "Name not set"
        self.email.text = self.email_address.text = profile.email or "Email unavailable"
        if session.offline:
            self.status.text = "Last known: Verified (offline)" if profile.verified else "Verification unavailable offline"
        else:
            self.status.text = "Verified" if profile.verified else "Not Verified"
        self.status_icon.set_icon("check" if profile.verified else "info")
        self.set_busy(self.busy)

    def clear(self):
        self.avatar.show_photo(None)
        for field in (self.display_name, self.email, self.full_name, self.email_address, self.status, self.notice):
            field.text = ""
        if self.sheet:
            self.sheet.dismiss()
            self.sheet = None

    def set_busy(self, busy):
        self.busy = busy
        session = self.app.session
        self.edit_name.disabled = self.reset.disabled = busy or not session or session.offline

    def message(self, text):
        self.notice.text = text

    def _reload_photo(self):
        path = avatar_path(self.directory)
        texture = None
        if path.is_file() and not path.is_symlink():
            try:
                texture = CoreImage(str(path), nocache=True).texture
            except (OSError, ValueError):
                self.message("Could not load the profile photo.")
        self.avatar.show_photo(texture)

    def _choose_photo(self, *_):
        try:
            source = self.picker.choose_photo()
            if source is None:
                return
            save_avatar(source, self.directory)
        except (PhotoPickerError, OSError, ValueError) as error:
            self.message(str(error) if isinstance(error, (PhotoPickerError, ValueError))
                         else "Could not save the profile photo.")
            return
        self._reload_photo()
        self.message("Profile photo saved on this device.")

    def _edit(self, *_):
        session = self.app.session
        if not session or session.offline:
            return
        sheet = self._message("Edit Full Name", None, confirmation="Cancel")
        row, field = _text_field("Full Name")
        field.text = session.profile.name
        sheet.copy.add_widget(row)
        notice = wrapping_label("", 13, AMOUNT)
        sheet.copy.add_widget(notice)
        save = _Action("Save Changes", primary=True, size_hint_y=None, height=dp(44))
        sheet.copy.add_widget(save)

        def submit(*_):
            if save.disabled or sheet.parent is None:
                return
            try:
                name = clean_display_name(field.text)
            except ValueError as error:
                notice.text = str(error)
                return
            if self.app.update_profile_name(name):
                sheet.dismiss()

        sheet.bind(parent=lambda _, parent: setattr(field, "focus", False) if parent is None else None)
        save.bind(on_release=submit)

    def _confirm_password_reset(self, *_):
        self._confirm(
            "Change Password", "Send a secure password reset link to your account email?",
            "Send Reset Link", self.app.send_profile_password_reset,
        )

    def _confirm_logout(self, *_):
        self._confirm("Log Out?", "Are you sure you want to log out of your GrillFlow account?",
                      "Log Out", self.app.logout)

    def _confirm(self, title, text, caption, action):
        sheet = self._message(title, text, confirmation="Cancel")
        button = _Action(caption, primary=True, size_hint_y=None, height=dp(44))

        def submit(*_):
            if sheet.parent is self:
                sheet.dismiss()
                action()

        button.bind(on_release=submit)
        sheet.copy.add_widget(button)

    def _message(self, title, text, *, confirmation="Close"):
        if self.sheet:
            self.sheet.dismiss()
        self.sheet = BottomSheet(title, text, confirmation=confirmation)
        self.add_widget(self.sheet)
        return self.sheet
