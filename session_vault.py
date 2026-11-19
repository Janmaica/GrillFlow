"""Device-bound protection for Firebase refresh credentials."""

import base64
import ctypes
import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile

from firebase_auth import AuthError


def _dpapi(payload, encrypt):
    from ctypes import wintypes

    class Blob(ctypes.Structure):
        _fields_ = [("size", wintypes.DWORD), ("data", ctypes.c_void_p)]

    source = ctypes.create_string_buffer(payload)
    incoming = Blob(len(payload), ctypes.cast(source, ctypes.c_void_p))
    outgoing = Blob()
    crypt = ctypes.WinDLL("crypt32", use_last_error=True)
    transform = crypt.CryptProtectData if encrypt else crypt.CryptUnprotectData
    transform.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
                         ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
    transform.restype = wintypes.BOOL
    if not transform(ctypes.byref(incoming), None, None, None, None, 1, ctypes.byref(outgoing)):
        raise ctypes.WinError(ctypes.get_last_error())
    free = ctypes.WinDLL("kernel32").LocalFree
    free.argtypes = [ctypes.c_void_p]
    free.restype = ctypes.c_void_p
    try:
        return ctypes.string_at(outgoing.data, outgoing.size)
    finally:
        ctypes.memset(outgoing.data, 0, outgoing.size)
        free(outgoing.data)


def _android(payload, encrypt):
    from jnius import autoclass

    alias = "grillflow-firebase-session-v1"
    keys = autoclass("java.security.KeyStore").getInstance("AndroidKeyStore")
    keys.load(None)
    key = keys.getKey(alias, None)
    if key is None:
        if not encrypt:
            raise ValueError("Missing device key")
        properties = autoclass("android.security.keystore.KeyProperties")
        builder = autoclass("android.security.keystore.KeyGenParameterSpec$Builder")(
            alias, properties.PURPOSE_ENCRYPT | properties.PURPOSE_DECRYPT,
        )
        builder.setBlockModes(properties.BLOCK_MODE_GCM)
        builder.setEncryptionPaddings(properties.ENCRYPTION_PADDING_NONE)
        generator = autoclass("javax.crypto.KeyGenerator").getInstance("AES", "AndroidKeyStore")
        generator.init(builder.setKeySize(256).build())
        key = generator.generateKey()

    codec = autoclass("android.util.Base64")
    Cipher = autoclass("javax.crypto.Cipher")
    cipher = Cipher.getInstance("AES/GCM/NoPadding")

    def java_bytes(data):
        return codec.decode(base64.b64encode(data).decode("ascii"), codec.NO_WRAP)

    def python_bytes(data):
        return base64.b64decode(codec.encodeToString(data, codec.NO_WRAP))

    if encrypt:
        cipher.init(Cipher.ENCRYPT_MODE, key)
        return python_bytes(cipher.getIV()) + python_bytes(cipher.doFinal(java_bytes(payload)))
    if len(payload) < 28:
        raise ValueError("Invalid encrypted session")
    params = autoclass("javax.crypto.spec.GCMParameterSpec")(128, java_bytes(payload[:12]))
    cipher.init(Cipher.DECRYPT_MODE, key, params)
    return python_bytes(cipher.doFinal(java_bytes(payload[12:])))


class SessionVault:
    def __init__(self, directory, platform):
        self.path = Path(directory) / "firebase-session.bin"
        self.backend = {"win": _dpapi, "android": _android}.get(platform)

    def load(self):
        try:
            with self.path.open("rb") as file:
                payload = file.read(65537)
        except FileNotFoundError:
            return None
        except OSError:
            raise AuthError("STORAGE") from None
        try:
            if self.backend is None or len(payload) > 65536:
                raise ValueError
            return json.loads(self.backend(payload, False))
        except Exception:
            raise AuthError("STORAGE") from None

    def save(self, data):
        temporary = None
        try:
            if self.backend is None:
                raise ValueError
            payload = self.backend(json.dumps(data).encode("utf-8"), True)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with NamedTemporaryFile(dir=self.path.parent, suffix=".tmp", delete=False) as file:
                temporary = Path(file.name)
                file.write(payload)
                file.flush()
                os.fsync(file.fileno())
            temporary.replace(self.path)
        except Exception:
            raise AuthError("STORAGE") from None
        finally:
            if temporary is not None:
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    pass

    def clear(self):
        try:
            self.path.unlink(missing_ok=True)
        except OSError:
            raise AuthError("STORAGE") from None
