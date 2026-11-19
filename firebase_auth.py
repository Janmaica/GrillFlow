"""Firebase client authentication. Business data stays in the local account directory."""

import base64
import hashlib
import json
import math
import os
import re
import socket
import ssl
import time
from dataclasses import dataclass, field
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPSHandler, HTTPRedirectHandler, Request, build_opener


IDENTITY = "https://identitytoolkit.googleapis.com/v1/accounts:"
TOKEN = "https://securetoken.googleapis.com/v1/token"
FIREBASE_CONFIG = Path(__file__).resolve().with_name("google-services (3).json")
ANDROID_PACKAGE = "com.grillflow.app"
INVALID_SESSION = {"INVALID_REFRESH_TOKEN", "TOKEN_EXPIRED", "INVALID_ID_TOKEN",
                   "USER_DISABLED", "USER_NOT_FOUND", "USER_DELETED", "INVALID_GRANT"}
MESSAGES = {
    "INVALID_LOGIN_CREDENTIALS": "Incorrect email or password.",
    "INVALID_PASSWORD": "Incorrect email or password.",
    "EMAIL_NOT_FOUND": "Incorrect email or password.",
    "EMAIL_EXISTS": "An account already exists for this email. Log in or reset your password.",
    "INVALID_EMAIL": "Enter a valid email address.",
    "USER_DISABLED": "This account has been disabled.",
    "TOO_MANY_ATTEMPTS_TRY_LATER": "Too many attempts. Try again later.",
    "QUOTA_EXCEEDED": "Too many requests. Try again later.",
    "WEAK_PASSWORD": "Choose a stronger password that meets the account password policy.",
    "PASSWORD_DOES_NOT_MEET_REQUIREMENTS": "Choose a password that meets the account password policy.",
    "OPERATION_NOT_ALLOWED": "Email/password authentication is unavailable. Check the Firebase project settings.",
    "CONFIG": "Firebase Authentication is not configured for this installation.",
    "PROJECT_NUMBER_MISMATCH": "Firebase Authentication is configured for a different project.",
    "API_KEY_INVALID": "Firebase Authentication is not configured for this installation.",
    "NETWORK": "Unable to connect. Check your internet connection.",
    "EXPIRED": "Your offline access has expired. Log in online to continue.",
    "VERIFY": "Please verify your email before logging in.",
    "STORAGE": "Secure session storage is unavailable. Check this device's credential storage.",
    **{code: "Your session has expired. Please log in again." for code in INVALID_SESSION if code != "USER_DISABLED"},
}


