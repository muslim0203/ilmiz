import hashlib
import os
import tempfile
import unittest

database_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
database_file.close()
os.environ.setdefault("DATABASE_URL", f"sqlite:///{database_file.name}")

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select  # noqa: E402

from backend.app.db import SessionLocal, engine  # noqa: E402
from backend.app.main import app  # noqa: E402
from backend.app.models import OAuthState, User, UserSession  # noqa: E402
from backend.app.services import auth as auth_service  # noqa: E402

ADMIN_TOKEN = "test-admin-token"

PROVIDER_ENV = {
    "ORCID_CLIENT_ID": "test-orcid-id",
    "ORCID_CLIENT_SECRET": "test-orcid-secret",
    "GOOGLE_CLIENT_ID": "test-google-id",
    "GOOGLE_CLIENT_SECRET": "test-google-secret",
    "ILMIZ_PUBLIC_URL": "http://127.0.0.1:5173",
}


class AuthTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.context = TestClient(app)
        cls.client = cls.context.__enter__()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.context.__exit__(None, None, None)
        engine.dispose()
        for suffix in ("", "-wal", "-shm"):
            try:
                os.unlink(database_file.name + suffix)
            except OSError:
                pass

    def setUp(self) -> None:
        self.client.cookies.clear()

    def configure(self) -> None:
        for key, value in PROVIDER_ENV.items():
            os.environ[key] = value
        self.addCleanup(lambda: [os.environ.pop(key, None) for key in PROVIDER_ENV])

    # --- provayderlar ---------------------------------------------------

    def test_unconfigured_providers_are_not_offered(self) -> None:
        """Sozlanmagan provayder tugma sifatida ko'rsatilmasligi kerak."""
        for key in PROVIDER_ENV:
            os.environ.pop(key, None)
        body = self.client.get("/api/auth/providers").json()
        self.assertEqual(body["providers"], [])

    def test_configured_providers_are_listed(self) -> None:
        self.configure()
        body = self.client.get("/api/auth/providers").json()
        self.assertEqual(sorted(body["providers"]), ["google", "orcid"])

    def test_start_without_configuration_is_refused(self) -> None:
        for key in PROVIDER_ENV:
            os.environ.pop(key, None)
        response = self.client.get("/api/auth/orcid/start", follow_redirects=False)
        self.assertEqual(response.status_code, 503)

    def test_unknown_provider_is_404(self) -> None:
        self.configure()
        response = self.client.get("/api/auth/facebook/start", follow_redirects=False)
        self.assertEqual(response.status_code, 404)

    def test_start_redirects_with_state_and_redirect_uri(self) -> None:
        self.configure()
        response = self.client.get("/api/auth/orcid/start", follow_redirects=False)
        self.assertEqual(response.status_code, 307)
        location = response.headers["location"]
        self.assertTrue(location.startswith("https://orcid.org/oauth/authorize"))
        self.assertIn("state=", location)
        self.assertIn("redirect_uri=", location)
        self.assertIn("client_id=test-orcid-id", location)

    # --- state ----------------------------------------------------------

    def test_state_is_single_use(self) -> None:
        """CSRF himoyasi: bir state ikki marta ishlatilmasin."""
        with SessionLocal() as db:
            state = auth_service.create_state(db, "orcid", None)
            self.assertIsNotNone(db.scalar(select(OAuthState).where(OAuthState.state == state)))
            auth_service.consume_state(db, "orcid", state)
            self.assertIsNone(db.scalar(select(OAuthState).where(OAuthState.state == state)))

    def test_callback_rejects_unknown_state(self) -> None:
        self.configure()
        response = self.client.get(
            "/api/auth/orcid/callback",
            params={"code": "abc", "state": "yaroqsiz"},
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 400)

    def test_callback_without_code_is_rejected(self) -> None:
        self.configure()
        response = self.client.get("/api/auth/orcid/callback", follow_redirects=False)
        self.assertEqual(response.status_code, 400)

    def test_user_denial_is_not_an_error(self) -> None:
        """Foydalanuvchi ruxsat bermasa, bu xato emas — bosh sahifaga qaytamiz."""
        self.configure()
        response = self.client.get(
            "/api/auth/orcid/callback",
            params={"error": "access_denied"},
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 307)
        self.assertIn("auth=bekor", response.headers["location"])

    # --- sessiya --------------------------------------------------------

    def make_user(self, provider: str = "orcid", subject: str = "0000-0002-1825-0097") -> User:
        with SessionLocal() as db:
            identity = auth_service.ProviderIdentity(
                subject=subject,
                display_name="Test Tadqiqotchi",
                orcid=subject if provider == "orcid" else None,
            )
            user = auth_service.upsert_user(db, provider, identity)
            return user

    def test_session_token_is_stored_hashed(self) -> None:
        """Baza o'qilib qolsa ham tayyor token qo'lga tushmasligi kerak."""
        user = self.make_user()
        with SessionLocal() as db:
            token = auth_service.create_session(db, db.get(User, user.id))
            stored = db.scalar(select(UserSession).where(UserSession.user_id == user.id))
            self.assertNotEqual(stored.token_hash, token)
            self.assertEqual(stored.token_hash, hashlib.sha256(token.encode()).hexdigest())

    def test_me_is_null_without_session(self) -> None:
        self.assertIsNone(self.client.get("/api/auth/me").json()["user"])

    def test_me_returns_user_with_session_cookie(self) -> None:
        user = self.make_user(subject="0000-0002-1825-0098")
        with SessionLocal() as db:
            token = auth_service.create_session(db, db.get(User, user.id))
        self.client.cookies.set(auth_service.SESSION_COOKIE, token)
        body = self.client.get("/api/auth/me").json()
        self.assertEqual(body["user"]["orcid"], "0000-0002-1825-0098")
        self.assertEqual(body["user"]["provider"], "orcid")

    def test_invalid_token_is_ignored(self) -> None:
        self.client.cookies.set(auth_service.SESSION_COOKIE, "yolgon-token")
        self.assertIsNone(self.client.get("/api/auth/me").json()["user"])

    def test_logout_revokes_the_session(self) -> None:
        user = self.make_user(subject="0000-0002-1825-0099")
        with SessionLocal() as db:
            token = auth_service.create_session(db, db.get(User, user.id))
        self.client.cookies.set(auth_service.SESSION_COOKIE, token)
        self.assertIsNotNone(self.client.get("/api/auth/me").json()["user"])

        self.client.post("/api/auth/logout")
        self.client.cookies.set(auth_service.SESSION_COOKIE, token)
        self.assertIsNone(self.client.get("/api/auth/me").json()["user"])

    # --- profil ---------------------------------------------------------

    def test_profile_update_requires_a_session(self) -> None:
        response = self.client.patch("/api/auth/me", json={"display_name": "X"})
        self.assertEqual(response.status_code, 401)

    def test_profile_update_stores_scholar_link(self) -> None:
        """Google Scholar OAuth provayderi emas — havola qo'lda kiritiladi."""
        user = self.make_user(subject="0000-0002-1825-0100")
        with SessionLocal() as db:
            token = auth_service.create_session(db, db.get(User, user.id))
        self.client.cookies.set(auth_service.SESSION_COOKIE, token)
        response = self.client.patch(
            "/api/auth/me",
            json={
                "display_name": "Yangi Ism",
                "affiliation": "Toshkent davlat universiteti",
                "scholar_url": "https://scholar.google.com/citations?user=ABC123",
            },
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()["user"]
        self.assertEqual(body["displayName"], "Yangi Ism")
        self.assertEqual(body["affiliation"], "Toshkent davlat universiteti")
        self.assertIn("scholar.google.com", body["scholarUrl"])

    def test_blank_name_is_rejected(self) -> None:
        user = self.make_user(subject="0000-0002-1825-0101")
        with SessionLocal() as db:
            token = auth_service.create_session(db, db.get(User, user.id))
        self.client.cookies.set(auth_service.SESSION_COOKIE, token)
        response = self.client.patch("/api/auth/me", json={"display_name": "   "})
        self.assertEqual(response.status_code, 422)

    # --- admin huquqi ---------------------------------------------------

    def admin_session(self, subject: str) -> str:
        from backend.app.models import User as UserModel

        user = self.make_user(subject=subject)
        with SessionLocal() as db:
            row = db.get(UserModel, user.id)
            row.is_admin = True
            db.commit()
            return auth_service.create_session(db, row)

    def test_plain_user_cannot_reach_admin_api(self) -> None:
        os.environ["ILMIZ_ADMIN_TOKEN"] = ADMIN_TOKEN
        try:
            user = self.make_user(subject="0000-0004-0000-0001")
            with SessionLocal() as db:
                token = auth_service.create_session(db, db.get(User, user.id))
            self.client.cookies.set(auth_service.SESSION_COOKIE, token)
            self.assertEqual(self.client.get("/api/admin/dashboard").status_code, 401)
        finally:
            os.environ.pop("ILMIZ_ADMIN_TOKEN", None)

    def test_admin_user_reaches_admin_api_without_token(self) -> None:
        """Asosiy maqsad: admin o'z hisobi bilan kiradi, alohida token kerak emas."""
        for key in PROVIDER_ENV:
            os.environ.pop(key, None)
        os.environ.pop("ILMIZ_ADMIN_TOKEN", None)
        self.client.cookies.set(auth_service.SESSION_COOKIE, self.admin_session("0000-0004-0000-0002"))
        response = self.client.get("/api/admin/dashboard")
        self.assertEqual(response.status_code, 200)
        self.assertIn("journals", response.json())

    def test_token_still_works_as_a_fallback(self) -> None:
        """Birinchi adminni tayinlash uchun token yo'li ochiq qolishi kerak."""
        os.environ["ILMIZ_ADMIN_TOKEN"] = ADMIN_TOKEN
        try:
            self.assertEqual(
                self.client.get("/api/admin/dashboard", headers={"X-Admin-Token": ADMIN_TOKEN}).status_code,
                200,
            )
        finally:
            os.environ.pop("ILMIZ_ADMIN_TOKEN", None)

    def test_me_reports_admin_flag(self) -> None:
        self.client.cookies.set(auth_service.SESSION_COOKIE, self.admin_session("0000-0004-0000-0003"))
        self.assertTrue(self.client.get("/api/auth/me").json()["user"]["isAdmin"])

    def test_me_reports_non_admin(self) -> None:
        user = self.make_user(subject="0000-0004-0000-0004")
        with SessionLocal() as db:
            token = auth_service.create_session(db, db.get(User, user.id))
        self.client.cookies.set(auth_service.SESSION_COOKIE, token)
        self.assertFalse(self.client.get("/api/auth/me").json()["user"]["isAdmin"])

    def test_grant_and_revoke_admin(self) -> None:
        user = self.make_user(subject="0000-0004-0000-0005")
        with SessionLocal() as db:
            db.get(User, user.id).email = "admin@example.uz"
            db.commit()
            granted = auth_service.grant_admin(db, "admin@example.uz")
            self.assertTrue(granted.is_admin)
            revoked = auth_service.grant_admin(db, "admin@example.uz", revoke=True)
            self.assertFalse(revoked.is_admin)
            self.assertIsNone(auth_service.grant_admin(db, "yoq@example.uz"))

    # --- hisoblarni bog'lash --------------------------------------------

    def test_same_orcid_does_not_create_a_second_account(self) -> None:
        """Bir odam ORCID bilan ikki marta kirsa, bitta hisob bo'lishi kerak."""
        first = self.make_user(subject="0000-0003-1111-2222")
        second = self.make_user(subject="0000-0003-1111-2222")
        self.assertEqual(first.id, second.id)

    def test_google_and_orcid_are_separate_without_a_shared_orcid(self) -> None:
        orcid_user = self.make_user(provider="orcid", subject="0000-0003-3333-4444")
        google_user = self.make_user(provider="google", subject="google-sub-1")
        self.assertNotEqual(orcid_user.id, google_user.id)


if __name__ == "__main__":
    unittest.main()
