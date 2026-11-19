import sqlite3

from kivy.core.image import Image as CoreImage
from kivy.graphics import RoundedRectangle, StencilPop, StencilPush, StencilUnUse, StencilUse
from kivy.logger import Logger
from kivy.metrics import dp, sp
from kivy.uix.anchorlayout import AnchorLayout
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.image import Image
from kivy.uix.screenmanager import Screen
from kivy.uix.scrollview import ScrollView
from kivy.uix.spinner import Spinner, SpinnerOption
from kivy.uix.textinput import TextInput

from product_photos import (
    DEFAULT_PHOTO, IMAGE_EXTENSIONS, PhotoPickerError, create_photo_picker, import_photo, product_photo_path,
)
from product_store import (
    DUPLICATE_PRODUCT_MESSAGE, UNITS, ProductConflict, format_product_name, normalized_name, validate_product,
)
from screens.dashboard_screen import (
    AMOUNT, BORDER, CREAM, INK, MUTED, ORANGE, WHITE, BottomSheet, IconButton,
    label, paint_header_gradient, paint_surface, wrapping_label,
)
from screens.splash_screen import _RoundedButton


class ProductImage(Image):
    def __init__(self, **kwargs):
        super().__init__(fit_mode="cover", **kwargs)
        with self.canvas.before:
            StencilPush()
            mask = RoundedRectangle(radius=[dp(12)])
            StencilUse()
        with self.canvas.after:
            StencilUnUse()
            cleanup = RoundedRectangle(radius=[dp(12)])
            StencilPop()

        def update(*_):
            mask.pos = cleanup.pos = self.pos
            mask.size = cleanup.size = self.size

        self.bind(pos=update, size=update)
        update()


class _UnitOption(SpinnerOption):
    def __init__(self, **kwargs):
        super().__init__(
            height=dp(44), font_size=sp(15), color=INK, background_normal="",
            background_down="", background_color=CREAM, **kwargs,
        )


