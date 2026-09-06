"""SEO invariants using an isolated database, never the harvested live database."""
import json
import os
import re
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch
from urllib.parse import quote

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.app.db import Base, get_db
from backend.app.models import Article, Journal
from backend.app.seo_routes import router
from backend.app.services import seo


class SeoRegressionTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {"ILMIZ_SITE_URL": "https://seo.example", "ILMIZ_NOINDEX": ""})
        self.env.start()
        self.engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        journal = Journal(slug="test-journal", name="Test journal", short_name="Test", publisher="Publisher", city="Toshkent")
        self.db.add(journal)
        self.db.flush()
        self.db.add_all([
            Article(journal_id=journal.id, title=f"Paper {index}", normalized_title=f"paper {index}",
                    authors=["Researcher, First", "Researcher, Second"], publication_year=2025,
                    publication_date="2025-02-20", abstract="Full author-written abstract. " * 100,
                    pdf_url="https://publisher.example/paper.pdf")
            for index in range(121)
        ])
        self.db.commit()
        seo.reset_cache()
        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_db] = lambda: self.db
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        self.db.close()
        self.engine.dispose()
        seo.reset_cache()
        self.env.stop()

    def test_archive_covers_every_article_once(self):
        seen = []
        for page in (1, 2, 3):
            suffix = f"?sahifa={page}" if page > 1 else ""
            response = self.client.get("/jurnal/test-journal/2025" + suffix)
            self.assertEqual(response.status_code, 200)
            seen.extend(re.findall(r'class="seo-item-title" href="/maqola/(\d+)-', response.text))
        self.assertEqual(len(seen), 121)
        self.assertEqual(len(set(seen)), 121)

    def test_archive_has_real_next_page_links(self):
        response = self.client.get("/jurnal/test-journal/2025")
        self.assertIn('href="/jurnal/test-journal/2025?sahifa=2"', response.text)

    def test_out_of_range_pages_are_real_404(self):
        for path in ("/maqolalar?sahifa=9999", "/jurnallar?sahifa=2", "/jurnal/test-journal/2025?sahifa=4"):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 404)
            self.assertIn("noindex", response.headers["X-Robots-Tag"])

    def test_article_page_sizes_match_browser(self):
        page = self.client.get("/maqolalar?sahifa=2").text
        self.assertEqual(len(re.findall('class="seo-item-title"', page)), 50)
        self.assertIn('canonical" href="https://seo.example/maqolalar?sahifa=2"', page)

    def test_metadata_endpoint_matches_document(self):
        path = "/maqola/1-paper-0"
        doc = self.client.get(path).text
        payload = self.client.get("/api/seo", params={"path": path}).json()
        self.assertIn(payload["head"], doc)
        self.assertIn(payload["body"], doc)
        self.assertIn('citation_title" content="Paper 0"', payload["head"])

    def test_metadata_endpoint_rejects_external_targets(self):
        for path in ("https://outside.example", "//outside.example", "javascript:alert(1)"):
            self.assertEqual(self.client.get("/api/seo", params={"path": path}).status_code, 400)

    def test_metadata_missing_page_is_explicit(self):
        payload = self.client.get("/api/seo", params={"path": "/missing"}).json()
        self.assertEqual(payload["status"], 404)
        self.assertIn("noindex", payload["head"])

    def test_staging_metadata_cannot_enable_indexing(self):
        with patch.dict(os.environ, {"ILMIZ_NOINDEX": "1", "ILMIZ_ALLOW_INDEXING": "1"}):
            payload = self.client.get("/api/seo", params={"path": "/"}).json()
            self.assertIn('name="robots" content="noindex', payload["head"])

    def test_unknown_domain_is_not_invented(self):
        with patch.dict(os.environ, {"ILMIZ_SITE_URL": "", "ILMIZ_PUBLIC_URL": "http://127.0.0.1:18080"}):
            self.assertEqual(seo.site_url(), "http://127.0.0.1:18080")
            self.assertFalse(seo.is_production_host())

    def test_bad_canonical_origins_remain_noindex(self):
        for origin in ("https://127.0.0.1", "https://localhost", "https://user:pass@seo.example", "https://seo.example/path", "https://seo.example?x=1"):
            with patch.dict(os.environ, {"ILMIZ_SITE_URL": origin, "ILMIZ_ALLOW_INDEXING": "1"}):
                self.assertFalse(seo.is_production_host())

    def test_jsonld_cannot_break_out_of_script(self):
        hostile = '</script><script>alert("x")</script> & title'
        meta = seo.PageMeta(title=hostile, description=hostile, path="/", jsonld=[{"@type": "Thing", "name": hostile}])
        head = seo.render_head(meta)
        self.assertNotIn('</script><script>', head)
        payload = re.search(r'<script type="application/ld\+json">(.*?)</script>', head).group(1)
        self.assertEqual(json.loads(payload)["name"], hostile)

    def test_external_pdf_is_linked_but_not_mislabelled_as_hosted(self):
        body = self.client.get("/maqola/1-paper-0").text
        self.assertIn('href="https://publisher.example/paper.pdf"', body)
        self.assertNotIn('name="citation_pdf_url"', body)

    def test_complete_abstract_is_available_without_javascript(self):
        body = self.client.get("/maqola/1-paper-0").text
        self.assertIn("Full author-written abstract. " * 99, body)

    def test_date_validation_does_not_invent_dates(self):
        self.assertEqual(seo.publication_date("2025-02-31", 2025), "2025")
        self.assertEqual(seo.publication_date("n/a", None), "")
        self.assertEqual(seo.publication_date("2024/02/29", 2024), "2024-02-29")

    def test_sitemap_index_does_not_invent_daily_modifications(self):
        self.assertNotIn("<lastmod>", self.client.get("/sitemap.xml").text)

    def test_trailing_slash_redirects(self):
        response = self.client.get("/maqolalar/?sahifa=2", follow_redirects=False)
        self.assertEqual(response.status_code, 301)
        self.assertEqual(response.headers["location"], "/maqolalar?sahifa=2")

    def test_scheme_relative_path_is_not_an_open_redirect(self):
        """`//evil.example/` → `Location: //evil.example` bo'lib chiqardi."""
        # httpx nisbiy `//host` ni asosiy URL bilan almashtirib yuboradi,
        # shuning uchun yo'l to'liq manzil ichida beriladi.
        for path in ("//evil.example/", "//evil.example", "///evil.example/x/"):
            response = self.client.get("http://testserver" + path, follow_redirects=False)
            self.assertEqual(response.status_code, 404, path)
            self.assertNotIn("location", response.headers, path)

    def test_index_html_is_not_a_duplicate_empty_spa(self):
        response = self.client.get("/index.html", follow_redirects=False)
        self.assertEqual(response.status_code, 301)
        self.assertEqual(response.headers["location"], "/")

    def test_recent_feed_excludes_old_harvests(self):
        self.db.get(Article, 1).harvested_at = datetime.utcnow() - timedelta(days=30)
        self.db.commit()
        html = ''.join(self.client.get(f"/yangi-maqolalar?sahifa={page}").text for page in (1, 2, 3))
        self.assertNotIn('class="seo-item-title" href="/maqola/1-paper-0"', html)
        self.assertIn('class="seo-item-title" href="/maqola/2-paper-1"', html)

    def test_public_data_is_crawlable_for_rendering_but_admin_is_blocked(self):
        body = self.client.get("/robots.txt").text
        self.assertNotIn("Disallow: /api/\n", body)
        self.assertIn("Disallow: /api/admin/", body)
        self.assertNotIn("Disallow: /qidiruv", body)

    def test_malformed_and_credential_urls_are_not_emitted(self):
        for value in ("http://", "https://user:secret@example.com/a", "https://a.test/has space"):
            self.assertIsNone(seo.web_url(value))


if __name__ == "__main__":
    unittest.main()
