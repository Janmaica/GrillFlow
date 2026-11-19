import base64
import io
import json
import ssl
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs
from unittest.mock import patch

from firebase_auth import AuthError, FirebaseAuth, VerificationRequired, account_directory, signup_fields
from order_store import OrderStore
from product_store import ProductFields, ProductStore
from session_vault import SessionVault


class MemoryVault:
    def __init__(self):
        self.record = None

    def load(self):
        return self.record

    def save(self, record):
        self.record = record

    def clear(self):
        self.record = None


class StubOpener:
    def __init__(self):
        self.requests = []
        self.responses = []

    def open(self, request, *, timeout):
        self.requests.append((request.full_url.split("?")[0], request.data, timeout))
        result = self.responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return io.BytesIO(json.dumps(result).encode())


def firebase_error(code):
    data = json.dumps({"error": {"message": code}}).encode()
    return HTTPError("https://example.invalid", 400, "", {}, io.BytesIO(data))


def token_payload(uid="owner-A", *, project="grillflow-test", refresh=False):
    claims = {"aud": project, "iss": f"https://securetoken.google.com/{project}", "sub": uid}
    payload = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("=")
    keys = ("user_id", "id_token", "refresh_token", "expires_in") if refresh else (
        "localId", "idToken", "refreshToken", "expiresIn",
    )
    return dict(zip(keys, (uid, f"header.{payload}.signature", "test-refresh-credential", "3600")))