class AddProductScreen(Screen):
    def __init__(self, store, **kwargs):
        super().__init__(**kwargs)
        self.store = store
        self.photo_picker = create_photo_picker()
        self.selected_photo = None
        self.existing_image_path = None
        self.editing = None
        self.photo_sheet = None
        self.saving = False

        shell = BoxLayout(orientation="vertical")
        paint_surface(shell, ORANGE)
        header = BoxLayout(size_hint_y=None, height=dp(57), spacing=dp(5),
                           padding=(dp(5), 0, dp(12), 0))
        paint_header_gradient(header)
        self.back_button = IconButton("back", WHITE, 22, size_hint_x=None, width=dp(44))
        self.back_button.bind(on_release=self._go_back)
        header.add_widget(self.back_button)
        self.heading = label("Add Product", 23, WHITE, bold=True)
        header.add_widget(self.heading)
        shell.add_widget(header)

        panel = BoxLayout(padding=(dp(8), 0))
        paint_surface(panel, CREAM, radius=18, top_only=True)
        scroll = ScrollView(do_scroll_x=False, bar_width=dp(3))
        form = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(6),
                         padding=(dp(12), dp(14), dp(12), dp(15)))
        form.bind(minimum_height=form.setter("height"))
        form.add_widget(self._build_photo())
        self.name_input, _ = self._add_input(form, "Product Name", "Enter product name")
        self.name_input.bind(focus=self._format_name_on_blur)
        self.price_input, _ = self._add_input(form, "Selling Price (₱)", "0.00")
        self.stock_input, self.stock_caption = self._add_input(form, "Initial Stock", "0")
        form.add_widget(label("Unit", 14, bold=True, size_hint_y=None, height=dp(20)))
        self.unit_input = Spinner(
            text=UNITS[0], values=UNITS, option_cls=_UnitOption, color=INK,
            font_size=sp(15), size_hint_y=None, height=dp(43), background_normal="",
            background_down="", background_color=(0, 0, 0, 0),
            halign="left", valign="middle", padding=(dp(11), 0),
        )
        self.unit_input.bind(size=lambda widget, size: setattr(widget, "text_size", size))
        paint_surface(self.unit_input, WHITE, radius=9, border=BORDER)
        unit_row = FloatLayout(size_hint_y=None, height=dp(43))
        self.unit_input.pos_hint = {"x": 0, "y": 0}
        unit_row.add_widget(self.unit_input)
        unit_row.add_widget(label("v", 14, MUTED, align="center", size_hint=(None, 1),
                                  width=dp(34), pos_hint={"right": 1, "y": 0}))
        form.add_widget(unit_row)
        self.status = wrapping_label("", 14, AMOUNT)
        self.status.height = 0
        form.add_widget(self.status)
        self.save_button = _RoundedButton(text="Save Product", size_hint_y=None, height=dp(48))
        self.save_button.bind(on_release=self._save)
        form.add_widget(self.save_button)
        scroll.add_widget(form)
        panel.add_widget(scroll)
        shell.add_widget(panel)
        self.add_widget(shell)

    def _build_photo(self):
        holder = AnchorLayout(size_hint_y=None, height=dp(150))
        preview = FloatLayout(size_hint=(None, None), size=(dp(176), dp(146)))
        self.preview = ProductImage(
            source=str(DEFAULT_PHOTO), size_hint=(None, None), size=(dp(162), dp(133)),
            pos_hint={"x": 0, "top": 1},
        )
        preview.add_widget(self.preview)
        self.camera_button = IconButton(
            "camera", ORANGE, 23, size_hint=(None, None), size=(dp(46), dp(46)),
            pos_hint={"right": 1, "y": 0},
        )
        paint_surface(self.camera_button, WHITE, radius=12, border=BORDER)
        self.camera_button.bind(on_release=self._show_photo_options)
        preview.add_widget(self.camera_button)
        holder.add_widget(preview)
        return holder

    @staticmethod
    def _add_input(form, caption, hint):
        heading = label(caption, 14, bold=True, size_hint_y=None, height=dp(20))
        form.add_widget(heading)
        container = BoxLayout(size_hint_y=None, height=dp(43))
        paint_surface(container, WHITE, radius=9, border=BORDER)
        field = TextInput(
            hint_text=hint, multiline=False, font_size=sp(15),
            padding=(dp(11), dp(11)), foreground_color=INK,
            hint_text_color=MUTED, cursor_color=ORANGE, background_normal="",
            background_active="", background_color=(0, 0, 0, 0),
        )
        container.add_widget(field)
        form.add_widget(container)
        return field, heading

    def on_pre_enter(self, *_):
        self.saving = False
        self.save_button.disabled = False
        for field in (self.name_input, self.price_input, self.stock_input):
            field.text = ""
        self.unit_input.text = UNITS[0]
        self._use_default_photo()
        product = self.editing
        self.heading.text = "Edit Product" if product else "Add Product"
        self.stock_caption.text = "Current Stock" if product else "Initial Stock"
        if product:
            self.name_input.text = product["name"]
            pesos, cents = divmod(product["selling_price"], 100)
            self.price_input.text = f"{pesos}.{cents:02d}"
            self.stock_input.text = str(product["stock"])
            self.unit_input.text = product["unit"]
            self.existing_image_path = product["image_path"]
            source = product_photo_path(self.store.data_dir, self.existing_image_path)
            if source != DEFAULT_PHOTO:
                try:
                    if CoreImage(str(source), nocache=True).texture:
                        self.preview.source = str(source)
                except Exception:
                    Logger.warning("Products: Existing photo is unreadable; showing default")

    def on_pre_leave(self, *_):
        self._clear_focus()
        if self.photo_sheet:
            self.photo_sheet.dismiss()
        self.editing = None

    def _format_name_on_blur(self, field, focused):
        if not focused:
            field.text = format_product_name(field.text)

    def _clear_focus(self):
        for field in (self.name_input, self.price_input, self.stock_input):
            field.focus = False
        self.unit_input.is_open = False

    def _go_back(self, *_):
        self.manager.current = "products"

    def _show_photo_options(self, *_):
        self._clear_focus()
        if self.photo_sheet and self.photo_sheet.parent:
            return
        self.photo_sheet = BottomSheet("Product Photo", None)
        for title, action in (
            ("Take Photo", self.photo_picker.take_photo),
            ("Choose from Gallery", self.photo_picker.choose_photo),
            ("Use Default Photo", self._use_default_photo),
        ):
            option = _RoundedButton(text=title, size_hint_y=None, height=dp(45))
            option.bind(on_release=lambda _, action=action: self._choose_photo(action))
            self.photo_sheet.copy.add_widget(option)
        self.add_widget(self.photo_sheet)

    def _choose_photo(self, action):
        self.photo_sheet.dismiss()
        try:
            photo = action()
        except PhotoPickerError as error:
            self.status.text = str(error)
            return
        if photo is None:
            return
        if photo.suffix.lower() not in IMAGE_EXTENSIONS:
            self.status.text = "Choose a JPEG or PNG image."
            return
        try:
            texture = CoreImage(str(photo), nocache=True).texture
        except Exception:
            # Kivy image providers can raise a bare Exception on invalid input.
            texture = None
        if texture is None:
            self.status.text = "Could not open that image. Choose a readable JPEG or PNG."
            return
        self.selected_photo = photo
        self.preview.source = str(photo)
        self.preview.reload()
        self.status.text = ""

    def _use_default_photo(self):
        self.selected_photo = None
        self.existing_image_path = None
        self.preview.source = str(DEFAULT_PHOTO)
        self.status.text = ""

    def _save(self, *_):
        if self.saving:
            return
        self._clear_focus()
        try:
            fields = validate_product(self.name_input.text, self.price_input.text,
                                      self.stock_input.text, self.unit_input.text)
        except ValueError as error:
            self.status.text = str(error)
            return

        self.saving = True
        self.save_button.disabled = True
        imported = None
        try:
            product = self.editing
            unchanged_key = product and normalized_name(product["name"]) == normalized_name(fields.name)
            if not unchanged_key and self.store.name_exists(fields.name, product["id"] if product else None):
                raise ProductConflict(DUPLICATE_PRODUCT_MESSAGE)
            if self.selected_photo:
                imported = import_photo(self.selected_photo, self.store.data_dir)
            image_path = imported.name if imported else self.existing_image_path
            if product:
                self.store.update(product, fields, image_path)
            else:
                self.store.add(fields, image_path)
        except (OSError, sqlite3.Error, ProductConflict) as error:
            if imported:
                try:
                    imported.unlink(missing_ok=True)
                except OSError:
                    Logger.warning("Products: Could not remove unsaved photo")
            if isinstance(error, ProductConflict) or str(error) == DUPLICATE_PRODUCT_MESSAGE:
                self.status.text = str(error)
            else:
                Logger.warning("Products: Could not save product: %s", error)
                self.status.text = "Could not save the product. Check storage access and try again."
            self.saving = False
            self.save_button.disabled = False
            return

        products = self.manager.get_screen("products")
        if not product:
            products.search_input.text = ""
        self._go_back()
        products.show_saved()
