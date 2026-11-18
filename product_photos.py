from pathlib import Path
from shutil import copyfile
from uuid import uuid4

from kivy.utils import platform


DEFAULT_PHOTO = Path(__file__).resolve().parent / "assets" / "images" / "splash_background.png"
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png"}


class PhotoPickerError(Exception):
    pass


class DesktopPhotoPicker:
    def choose_photo(self):
        try:
            import tkinter
            from tkinter import filedialog
        except ImportError as error:
            raise PhotoPickerError("The desktop photo picker is unavailable on this installation.") from error

        try:
            root = tkinter.Tk()
            try:
                root.withdraw()
                root.attributes("-topmost", True)
                selected = filedialog.askopenfilename(
                    parent=root, title="Choose product photo",
                    filetypes=(("Product photos", "*.jpg *.jpeg *.png"),),
                )
            finally:
                root.destroy()
        except (OSError, tkinter.TclError) as error:
            raise PhotoPickerError("Could not open the photo picker.") from error
        return Path(selected) if selected else None

    def take_photo(self):
        raise PhotoPickerError("Capture a photo with your camera app, then choose it from the gallery.")


class AndroidPhotoPicker:
    # Future adapter: use Android Photo Picker and TakePicture via a content URI.
    # Import through ContentResolver into app-private storage using the URI grant.
    def choose_photo(self):
        raise PhotoPickerError("Android gallery selection is not available yet.")

    def take_photo(self):
        raise PhotoPickerError("Android camera capture is not available yet.")


def create_photo_picker():
    return AndroidPhotoPicker() if platform == "android" else DesktopPhotoPicker()


def import_photo(source, data_dir):
    folder = Path(data_dir) / "product_photos"
    folder.mkdir(parents=True, exist_ok=True)
    destination = folder / f"{uuid4().hex}{source.suffix.lower()}"
    try:
        copyfile(source, destination)
    except OSError:
        destination.unlink(missing_ok=True)
        raise
    return destination


def product_photo_path(data_dir, image_path):
    if image_path:
        candidate = Path(data_dir) / "product_photos" / image_path
        if candidate.is_file():
            return candidate
    return DEFAULT_PHOTO
