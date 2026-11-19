import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from PIL import Image

from firebase_auth import account_directory
from profile_photo import avatar_path, save_avatar


class ProfilePhotoTests(unittest.TestCase):
    def test_photos_are_bounded_oriented_and_isolated_by_account(self):
        with TemporaryDirectory() as fixture:
            root = Path(fixture)
            first = account_directory(root, "project", "user-a")
            second = account_directory(root, "project", "user-b")
            source = root / "portrait.jpg"
            with Image.new("RGB", (1200, 1200), "red") as image:
                image.paste("blue", (0, 0, 600, 1200))
                exif = image.getexif()
                exif[274] = 6
                image.save(source, exif=exif)
            save_avatar(source, first)
            self.assertFalse(avatar_path(second).exists())
            with Image.open(avatar_path(first)) as avatar:
                self.assertEqual(avatar.size, (512, 512))
                self.assertEqual(avatar.format, "JPEG")
                self.assertIsNone(avatar.getexif().get(274))
                self.assertGreater(avatar.getpixel((256, 32))[2], 240)
                self.assertGreater(avatar.getpixel((256, 480))[0], 240)
            original = avatar_path(first).read_bytes()
            replacement = root / "replacement.png"
            with Image.new("RGBA", (200, 350), (0, 255, 0, 128)) as image:
                image.save(replacement)
            save_avatar(replacement, second)
            self.assertEqual(avatar_path(first).read_bytes(), original)
            self.assertNotEqual(avatar_path(second).read_bytes(), original)
            save_avatar(replacement, first)
            self.assertEqual(avatar_path(first).read_bytes(), avatar_path(second).read_bytes())

    def test_invalid_photo_does_not_replace_avatar(self):
        with TemporaryDirectory() as fixture:
            root = Path(fixture)
            destination = avatar_path(root)
            destination.write_bytes(b"existing avatar")
            invalid = root / "invalid.jpg"
            invalid.write_bytes(b"not an image")
            with self.assertRaises(ValueError):
                save_avatar(invalid, root)
            self.assertEqual(destination.read_bytes(), b"existing avatar")
