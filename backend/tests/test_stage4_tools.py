import json
import os
import re
import unittest
from unittest.mock import patch

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.app.db import Base, get_db
from backend.app.main import app as main_app
from backend.app.models import Article, Journal, OakImportRun, OakRegistryEntry
from backend.app.seo_routes import router
from backend.app.services import citation_tool, seo

TOKEN = "test-admin-token"
HEADERS = {"X-Admin-Token": TOKEN}
LONG_BODY = "## Kirish\nBu qo‘llanma maqola tayyorlash bosqichlarini tushuntiradi. " + "Matn davomi. " * 160


class Stage4Test(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {"ILMIZ_SITE_URL": "https://seo.example", "ILMIZ_NOINDEX": "", "ILMIZ_ADMIN_TOKEN": TOKEN})
        self.env.start()
        self.engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        journal = Journal(slug="tib", name="Tibbiyot jurnali", short_name="T", publisher="P", city="Toshkent", fields=["Tibbiyot"])
        self.db.add(journal)
        self.db.flush()
        run = OakImportRun(source_url="https://oak.uz", status="succeeded")
        self.db.add(run)
        self.db.flush()
        self.db.add(OakRegistryEntry(import_run_id=run.id, journal_id=journal.id, source_key="k1", name="Tibbiyot jurnali",
                                     specialty_code="14.00.00", area="Тиббиёт фанлари"))
        self.db.add(Article(journal_id=journal.id, title="Yurak kasalliklarini davolash", normalized_title="yurak",
                            authors=["Karimov A."], abstract="Annotatsiya. " * 50, keywords=["yurak"],
                            publication_year=2025, volume="3", issue="2", pages="10-15", doi="10.1234/abc"))
        self.db.commit()
        seo.reset_cache()
        site = FastAPI()
        site.include_router(router)
        site.dependency_overrides[get_db] = lambda: self.db
        self.site = TestClient(site)
        main_app.dependency_overrides[get_db] = lambda: self.db
        self.api = TestClient(main_app)

    def tearDown(self):
        main_app.dependency_overrides.clear()
        self.site.close()
        self.db.close()
        self.engine.dispose()
        seo.reset_cache()
        self.env.stop()

    def test_specialty_code_redirects_to_field_page_with_code(self):
        response = self.site.get("/oak-jurnallar/ixtisoslik/14.00.00", follow_redirects=False)
        self.assertEqual(response.status_code, 301)
        self.assertEqual(response.headers["location"], "/soha/tibbiyot")
        self.assertEqual(self.site.get("/oak-jurnallar/ixtisoslik/99.00.00", follow_redirects=False).status_code, 404)
        page = self.site.get("/soha/tibbiyot").text
        self.assertIn("OAK ixtisoslik shifri: <strong>14.00.00</strong>", page)
        self.assertIn("<title>Tibbiyot (14.00.00) — OAK jurnallari</title>", page)

    def test_citation_page_has_real_example_and_tool_schema(self):
        page = self.site.get("/iqtibos").text
        self.assertIn("<h1>Iqtibos generatori", page)
        self.assertIn("Karimov A. Yurak kasalliklarini davolash // Tibbiyot jurnali. – 2025.", page)
        self.assertIn('"@type":"WebApplication"', page.replace(" ", ""))

    def test_format_api_and_validation(self):
        result = self.api.post("/api/citations/format", json={
            "title": "Sarlavha", "journal": "Jurnal", "authors": ["Aliyev B."], "year": 2024, "pages": "1-5",
        }).json()
        self.assertEqual(set(result["formats"]), {"gost", "apa", "mla", "chicago"})
        self.assertTrue(result["formats"]["gost"].startswith("Aliyev B. Sarlavha // Jurnal. – 2024."))
        self.assertNotIn("B..", result["formats"]["mla"])  # "Aliyev B." + format nuqtasi
        uzbek = self.api.post("/api/citations/format", json={
            "title": "S", "journal": "J", "authors": ["A B."], "pages": "1-5", "language": "uz"}).json()
        self.assertIn("– B. 1-5.", uzbek["formats"]["gost"])
        self.assertEqual(self.api.post("/api/citations/format", json={"title": "", "journal": "J"}).status_code, 422)

    def test_doi_lookup_uses_database_then_crossref(self):
        local = self.api.get("/api/citations/doi", params={"doi": "https://doi.org/10.1234/ABC"}).json()
        self.assertEqual(local["source"], "ilmiz")
        self.assertTrue(local["articleUrl"].startswith("/maqola/"))

        def handler(request: httpx.Request) -> httpx.Response:
            self.assertIn("10.5555/xyz", str(request.url))
            return httpx.Response(200, json={"message": {
                "title": ["Remote <i>paper</i>"], "container-title": ["Remote Journal"],
                "author": [{"family": "Smith", "given": "John Paul"}], "issued": {"date-parts": [[2023]]},
                "volume": "7", "page": "1-9",
            }})

        client = httpx.Client(transport=httpx.MockTransport(handler))
        citation_tool._cache.clear()
        remote = citation_tool.lookup_doi(self.db, "doi:10.5555/xyz", client=client)
        self.assertEqual(remote["source"], "crossref")
        self.assertEqual(remote["fields"]["title"], "Remote paper")
        self.assertIn("Smith J. P.", remote["formats"]["apa"])
        self.assertEqual(self.api.get("/api/citations/doi", params={"doi": "yaroqsiz"}).status_code, 422)

    def test_guides_crud_render_and_sitemap(self):
        short = self.api.post("/api/admin/guides", headers=HEADERS, json={
            "slug": "oak-talablari", "title": "OAK talablari", "body": "Qisqa", "isPublished": True})
        self.assertEqual(short.status_code, 422)  # 150 so'zdan kam — chop etilmaydi

        draft = self.api.post("/api/admin/guides", headers=HEADERS, json={
            "slug": "oak-talablari", "title": "OAK talablari", "summary": "Qisqacha", "body": LONG_BODY + "\n<script>x</script>"}).json()
        self.assertEqual(self.site.get("/yoriqnoma/oak-talablari").status_code, 404)  # qoralama ko'rinmaydi
        self.assertIn('content="noindex', self.site.get("/yoriqnoma").text)

        published = self.api.put(f"/api/admin/guides/{draft['id']}", headers=HEADERS, json={
            "slug": "oak-talablari", "title": "OAK talablari", "summary": "Qisqacha",
            "body": LONG_BODY + "\n<script>x</script>", "isPublished": True})
        self.assertEqual(published.status_code, 200)
        page = self.site.get("/yoriqnoma/oak-talablari").text
        self.assertIn("<h2>Kirish</h2>", page)
        self.assertIn("&lt;script&gt;x&lt;/script&gt;", page)
        graph = [json.loads(item) for item in re.findall(r'<script type="application/ld\+json">(.*?)</script>', page, re.S)]
        self.assertTrue(any(item.get("@type") == "Article" for item in graph))
        self.assertIn("/yoriqnoma/oak-talablari", self.site.get("/sitemap-pages.xml").text)
        self.assertIn("/iqtibos", self.site.get("/sitemap-pages.xml").text)

        self.assertEqual(self.api.delete(f"/api/admin/guides/{draft['id']}", headers=HEADERS).status_code, 200)
        self.assertEqual(self.site.get("/yoriqnoma/oak-talablari").status_code, 404)


if __name__ == "__main__":
    unittest.main()
