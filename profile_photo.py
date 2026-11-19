"""Store a bounded, device-local avatar in the authenticated account directory."""

import os
from pathlib import Path
from tempfile import NamedTemporaryFile

from PIL import Image, ImageOps


AVATAR = "profile-avatar.jpg"
MAX_BYTES = 32 * 1024 * 1024
MAX_PIXELS = 50_000_000
MAX_SIDE = 512


def avatar_path(directory):
    return Path(directory) / AVATAR


def save_avatar(source, directory):
    source = Path(source)
    if source.suffix.lower() not in {".jpg", ".jpeg", ".png"}:
        raise ValueError("Choose a JPG, JPEG, or PNG image.")
    directory = Path(directory)
    destination = avatar_path(directory)
    if directory.is_symlink() or destination.is_symlink():
        raise ValueError("The profile photo location is unavailable.")
    directory.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        if not source.is_file():
            raise ValueError("Choose a valid image file.")
        with source.open("rb") as file:
            if os.fstat(file.fileno()).st_size > MAX_BYTES:
                raise ValueError("Choose an image smaller than 32 MB.")
            with Image.open(file, formats=("JPEG", "PNG")) as image:
                if image.width * image.height > MAX_PIXELS:
                    raise ValueError("Choose an image with fewer than 50 million pixels.")
                image.draft("RGB", (MAX_SIDE, MAX_SIDE))
                corrected = ImageOps.exif_transpose(image)
                side = min(MAX_SIDE, *corrected.size)
                square = ImageOps.fit(corrected, (side, side), Image.Resampling.LANCZOS).convert("RGBA")
                avatar = Image.new("RGB", square.size, "white")
                avatar.paste(square, mask=square.getchannel("A"))
        with NamedTemporaryFile(dir=directory, suffix=".tmp", delete=False) as file:
            temporary = Path(file.name)
            avatar.save(file, "JPEG", quality=86, optimize=True)
        temporary.replace(destination)
    except (Image.UnidentifiedImageError, Image.DecompressionBombError, SyntaxError) as error:
        raise ValueError("Choose a valid JPG, JPEG, or PNG image.") from error
    finally:
        if temporary:
            temporary.unlink(missing_ok=True)
    return destination