class FirebaseAuthTests(unittest.TestCase):
    def setUp(self):
        self.opener = StubOpener()
        self.vault = MemoryVault()
        self.now = 1000
        self.auth = FirebaseAuth(self.vault, api_key="fixture-key", project="grillflow-test",
                                 opener=self.opener, offline_hours=1, now=lambda: self.now)

    def test_loads_android_config_and_rejects_ambiguous_keys(self):
        with TemporaryDirectory() as directory:
            config = Path(directory) / "google-services (3).json"
            data = {"project_info": {"project_id": "fixture-project"},
                    "client": [{"api_key": [{"current_key": "fixture-key"}]}]}
            with patch("firebase_auth.FIREBASE_CONFIG", config):
                config.write_text(json.dumps(data), encoding="utf-8")
                auth = FirebaseAuth.from_project_config(self.vault)
                self.assertEqual((auth.api_key, auth.project), ("fixture-key", "fixture-project"))
                data["client"][0]["client_info"] = {
                    "android_client_info": {"package_name": "com.grillflow.app"},
                }
                data["client"].append({"api_key": [{"current_key": "another-key"}]})
                config.write_text(json.dumps(data), encoding="utf-8")
                android = FirebaseAuth.from_project_config(self.vault, android=True)
                self.assertEqual((android.api_key, android.project), ("fixture-key", "fixture-project"))
                auth = FirebaseAuth.from_project_config(self.vault)
                with self.assertRaises(AuthError) as caught:
                    auth.sign_in("ana@example.com", "password")
                self.assertEqual(caught.exception.code, "CONFIG")

    def test_registration_and_email_verification_endpoints(self):
        self.opener.responses.extend([
            token_payload(), {}, {}, {"users": [{"localId": "owner-A", "emailVerified": False}]},
            token_payload(refresh=True), {"users": [{"localId": "owner-A", "emailVerified": True}]},
        ])
        name, email, password = signup_fields("  Ana  Cruz ", " ANA@EXAMPLE.COM ", "password9", "password9")
        tokens = self.auth.register(email, password)
        self.auth.update_name(tokens, name)
        self.auth.send_verification(tokens)
        self.assertFalse(self.auth.is_verified(tokens))
        self.assertIsNone(self.vault.load())
        tokens = self.auth.refresh(tokens.refresh_token)
        self.assertTrue(self.auth.is_verified(tokens))
        session = self.auth.remember(tokens)
        self.assertEqual(session.expires_at, 4600)
        self.assertNotIn("test-refresh-credential", repr(session))
        self.assertNotIn(password, repr(self.vault.load()))
        identity = "https://identitytoolkit.googleapis.com/v1/accounts:"
        self.assertEqual([url for url, _, _ in self.opener.requests], [
            identity + "signUp", identity + "update", identity + "sendOobCode", identity + "lookup",
            "https://securetoken.googleapis.com/v1/token", identity + "lookup",
        ])
        self.assertEqual(json.loads(self.opener.requests[1][1])["displayName"], "Ana Cruz")
        self.assertEqual(json.loads(self.opener.requests[2][1])["requestType"], "VERIFY_EMAIL")
        self.assertEqual(parse_qs(self.opener.requests[4][1].decode())["grant_type"], ["refresh_token"])

    def test_invalid_inputs_and_friendly_errors(self):
        for fields in (("", "a@b.co", "password", "password"),
                       ("Ana", "broken", "password", "password"),
                       ("Ana", "a@b.co", "short", "short"),
                       ("Ana", "a@b.co", "password", "other")):
            with self.subTest(fields=fields), self.assertRaises(ValueError):
                signup_fields(*fields)
        self.opener.responses.append(firebase_error("INVALID_LOGIN_CREDENTIALS : server details"))
        with self.assertRaisesRegex(AuthError, "^Incorrect email or password\\.$"):
            self.auth.sign_in("ana@example.com", "wrong")
        self.opener.responses.append(URLError(OSError("network failed")))
        with self.assertRaisesRegex(AuthError, "^Unable to connect"):
            self.auth.sign_in("ana@example.com", "wrong")

    def test_reset_has_same_result_for_unknown_and_known_addresses(self):
        self.opener.responses.extend([{}, firebase_error("EMAIL_NOT_FOUND")])
        for email in ("known@example.com", "unknown@example.com"):
            self.assertIsNone(self.auth.reset_password(email))
        self.assertTrue(all(json.loads(data)["requestType"] == "PASSWORD_RESET"
                            for _, data, _ in self.opener.requests))

    def test_restore_refreshes_expired_id_token_and_offline_window_is_bounded(self):
        self.opener.responses.append(token_payload())
        original = self.auth.remember(self.auth.sign_in("ana@example.com", "password"))
        self.now = original.expires_at + 5
        self.opener.responses.extend([
            token_payload(refresh=True), {"users": [{"localId": original.uid, "emailVerified": True}]},
        ])
        restored = self.auth.restore()
        self.assertEqual(restored.verified_at, self.now)
        self.assertGreater(restored.expires_at, original.expires_at)
        self.now += 3599
        self.opener.responses.append(URLError(OSError("offline")))
        self.assertTrue(self.auth.restore().offline)
        self.assertEqual(self.vault.load()["verified_at"], restored.verified_at)
        self.now += 1
        self.opener.responses.append(URLError(OSError("offline")))
        with self.assertRaisesRegex(AuthError, "offline access has expired"):
            self.auth.restore()

    def test_invalidated_or_mismatched_accounts_cannot_use_offline_fallback(self):
        self.opener.responses.append(token_payload())
        self.auth.remember(self.auth.sign_in("ana@example.com", "password"))
        saved = self.vault.load()
        for error in (firebase_error("USER_DISABLED"), token_payload(uid="owner-B", refresh=True)):
            self.vault.save(saved)
            self.opener.responses.append(error)
            with self.assertRaises(AuthError):
                self.auth.restore()
            self.assertIsNone(self.vault.load())
        self.vault.save(saved)
        self.opener.responses.append(URLError(ssl.SSLCertVerificationError("untrusted")))
        with self.assertRaises(AuthError) as caught:
            self.auth.restore()
        self.assertEqual(caught.exception.code, "SERVICE")

    def test_rejects_a_different_firebase_project(self):
        self.opener.responses.append(token_payload(project="other-project"))
        with self.assertRaises(AuthError) as caught:
            self.auth.sign_in("ana@example.com", "password")
        self.assertEqual(caught.exception.code, "CONFIG")

    def test_profile_name_round_trip_offline_cache_and_authenticated_password_reset(self):
        record = {"localId": "owner-A", "displayName": "Ana", "email": "ana@example.com", "emailVerified": True}
        self.opener.responses.extend([token_payload(), {"users": [record]}])
        tokens = self.auth.sign_in("ana@example.com", "password")
        session = self.auth.remember(tokens, self.auth.lookup_profile(tokens))
        self.opener.responses.extend([
            token_payload(refresh=True), {"users": [record]}, {"localId": "owner-A", "displayName": "Ana Cruz"},
        ])
        updated = self.auth.change_profile_name(session, "  Ana   Cruz ")
        self.assertEqual((updated.uid, updated.profile.name), (session.uid, "Ana Cruz"))
        self.assertEqual(json.loads(self.opener.requests[-1][1])["displayName"], "Ana Cruz")
        reopened = FirebaseAuth(self.vault, api_key="fixture-key", project="grillflow-test",
                                opener=self.opener, now=lambda: self.now)
        self.opener.responses.append(URLError(OSError("offline")))
        cached = reopened.restore()
        self.assertTrue(cached.offline)
        self.assertEqual(cached.profile, updated.profile)
        record = dict(record, displayName="Ana Cruz")
        self.opener.responses.extend([token_payload(refresh=True), {"users": [record]}, {}])
        self.assertEqual(self.auth.send_profile_password_reset(updated).profile, updated.profile)
        self.assertEqual(json.loads(self.opener.requests[-1][1]), {
            "requestType": "PASSWORD_RESET", "email": "ana@example.com",
        })
        self.opener.responses.extend([token_payload(refresh=True), {"users": [record]},
                                     URLError(OSError("offline"))])
        with self.assertRaisesRegex(AuthError, "Check your internet connection"):
            self.auth.change_profile_name(updated, "Another Name")
        self.assertEqual(self.vault.load()["name"], "Ana Cruz")

    def test_unverified_profile_returns_to_verification_and_clears_cached_session(self):
        self.opener.responses.append(token_payload())
        self.auth.remember(self.auth.sign_in("ana@example.com", "password"))
        self.opener.responses.extend([
            token_payload(refresh=True),
            {"users": [{"localId": "owner-A", "email": "ana@example.com", "emailVerified": False}]},
        ])
        with self.assertRaises(VerificationRequired) as caught:
            self.auth.restore()
        self.assertEqual(caught.exception.email, "ana@example.com")
        self.assertIsNone(self.vault.load())

    def test_account_paths_isolate_data_and_legacy_file(self):
        with TemporaryDirectory() as directory:
            shared = Path(directory) / "grillflow.sqlite3"
            shared.write_bytes(b"legacy data fixture")
            first = account_directory(directory, "project", "../owner-A")
            second = account_directory(directory, "project", "owner-B")
            self.assertNotEqual(first, account_directory(directory, "other-project", "../owner-A"))
            self.assertEqual(first.parent, second.parent)
            a, b = ProductStore(first), ProductStore(second)
            order_a, order_b = OrderStore(a), OrderStore(b)
            order_a.initialize()
            order_b.initialize()
            a.add(ProductFields("Skewer", 1000, 5, "Stick"))
            self.assertEqual(b.list_products(), [])
            b.add(ProductFields("Rice", 500, 3, "Serving"))
            order_a.reset_all_data()
            self.assertEqual(a.list_products(), [])
            self.assertEqual([product["name"] for product in b.list_products()], ["Rice"])
            self.assertEqual(shared.read_bytes(), b"legacy data fixture")

    @unittest.skipUnless(sys.platform == "win32", "Windows DPAPI test")
    def test_windows_vault_persists_only_ciphertext_and_clears_it(self):
        with TemporaryDirectory() as directory:
            vault = SessionVault(directory, "win")
            self.assertIsNone(vault.load())
            self.opener.responses.append(token_payload())
            self.auth.vault = vault
            saved = self.auth.remember(self.auth.sign_in("ana@example.com", "password"))
            self.assertNotIn(saved.refresh_token.encode(), vault.path.read_bytes())
            fresh_opener = StubOpener()
            fresh_opener.responses.extend([
                token_payload(refresh=True), {"users": [{"localId": saved.uid, "emailVerified": True}]},
            ])
            restarted = FirebaseAuth(SessionVault(directory, "win"), opener=fresh_opener,
                                     api_key="fixture-key", project="grillflow-test")
            self.assertEqual(restarted.restore().uid, saved.uid)
            vault.clear()
            self.assertIsNone(vault.load())
