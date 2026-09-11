import hashlib
import os
import tempfile
import unittest
from unittest.mock import patch

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

    def test_expired_state_is_rejected(self) -> None:
        with SessionLocal() as db:
            state = auth_service.create_state(db, "orcid", "/jurnallar")
            row = db.scalar(select(OAuthState).where(OAuthState.state == state))
            row.created_at = row.created_at - auth_service.STATE_TTL * 2
            db.commit()
            with self.assertRaises(LookupError):
                auth_service.consume_state(db, "orcid", state)
            self.assertIsNone(db.scalar(select(OAuthState).where(OAuthState.state == state)))

    # --- redirect_to -----------------------------------------------------

    def test_safe_redirect_keeps_only_own_site(self) -> None:
        """Ochiq yo'naltirish: begona manzil bosh sahifaga almashadi."""
        self.configure()
        self.assertEqual(auth_service.safe_redirect("/jurnal/fardu?x=1"), "/jurnal/fardu?x=1")
        self.assertEqual(
            auth_service.safe_redirect("http://127.0.0.1:5173/maqola/7-x"),
            "http://127.0.0.1:5173/maqola/7-x",
        )
        for bad in (
            "https://evil.example/",
            "//evil.example/",
            "/\\evil.example",
            "http://127.0.0.1:5173.evil.example/",
            "javascript:alert(1)",
            "/ok\r\nSet-Cookie: x=1",
            "/" + "a" * 3000,
            "",
            None,
        ):
            self.assertIsNone(auth_service.safe_redirect(bad), bad)

    def test_start_stores_sanitized_redirect(self) -> None:
        self.configure()
        response = self.client.get(
            "/api/auth/orcid/start",
            params={"redirect_to": "https://evil.example/phish"},
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 307)
        with SessionLocal() as db:
            rows = list(db.scalars(select(OAuthState).where(OAuthState.provider == "orcid")))
            self.assertTrue(rows)
            self.assertTrue(all(row.redirect_to is None for row in rows if row.redirect_to is not None and "evil" in row.redirect_to))
            self.assertIsNone(rows[-1].redirect_to)

    def _login(self, redirect_to: str | None):
        self.configure()
        with SessionLocal() as db:
            state = auth_service.create_state(db, "orcid", redirect_to)
        identity = auth_service.ProviderIdentity(subject="0000-0001-2345-6789", display_name="Test", orcid="0000-0001-2345-6789")
        with patch.object(auth_service, "exchange_code", return_value=identity):
            return self.client.get(
                "/api/auth/orcid/callback",
                params={"code": "abc", "state": state},
                follow_redirects=False,
            )

    def test_callback_without_redirect_to_succeeds(self) -> None:
        """Ilgari `redirect_to`siz boshlangan kirish har doim 400 bilan yiqilardi."""
        response = self._login(None)
        self.assertEqual(response.status_code, 307)
        self.assertEqual(response.headers["location"], "http://127.0.0.1:5173/")
        self.assertIn(auth_service.SESSION_COOKIE, response.cookies)

    def test_callback_returns_to_requested_page(self) -> None:
        response = self._login("/jurnal/fardu")
        self.assertEqual(response.status_code, 307)
        self.assertEqual(response.headers["location"], "/jurnal/fardu")

    def test_callback_ignores_foreign_redirect_stored_in_db(self) -> None:
        response = self._login("https://evil.example/")
        self.assertEqual(response.status_code, 307)
        self.assertEqual(response.headers["location"], "http://127.0.0.1:5173/")

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

    def test_expired_and_excess_sessions_are_pruned(self) -> None:
        """Muddati o'tganlar va foydalanuvchining ortiqcha sessiyalari o'chirilsin."""
        from datetime import datetime, timedelta, timezone

        user = self.make_user(subject="0000-0002-1825-0090")
        with SessionLocal() as db:
            stored = db.get(User, user.id)
            for _ in range(auth_service.MAX_SESSIONS_PER_USER + 3):
                auth_service.create_session(db, stored)
            count = len(list(db.scalars(select(UserSession).where(UserSession.user_id == user.id))))
            self.assertEqual(count, auth_service.MAX_SESSIONS_PER_USER)

            expired = db.scalar(select(UserSession).where(UserSession.user_id == user.id))
            expired.expires_at = datetime.now(timezone.utc) - timedelta(days=1)
            db.commit()
            auth_service.create_session(db, stored)
            remaining = list(db.scalars(select(UserSession).where(UserSession.user_id == user.id)))
            self.assertNotIn(expired.id, [item.id for item in remaining])

    # --- CSRF ------------------------------------------------------------

    def test_cross_site_mutation_with_cookie_is_rejected(self) -> None:
        self.configure()
        user = self.make_user(subject="0000-0002-1825-0091")
        with SessionLocal() as db:
            token = auth_service.create_session(db, db.get(User, user.id))
        self.client.cookies.set(auth_service.SESSION_COOKIE, token)
        foreign = self.client.post("/api/auth/logout", headers={"Origin": "https://evil.example"})
        self.assertEqual(foreign.status_code, 403)
        fetch = self.client.post("/api/auth/logout", headers={"Sec-Fetch-Site": "cross-site"})
        self.assertEqual(fetch.status_code, 403)
        # Sessiya hali tirik.
        self.client.cookies.set(auth_service.SESSION_COOKIE, token)
        self.assertIsNotNone(self.client.get("/api/auth/me").json()["user"])
        own = self.client.post("/api/auth/logout", headers={"Origin": "http://127.0.0.1:5173"})
        self.assertEqual(own.status_code, 200)

    def test_same_host_origin_is_accepted(self) -> None:
        self.configure()
        user = self.make_user(subject="0000-0002-1825-0092")
        with SessionLocal() as db:
            token = auth_service.create_session(db, db.get(User, user.id))
        self.client.cookies.set(auth_service.SESSION_COOKIE, token)
        response = self.client.post(
            "/api/auth/logout", headers={"Origin": "http://testserver", "Host": "testserver"}
        )
        self.assertEqual(response.status_code, 200)

    # --- e-pochta va admin tayinlash ---------------------------------------

    def test_unverified_google_email_is_not_stored(self) -> None:
        """`grant-admin` pochta bo'yicha ishlaydi — tasdiqlanmagan pochta xavfli."""
        import httpx

        class FakeClient:
            def __init__(self, *args, **kwargs):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def post(self, *args, **kwargs):
                return httpx.Response(200, json={"access_token": "t"}, request=httpx.Request("POST", "https://x"))

            def get(self, *args, **kwargs):
                return httpx.Response(
                    200,
                    json={"sub": "g-1", "name": "G", "email": "someone@example.uz", "email_verified": False},
                    request=httpx.Request("GET", "https://x"),
                )

        self.configure()
        with patch.object(auth_service.httpx, "Client", FakeClient):
            identity = auth_service.exchange_code("google", "code")
        self.assertIsNone(identity.email)

    def test_grant_admin_refuses_ambiguous_identifier(self) -> None:
        with SessionLocal() as db:
            for provider, subject in (("orcid", "0000-0002-1825-0093"), ("google", "g-dup")):
                identity = auth_service.ProviderIdentity(
                    subject=subject, display_name="X", email="dup@example.uz",
                    orcid=subject if provider == "orcid" else None,
                )
                auth_service.upsert_user(db, provider, identity)
            with self.assertRaises(ValueError):
                auth_service.grant_admin(db, "dup@example.uz")
            granted = auth_service.grant_admin(db, "0000-0002-1825-0093")
            self.assertTrue(granted.is_admin)
            auth_service.grant_admin(db, "0000-0002-1825-0093", revoke=True)

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

    # --- ROR ish joyi ---------------------------------------------------

    ROR_RECORD = {
        "id": "https://ror.org/01bmg2a15",
        "names": [
            {"lang": None, "types": ["ror_display"], "value": "Tashkent State Technical University"},
            {"lang": "uz", "types": ["label"], "value": "Toshkent davlat texnika universiteti"},
            {"lang": None, "types": ["acronym"], "value": "TDTU"},
        ],
        "locations": [
            {"geonames_id": 1512569, "geonames_details": {
                "name": "Tashkent", "country_name": "Uzbekistan", "country_code": "UZ"}},
        ],
        "status": "active",
    }

    def session_for(self, subject: str) -> None:
        user = self.make_user(subject=subject)
        with SessionLocal() as db:
            token = auth_service.create_session(db, db.get(User, user.id))
        self.client.cookies.set(auth_service.SESSION_COOKIE, token)

    def fake_ror(self, responses: dict[str, "httpx.Response"], seen: list[str] | None = None):
        import httpx

        from backend.app.services import ror as ror_service

        ror_service.clear_cache()
        self.addCleanup(ror_service.clear_cache)

        class FakeClient:
            def __init__(self, *args, **kwargs):
                self.headers = kwargs.get("headers") or {}

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def get(self, url, params=None):
                key = url + (f"?{params['query']}" if params else "")
                if seen is not None:
                    seen.append(key)
                return responses[key]

        return patch.object(ror_service.httpx, "Client", FakeClient)

    def test_ror_id_normalisation(self) -> None:
        from backend.app.services import ror as ror_service

        self.assertEqual(ror_service.normalise_id("https://ror.org/01BMG2A15"), "01bmg2a15")
        self.assertEqual(ror_service.normalise_id("01bmg2a15"), "01bmg2a15")
        self.assertIsNone(ror_service.normalise_id("11bmg2a15"))  # 0 bilan boshlanmaydi
        self.assertIsNone(ror_service.normalise_id("01bmg2a1"))
        self.assertIsNone(ror_service.normalise_id("https://evil.example/01bmg2a15"))

    def test_ror_search_requires_a_session(self) -> None:
        self.assertEqual(self.client.get("/api/auth/ror/search?q=Tashkent").status_code, 401)

    def test_ror_search_returns_compact_items_and_caches(self) -> None:
        import httpx

        from backend.app.services import ror as ror_service

        self.session_for("0000-0002-1825-0110")
        seen: list[str] = []
        responses = {
            f"{ror_service.API}?Tashkent technical": httpx.Response(
                200, json={"items": [self.ROR_RECORD]}, request=httpx.Request("GET", "https://x")),
        }
        with self.fake_ror(responses, seen):
            first = self.client.get("/api/auth/ror/search?q=Tashkent technical").json()
            self.client.get("/api/auth/ror/search?q=tashkent  TECHNICAL").json()
            short = self.client.get("/api/auth/ror/search?q=Ta").json()
        self.assertEqual(first["items"], [{
            "id": "01bmg2a15",
            "name": "Tashkent State Technical University",
            "localName": "Toshkent davlat texnika universiteti",
            "acronym": "TDTU",
            "city": "Tashkent",
            "country": "Uzbekistan",
            "countryCode": "UZ",
        }])
        self.assertEqual(len(seen), 1, "bir xil qidiruv qayta yuborilmasligi kerak")
        self.assertEqual(short["items"], [])

    def test_ror_outage_is_503_not_500(self) -> None:
        import httpx

        from backend.app.services import ror as ror_service

        self.session_for("0000-0002-1825-0111")
        responses = {
            f"{ror_service.API}?Samarkand": httpx.Response(429, request=httpx.Request("GET", "https://x")),
        }
        with self.fake_ror(responses):
            response = self.client.get("/api/auth/ror/search?q=Samarkand")
        self.assertEqual(response.status_code, 503)

    def test_profile_links_affiliation_to_ror_with_registry_name(self) -> None:
        """Nom foydalanuvchi yuborganidan emas, ROR yozuvidan olinadi."""
        import httpx

        from backend.app.services import ror as ror_service

        self.session_for("0000-0002-1825-0112")
        responses = {
            f"{ror_service.API}/01bmg2a15": httpx.Response(
                200, json=self.ROR_RECORD, request=httpx.Request("GET", "https://x")),
        }
        with self.fake_ror(responses):
            response = self.client.patch(
                "/api/auth/me",
                json={"affiliation": "Soxta nom", "affiliation_ror": "https://ror.org/01bmg2a15"},
            )
        self.assertEqual(response.status_code, 200)
        body = response.json()["user"]
        self.assertEqual(body["affiliationRor"], "01bmg2a15")
        self.assertEqual(body["affiliation"], "Tashkent State Technical University")

        # Matn qo'lda o'zgartirilsa bog'lanish uziladi.
        body = self.client.patch(
            "/api/auth/me", json={"affiliation": "Boshqa institut", "affiliation_ror": ""}
        ).json()["user"]
        self.assertIsNone(body["affiliationRor"])
        self.assertEqual(body["affiliation"], "Boshqa institut")

    def test_profile_rejects_unknown_or_malformed_ror_id(self) -> None:
        import httpx

        from backend.app.services import ror as ror_service

        self.session_for("0000-0002-1825-0113")
        malformed = self.client.patch("/api/auth/me", json={"affiliation_ror": "not-a-ror"})
        self.assertEqual(malformed.status_code, 422)

        responses = {
            f"{ror_service.API}/05a28rw58": httpx.Response(404, request=httpx.Request("GET", "https://x")),
        }
        with self.fake_ror(responses):
            unknown = self.client.patch("/api/auth/me", json={"affiliation_ror": "05a28rw58"})
        self.assertEqual(unknown.status_code, 422)
        self.assertIsNone(self.client.get("/api/auth/me").json()["user"]["affiliationRor"])

    # --- ORCID'dan ish joyi ---------------------------------------------

    @staticmethod
    def employment(name: str, *, start: int = 2020, end: int | None = None,
                   ror: str | None = None, source: str = "ROR") -> dict:
        organization: dict = {"name": name, "address": {"city": "Tashkent", "country": "UZ"}}
        if ror:
            organization["disambiguated-organization"] = {
                "disambiguated-organization-identifier": ror, "disambiguation-source": source}
        return {"summaries": [{"employment-summary": {
            "start-date": {"year": {"value": str(start)}, "month": None, "day": None},
            "end-date": {"year": {"value": str(end)}} if end else None,
            "organization": organization,
        }}]}

    def orcid_login(self, employments, *, orcid: str, status: int = 200) -> dict:
        """ORCID token almashuvi + `/employments` so'rovi mock bilan; natija qatori."""
        import httpx

        seen: list[tuple[str, dict]] = []

        class FakeClient:
            def __init__(self, *args, **kwargs):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def post(self, *args, **kwargs):
                return httpx.Response(
                    200, json={"orcid": orcid, "name": "Orcid Foydalanuvchi", "access_token": "tok"},
                    request=httpx.Request("POST", "https://x"))

            def get(self, url, headers=None, **kwargs):
                seen.append((url, headers or {}))
                if isinstance(employments, Exception):
                    raise employments
                return httpx.Response(status, json=employments, request=httpx.Request("GET", url))

        self.configure()
        with patch.object(auth_service.httpx, "Client", FakeClient):
            identity = auth_service.exchange_code("orcid", "code")
        with SessionLocal() as db:
            user = auth_service.upsert_user(db, "orcid", identity)
            return {"affiliation": user.affiliation, "ror": user.affiliation_ror,
                    "source": user.affiliation_source, "seen": seen}

    def test_current_employment_selection(self) -> None:
        from backend.app.services import orcid_profile

        payload = {"affiliation-group": [
            self.employment("Eski institut", start=2010, end=2015, ror="https://ror.org/05a28rw58"),
            self.employment("Yangi markaz", start=2016, ror="5679", source="RINGGOLD"),
            self.employment("Tashkent State Technical University", start=2016, ror="https://ror.org/01bmg2a15"),
        ]}
        self.assertEqual(
            orcid_profile.current_employment(payload),
            orcid_profile.Affiliation("Tashkent State Technical University", "01bmg2a15"),
        )
        newer = {"affiliation-group": payload["affiliation-group"] + [self.employment("Eng yangi joy", start=2023)]}
        self.assertEqual(orcid_profile.current_employment(newer), orcid_profile.Affiliation("Eng yangi joy"))
        self.assertIsNone(orcid_profile.current_employment({"affiliation-group": [self.employment("X", end=2019)]}))
        self.assertIsNone(orcid_profile.current_employment({}))

    def test_orcid_login_fills_affiliation_from_registry(self) -> None:
        from backend.app.services import ror as ror_service

        payload = {"affiliation-group": [self.employment("TSTU", ror="https://ror.org/01bmg2a15")]}
        registry = {"id": "01bmg2a15", "name": "Tashkent State Technical University"}
        with patch.object(ror_service, "lookup", return_value=registry):
            result = self.orcid_login(payload, orcid="0000-0002-1825-0120")
        self.assertEqual(result["affiliation"], "Tashkent State Technical University")
        self.assertEqual(result["ror"], "01bmg2a15")
        self.assertEqual(result["source"], "orcid")
        url, headers = result["seen"][0]
        self.assertEqual(url, "https://pub.orcid.org/v3.0/0000-0002-1825-0120/employments")
        self.assertEqual(headers.get("Authorization"), "Bearer tok")

    def test_unconfirmed_ror_is_not_linked(self) -> None:
        from backend.app.services import ror as ror_service

        payload = {"affiliation-group": [self.employment("TSTU", ror="https://ror.org/01bmg2a15")]}
        with patch.object(ror_service, "lookup", side_effect=ror_service.RorUnavailable("429")):
            result = self.orcid_login(payload, orcid="0000-0002-1825-0121")
        self.assertEqual((result["affiliation"], result["ror"]), ("TSTU", None))

    def test_orcid_employment_failure_does_not_block_login(self) -> None:
        import httpx

        down = self.orcid_login(httpx.ConnectError("down"), orcid="0000-0002-1825-0122")
        broken = self.orcid_login({"error": "x"}, status=500, orcid="0000-0002-1825-0123")
        for result in (down, broken):
            self.assertIsNone(result["affiliation"])
            self.assertIsNone(result["source"])

    def test_orcid_updates_only_its_own_affiliation(self) -> None:
        orcid = "0000-0002-1825-0124"
        first = self.orcid_login({"affiliation-group": [self.employment("Birinchi universitet")]}, orcid=orcid)
        self.assertEqual((first["affiliation"], first["source"]), ("Birinchi universitet", "orcid"))
        # ORCID'da ish joyi almashsa, avtomatik qiymat ham yangilanadi.
        second = self.orcid_login(
            {"affiliation-group": [self.employment("Ikkinchi universitet", start=2024)]}, orcid=orcid)
        self.assertEqual(second["affiliation"], "Ikkinchi universitet")

        with SessionLocal() as db:
            token = auth_service.create_session(db, db.scalar(select(User).where(User.orcid == orcid)))
        self.client.cookies.set(auth_service.SESSION_COOKIE, token)
        # Ish joyiga tegmagan saqlash manbani o'zgartirmaydi.
        body = self.client.patch("/api/auth/me", json={
            "display_name": "Yangi Ism", "affiliation": "Ikkinchi universitet", "affiliation_ror": ""}).json()["user"]
        self.assertEqual(body["affiliationSource"], "orcid")
        # Foydalanuvchi o'zi o'zgartirgach, kirish uni ustidan yozmaydi.
        body = self.client.patch("/api/auth/me", json={
            "affiliation": "O'zim yozgan institut", "affiliation_ror": ""}).json()["user"]
        self.assertEqual(body["affiliationSource"], "manual")
        third = self.orcid_login({"affiliation-group": [self.employment("Uchinchi joy", start=2025)]}, orcid=orcid)
        self.assertEqual((third["affiliation"], third["source"]), ("O'zim yozgan institut", "manual"))

    def test_existing_affiliation_without_source_is_kept(self) -> None:
        """Migratsiyadan oldingi qiymatlar foydalanuvchiniki deb hisoblanadi."""
        orcid = "0000-0002-1825-0125"
        user = self.make_user(subject=orcid)
        with SessionLocal() as db:
            db.get(User, user.id).affiliation = "Avval kiritilgan"
            db.commit()
        result = self.orcid_login({"affiliation-group": [self.employment("ORCID'dagi joy")]}, orcid=orcid)
        self.assertEqual((result["affiliation"], result["source"]), ("Avval kiritilgan", None))

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