class AuthError(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__(MESSAGES.get(code, "Authentication is temporarily unavailable. Try again."))


def clean_email(value):
    email = value.strip().lower()
    if len(email) > 254 or not re.fullmatch(r"[^@\s]+@[^@\s.]+(?:\.[^@\s.]+)+", email):
        raise ValueError("Enter a valid email address.")
    return email


def signup_fields(name, email, password, confirmation):
    name = clean_display_name(name)
    email = clean_email(email)
    if len(password) < 8:
        raise ValueError("Use at least 8 characters for your password.")
    if password != confirmation:
        raise ValueError("Passwords do not match.")
    return name, email, password


def clean_display_name(name):
    name = " ".join(name.split())
    if not name or len(name) > 80 or any(ord(character) < 32 for character in name):
        raise ValueError("Enter your full name using 1 to 80 characters.")
    return name


def account_directory(root, project, uid):
    # Firebase project and UID come from a session validated by the service.
    digest = hashlib.sha256(json.dumps([project, uid], ensure_ascii=True).encode("ascii")).hexdigest()
    base = Path(root) / "accounts"
    directory = base / digest
    if base.is_symlink() or directory.is_symlink() or (directory / "grillflow.sqlite3").is_symlink():
        raise AuthError("STORAGE")
    if directory.resolve().parent != base.resolve():
        raise AuthError("STORAGE")
    return directory


def _firebase_settings(path, *, android_package=None):
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        project = data["project_info"]["project_id"].strip()
        clients = data["client"]
        if android_package:
            clients = [
                client for client in clients
                if client.get("client_info", {}).get("android_client_info", {}).get("package_name") == android_package
            ]
        keys = {
            entry["current_key"].strip()
            for client in clients
            for entry in client.get("api_key", [])
            if entry["current_key"].strip()
        }
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return "", ""
    if len(keys) != 1 or not project:
        return "", ""
    return keys.pop(), project


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


@dataclass(frozen=True)
class Tokens:
    uid: str
    id_token: str = field(repr=False)
    refresh_token: str = field(repr=False)
    expires_at: float


@dataclass(frozen=True)
class AccountProfile:
    name: str = ""
    email: str = ""
    verified: bool = False


class VerificationRequired(AuthError):
    def __init__(self, tokens, email):
        super().__init__("VERIFY")
        self.tokens = tokens
        self.email = email


@dataclass(frozen=True)
class Session:
    uid: str
    refresh_token: str = field(repr=False)
    verified_at: float
    expires_at: float = 0
    offline: bool = False
    profile: AccountProfile = field(default_factory=AccountProfile)


class FirebaseAuth:
    def __init__(self, vault, *, api_key="", project="", offline_hours=72, opener=None, now=time.time):
        self.vault = vault
        self.api_key = api_key
        self.project = project
        self.offline_seconds = offline_hours * 3600
        self.opener = opener or build_opener(_NoRedirect())
        self.now = now

    @classmethod
    def from_project_config(cls, vault, *, android=False):
        try:
            hours = int(os.getenv("GRILLFLOW_OFFLINE_HOURS", "72"))
            if not 0 <= hours <= 168:
                raise ValueError
        except ValueError:
            # Invalid policy configuration disables offline access.
            hours = 0
        opener = _AndroidOpener() if android else None
        api_key, project = _firebase_settings(FIREBASE_CONFIG, android_package=ANDROID_PACKAGE if android else None)
        return cls(vault, api_key=api_key, project=project, offline_hours=hours, opener=opener)

    def _post(self, endpoint, values, *, form=False):
        if not self.api_key or not self.project:
            raise AuthError("CONFIG")
        content = urlencode(values) if form else json.dumps(values)
        request = Request(endpoint + "?" + urlencode({"key": self.api_key}), content.encode(),
                          {"Content-Type": "application/x-www-form-urlencoded" if form else "application/json"})
        try:
            with self.opener.open(request, timeout=8) as response:
                data = json.loads(response.read(256 * 1024))
        except HTTPError as failure:
            with failure:
                try:
                    value = json.loads(failure.read(16384))["error"]["message"]
                    code = re.split(r"[\s:]", value, maxsplit=1)[0]
                except (OSError, ValueError, TypeError, KeyError):
                    code = "SERVICE"
            raise AuthError(code if code in MESSAGES else "SERVICE") from None
        except URLError as failure:
            reason = failure.reason
            code = "NETWORK" if isinstance(reason, OSError) and not isinstance(reason, ssl.SSLError) else "SERVICE"
            raise AuthError(code) from None
        except (TimeoutError, ConnectionError, socket.gaierror):
            raise AuthError("NETWORK") from None
        except (OSError, ValueError):
            raise AuthError("SERVICE") from None
        if not isinstance(data, dict):
            raise AuthError("SERVICE")
        return data

    def _tokens(self, response, *, refresh=False):
        fields = ("user_id", "id_token", "refresh_token", "expires_in") if refresh else (
            "localId", "idToken", "refreshToken", "expiresIn",
        )
        try:
            uid, token, credential, seconds = (response[key] for key in fields)
            if not all(isinstance(value, str) and value for value in (uid, token, credential)):
                raise ValueError
            # The token was issued by Firebase over HTTPS. Check its project and identity
            # to catch mismatched configuration. This is not a general JWT verifier.
            payload = token.split(".")[1]
            claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
            if (claims["aud"] != self.project or claims["sub"] != uid
                    or claims["iss"] != f"https://securetoken.google.com/{self.project}"):
                raise AuthError("CONFIG")
            lifetime = int(seconds)
            if lifetime <= 0:
                raise ValueError
            return Tokens(uid, token, credential, self.now() + lifetime)
        except (ValueError, TypeError, KeyError, IndexError, AttributeError):
            raise AuthError("SERVICE") from None

    def register(self, email, password):
        return self._tokens(self._post(IDENTITY + "signUp", {
            "email": email, "password": password, "returnSecureToken": True,
        }))

    def update_name(self, tokens, name):
        return self._post(IDENTITY + "update", {"idToken": tokens.id_token, "displayName": name,
                                                "returnSecureToken": False})

    def sign_in(self, email, password):
        return self._tokens(self._post(IDENTITY + "signInWithPassword", {
            "email": email, "password": password, "returnSecureToken": True,
        }))

    def refresh(self, credential):
        return self._tokens(self._post(TOKEN, {"grant_type": "refresh_token", "refresh_token": credential},
                                       form=True), refresh=True)

    def lookup_profile(self, tokens):
        response = self._post(IDENTITY + "lookup", {"idToken": tokens.id_token})
        users = response.get("users")
        if not isinstance(users, list) or len(users) != 1 or not isinstance(users[0], dict):
            raise AuthError("INVALID_ID_TOKEN")
        account = users[0]
        if account.get("localId") != tokens.uid or account.get("disabled"):
            raise AuthError("INVALID_ID_TOKEN")
        name, email = account.get("displayName", ""), account.get("email", "")
        return AccountProfile(name if isinstance(name, str) else "",
                              email if isinstance(email, str) else "", account.get("emailVerified") is True)

    def is_verified(self, tokens):
        return self.lookup_profile(tokens).verified

    def send_verification(self, tokens):
        self._post(IDENTITY + "sendOobCode", {"requestType": "VERIFY_EMAIL", "idToken": tokens.id_token})

    def reset_password(self, email):
        try:
            self._post(IDENTITY + "sendOobCode", {"requestType": "PASSWORD_RESET", "email": email})
        except AuthError as failure:
            if failure.code != "EMAIL_NOT_FOUND":
                raise

    def remember(self, tokens, profile=None):
        profile = profile or AccountProfile()
        session = Session(tokens.uid, tokens.refresh_token, self.now(), tokens.expires_at, profile=profile)
        self.vault.save({"project": self.project, "uid": session.uid,
                         "refresh_token": session.refresh_token, "verified_at": session.verified_at,
                         "name": profile.name, "email": profile.email, "email_verified": profile.verified})
        return session

    def _verified_account(self, session):
        try:
            tokens = self.refresh(session.refresh_token)
            if tokens.uid != session.uid:
                raise AuthError("INVALID_ID_TOKEN")
            profile = self.lookup_profile(tokens)
            if not profile.verified:
                raise VerificationRequired(tokens, profile.email)
            return tokens, profile
        except AuthError as failure:
            if failure.code in INVALID_SESSION or failure.code in {"VERIFY", "PROJECT_NUMBER_MISMATCH"}:
                self.vault.clear()
            raise

    def change_profile_name(self, session, name):
        name = clean_display_name(name)
        tokens, profile = self._verified_account(session)
        updated = self._profile_request(self.update_name, tokens, name)
        if updated.get("localId") != session.uid or updated.get("displayName") != name:
            raise AuthError("SERVICE")
        return self.remember(tokens, AccountProfile(name, profile.email, True))

    def send_profile_password_reset(self, session):
        tokens, profile = self._verified_account(session)
        if not profile.email:
            raise AuthError("SERVICE")
        self._profile_request(self._post, IDENTITY + "sendOobCode", {
            "requestType": "PASSWORD_RESET", "email": profile.email,
        })
        return self.remember(tokens, profile)

    def _profile_request(self, request, *args):
        try:
            return request(*args)
        except AuthError as failure:
            if failure.code in INVALID_SESSION:
                self.vault.clear()
            raise

    def offline_allowed(self, session):
        return 0 <= self.now() - session.verified_at < self.offline_seconds

    def restore(self, active=None):
        if active is None:
            saved = self.vault.load()
            if saved is None:
                return None
            if not self.project or not self.api_key:
                raise AuthError("CONFIG")
            try:
                uid, credential, verified = (saved[key] for key in ("uid", "refresh_token", "verified_at"))
                if (saved["project"] != self.project
                        or not all(isinstance(v, str) and v for v in (uid, credential))
                        or type(verified) not in (int, float) or not math.isfinite(verified)):
                    raise ValueError
                name, email = saved.get("name", ""), saved.get("email", "")
                profile = AccountProfile(name if isinstance(name, str) else "",
                                         email if isinstance(email, str) else "", saved.get("email_verified") is True)
                active = Session(uid, credential, verified, profile=profile)
            except (KeyError, TypeError, ValueError):
                self.vault.clear()
                raise AuthError("INVALID_ID_TOKEN") from None
        try:
            tokens, profile = self._verified_account(active)
            return self.remember(tokens, profile)
        except AuthError as failure:
            if failure.code == "NETWORK":
                if self.offline_allowed(active):
                    return Session(active.uid, active.refresh_token, active.verified_at, offline=True,
                                   profile=active.profile)
                raise AuthError("EXPIRED") from None
            raise


class _AndroidOpener:
    """Load Android's system TLS roots for Python distributions without a CA bundle."""

    def __init__(self):
        self.opener = None
        self.package = None
        self.certificate = None

    def open(self, request, *, timeout):
        if self.opener is None:
            from jnius import autoclass

            activity = autoclass("org.kivy.android.PythonActivity").mActivity
            package_manager = activity.getPackageManager()
            self.package = activity.getPackageName()
            if self.package != ANDROID_PACKAGE:
                raise AuthError("CONFIG")
            sdk = autoclass("android.os.Build$VERSION").SDK_INT
            flags = autoclass("android.content.pm.PackageManager")
            if sdk >= 28:
                info = package_manager.getPackageInfo(self.package, flags.GET_SIGNING_CERTIFICATES)
                signers = info.signingInfo.getApkContentsSigners()
            else:
                info = package_manager.getPackageInfo(self.package, flags.GET_SIGNATURES)
                signers = info.signatures
            if len(signers) != 1:
                raise AuthError("CONFIG")
            codec = autoclass("android.util.Base64")
            sha1 = autoclass("java.security.MessageDigest").getInstance("SHA-1")
            digest = sha1.digest(signers[0].toByteArray())
            self.certificate = base64.b64decode(codec.encodeToString(digest, codec.NO_WRAP)).hex().upper()

            store = autoclass("java.security.KeyStore").getInstance("AndroidCAStore")
            store.load(None)
            aliases = store.aliases()
            certificates = []
            while aliases.hasMoreElements():
                alias = aliases.nextElement()
                if not isinstance(alias, str):
                    alias = alias.toString()
                if alias.startswith("system:"):
                    certificate = store.getCertificate(alias)
                    encoded = codec.encodeToString(certificate.getEncoded(), codec.NO_WRAP)
                    certificates.append(ssl.DER_cert_to_PEM_cert(base64.b64decode(encoded)))
            if not certificates:
                raise AuthError("SERVICE")
            context = ssl.create_default_context(cadata="".join(certificates))
            self.opener = build_opener(_NoRedirect(), HTTPSHandler(context=context))
        request.add_unredirected_header("X-Android-Package", self.package)
        request.add_unredirected_header("X-Android-Cert", self.certificate)
        return self.opener.open(request, timeout=timeout)
