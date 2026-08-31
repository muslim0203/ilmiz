import json
import os
import re
import tempfile
import unittest
from unittest.mock import patch

database_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
database_file.close()
os.environ["DATABASE_URL"] = f"sqlite:///{database_file.name}"
os.environ["ILMIZ_SITE_URL"] = "https://ilmiz.test"

from fastapi.testclient import TestClient  # noqa: E402

from backend.app.db import engine  # noqa: E402
from backend.app.main import app  # noqa: E402
from backend.app.services import seo  # noqa: E402


def json_ld(html: str) -> list[dict]:
    return [
        json.loads(block)
        for block in re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.S)
    ]


def types(html: str) -> set[str]:
    return {item["@type"] for item in json_ld(html)}


def head_value(html: str, name: str) -> str | None:
    match = re.search(rf'<meta name="{name}" content="([^"]*)"', html)
    return match.group(1) if match else None


class SlugTest(unittest.TestCase):
    def test_cyrillic_and_apostrophes(self) -> None:
        """Slug mijozdagi `lib/slug.ts` bilan bir xil natija berishi shart."""
        for value, expected in (
            ("O‘zbekiston ilmiy xabarlari", "ozbekiston-ilmiy-xabarlari"),
            ("Тошкент давлат университети", "toshkent-davlat-universiteti"),
            ("FarDU ilmiy xabarlari", "fardu-ilmiy-xabarlari"),
            ("Qishloq xo‘jaligi", "qishloq-xojaligi"),
            ("!!!", ""),
        ):
            with self.subTest(value=value):
                self.assertEqual(seo.slugify(value), expected)

    def test_slug_is_not_cut_mid_word(self) -> None:
        slug = seo.slugify("bir ikki uch tort besh olti yetti sakkiz toqqiz on", limit=20)
        self.assertLessEqual(len(slug), 20)
        self.assertFalse(slug.endswith("-"))

    def test_web_url_rejects_non_browser_schemes(self) -> None:
        """`demo://pdf` `citation_pdf_url` ga tushsa, Scholar yozuvni rad etadi."""
        self.assertIsNone(seo.web_url("demo://pdf"))
        self.assertIsNone(seo.web_url(""))
        self.assertIsNone(seo.web_url("urn:isbn:123"))
        self.assertEqual(seo.web_url("https://a.uz/x.pdf"), "https://a.uz/x.pdf")


class SeoRoutesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client_context = TestClient(app)
        cls.client = cls.client_context.__enter__()
        cls.journal_slug = cls.client.get("/api/journals").json()[0]["id"]
        cls.article = cls.client.get("/api/articles").json()[0]

    @classmethod
    def tearDownClass(cls) -> None:
        cls.client_context.__exit__(None, None, None)
        engine.dispose()
        os.unlink(database_file.name)

    def test_every_page_is_server_rendered(self) -> None:
        """Robotga bo‘sh `#root` ketmasligi kerak — SPA'ning butun muammosi shu edi."""
        for path in ("/", "/jurnallar", "/maqolalar", "/sohalar", "/shaharlar", "/loyiha"):
            with self.subTest(path=path):
                html = self.client.get(path).text
                body = html[html.find('<div id="root">') : html.rfind("</div>")]
                self.assertIn("<h1>", body)
                self.assertIn('href="/', body)
                self.assertRegex(html, r"<title>.+</title>")

    def test_canonical_and_hreflang(self) -> None:
        response = self.client.get("/jurnallar?sahifa=2")
        self.assertIn('<link rel="canonical" href="https://ilmiz.test/jurnallar?sahifa=2">', response.text)
        self.assertIn('hreflang="uz"', response.text)
        self.assertIn('hreflang="x-default"', response.text)

    def test_only_one_title_and_description(self) -> None:
        """Qobiqdagi statik meta'lar server qo‘yganlari bilan ikkilanmasin."""
        html = self.client.get("/").text
        self.assertEqual(html.count("<title>"), 1)
        self.assertEqual(len(re.findall(r'<meta name="description"', html)), 1)

    def test_home_declares_site_search(self) -> None:
        html = self.client.get("/").text
        self.assertIn("WebSite", types(html))
        website = next(item for item in json_ld(html) if item["@type"] == "WebSite")
        self.assertEqual(
            website["potentialAction"]["target"]["urlTemplate"],
            "https://ilmiz.test/qidiruv?q={search_term_string}",
        )

    def test_journal_page_is_a_periodical(self) -> None:
        html = self.client.get(f"/jurnal/{self.journal_slug}").text
        self.assertEqual({"Periodical", "BreadcrumbList", "ItemList"} & types(html),
                         {"Periodical", "BreadcrumbList", "ItemList"})
        self.assertIsNotNone(head_value(html, "citation_journal_title"))

    def test_article_page_carries_scholar_metadata(self) -> None:
        path = seo.article_path(self.article["id"], self.article["title"])
        html = self.client.get(path).text
        self.assertIn("ScholarlyArticle", types(html))
        self.assertEqual(head_value(html, "citation_title"), self.article["title"])
        self.assertGreaterEqual(len(re.findall(r'<meta name="citation_author"', html)),
                                len(self.article["authors"]))
        self.assertIsNotNone(head_value(html, "DC.title"))

    def test_article_slug_change_redirects_to_canonical(self) -> None:
        """Sarlavha o‘zgarsa eski havola ishlashi, lekin indeksda bitta URL qolishi kerak."""
        response = self.client.get(f"/maqola/{self.article['id']}-eski-sarlavha", follow_redirects=False)
        self.assertEqual(response.status_code, 301)
        self.assertEqual(
            response.headers["location"],
            seo.article_path(self.article["id"], self.article["title"]),
        )

    def test_search_and_missing_pages_are_not_indexed(self) -> None:
        for path, status in (("/qidiruv?q=test", 200), ("/bunday-sahifa-yoq", 404)):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, status)
                self.assertIn("noindex", head_value(response.text, "robots"))

    def test_api_routes_survive_the_catch_all(self) -> None:
        """SEO routerida `/{path:path}` bor — u `/api/*` ni yutib yubormasin."""
        for path in ("/api/health", "/api/stats", "/api/journals", "/api/facets"):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                self.assertIn("application/json", response.headers["content-type"])

    @patch.dict(os.environ, {"ILMIZ_NOINDEX": "", "ILMIZ_SITE_URL": "https://ilmiz.test"})
    def test_robots_points_at_the_sitemap(self) -> None:
        body = self.client.get("/robots.txt").text
        self.assertIn("Sitemap: https://ilmiz.test/sitemap.xml", body)
        self.assertIn("Host: ilmiz.test", body)
        self.assertIn("Clean-param:", body)
        self.assertIn("Disallow: /api/admin/", body)
        self.assertNotIn("Disallow: /api/\n", body)

    def test_sitemap_index_lists_reachable_children(self) -> None:
        index = self.client.get("/sitemap.xml").text
        children = re.findall(r"<loc>https://ilmiz\.test(/[^<]+)</loc>", index)
        self.assertIn("/sitemap-pages.xml", children)
        self.assertIn("/sitemap-journals.xml", children)
        for path in children:
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                self.assertIn("<urlset", response.text)

    def test_sitemap_urls_are_absolute_and_resolvable(self) -> None:
        xml = self.client.get("/sitemap-journals.xml").text
        locations = re.findall(r"<loc>([^<]+)</loc>", xml)
        self.assertTrue(locations)
        for location in locations[:5]:
            with self.subTest(location=location):
                self.assertTrue(location.startswith("https://ilmiz.test/"))
                path = location[len("https://ilmiz.test") :]
                self.assertEqual(self.client.get(path).status_code, 200)

    def test_staging_host_is_never_indexable(self) -> None:
        """Prod domeni sozlanmagan nusxa indeksga tushsa, dublikat bo‘lardi."""
        os.environ.pop("ILMIZ_SITE_URL")
        try:
            self.assertIn("noindex", head_value(self.client.get("/").text, "robots"))
            self.assertIn("Disallow: /", self.client.get("/robots.txt").text)
        finally:
            os.environ["ILMIZ_SITE_URL"] = "https://ilmiz.test"


if __name__ == "__main__":
    unittest.main()
