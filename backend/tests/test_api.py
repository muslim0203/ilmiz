import os
import tempfile
import unittest

database_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
database_file.close()
os.environ["DATABASE_URL"] = f"sqlite:///{database_file.name}"

ADMIN_TOKEN = "test-admin-token"

from fastapi.testclient import TestClient  # noqa: E402

from backend.app.db import engine  # noqa: E402
from backend.app.main import app  # noqa: E402


class ApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client_context = TestClient(app)
        cls.client = cls.client_context.__enter__()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.client_context.__exit__(None, None, None)
        engine.dispose()
        os.unlink(database_file.name)

    def test_health(self) -> None:
        response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")

    def test_catalog_seed(self) -> None:
        response = self.client.get("/api/journals")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()), 6)

    def test_admin_requires_token(self) -> None:
        """`/api/admin/*` ilgari butunlay ochiq edi — tokensiz kirish yopilishi shart."""
        os.environ["ILMIZ_ADMIN_TOKEN"] = ADMIN_TOKEN
        try:
            for method, path in (
                ("get", "/api/admin/dashboard"),
                ("get", "/api/admin/sources"),
                ("get", "/api/admin/audit/jobs"),
                ("post", "/api/admin/audit/queue"),
                ("post", "/api/admin/profiles/queue"),
            ):
                with self.subTest(path=path):
                    kwargs = {"json": {}} if method == "post" else {}
                    response = getattr(self.client, method)(path, **kwargs)
                    self.assertEqual(response.status_code, 401)
        finally:
            os.environ.pop("ILMIZ_ADMIN_TOKEN", None)

    def test_admin_rejects_wrong_token(self) -> None:
        os.environ["ILMIZ_ADMIN_TOKEN"] = ADMIN_TOKEN
        try:
            response = self.client.get("/api/admin/dashboard", headers={"X-Admin-Token": "wrong-token"})
            self.assertEqual(response.status_code, 401)
        finally:
            os.environ.pop("ILMIZ_ADMIN_TOKEN", None)

    def test_admin_accepts_token_in_both_header_forms(self) -> None:
        os.environ["ILMIZ_ADMIN_TOKEN"] = ADMIN_TOKEN
        try:
            for headers in (
                {"X-Admin-Token": ADMIN_TOKEN},
                {"Authorization": f"Bearer {ADMIN_TOKEN}"},
            ):
                with self.subTest(headers=list(headers)):
                    response = self.client.get("/api/admin/dashboard", headers=headers)
                    self.assertEqual(response.status_code, 200)
                    self.assertIn("journals", response.json())
        finally:
            os.environ.pop("ILMIZ_ADMIN_TOKEN", None)

    def test_admin_rejects_malformed_body_before_parsing(self) -> None:
        """Buzuq JSON ham 401 berishi kerak — body auth’dan oldin parse qilinadi."""
        os.environ["ILMIZ_ADMIN_TOKEN"] = ADMIN_TOKEN
        try:
            response = self.client.post(
                "/api/admin/sources/harvest",
                content=b"buzuq",
                headers={"Content-Type": "application/json"},
            )
            self.assertEqual(response.status_code, 401)
        finally:
            os.environ.pop("ILMIZ_ADMIN_TOKEN", None)

    def test_admin_disabled_when_token_not_configured(self) -> None:
        """Token sozlanmagan bo'lsa fail-closed: 503, ochiq qolmasin."""
        os.environ.pop("ILMIZ_ADMIN_TOKEN", None)
        response = self.client.get("/api/admin/dashboard", headers={"X-Admin-Token": "nimadir"})
        self.assertEqual(response.status_code, 503)

    def test_public_endpoints_stay_open(self) -> None:
        os.environ["ILMIZ_ADMIN_TOKEN"] = ADMIN_TOKEN
        try:
            for path in ("/api/health", "/api/stats", "/api/journals", "/api/articles"):
                with self.subTest(path=path):
                    self.assertEqual(self.client.get(path).status_code, 200)
        finally:
            os.environ.pop("ILMIZ_ADMIN_TOKEN", None)

    def test_facets_list_every_field_in_the_data(self) -> None:
        """Frontend ilgari 7 ta sohani qattiq yozib olgan edi; facets hammasini bersin."""
        facets = self.client.get("/api/facets").json()
        journals = self.client.get("/api/journals").json()

        from_journals = {name for journal in journals for name in journal["fields"]}
        from_facets = {
            item["name"]
            for group in facets["fieldGroups"]
            for item in group["fields"]
        }
        self.assertEqual(from_facets, from_journals)
        self.assertEqual(facets["fieldCount"], len(from_journals))

    def test_facets_counts_match_journal_list(self) -> None:
        facets = self.client.get("/api/facets").json()
        journals = self.client.get("/api/journals").json()
        for group in facets["fieldGroups"]:
            for item in group["fields"]:
                expected = sum(1 for journal in journals if item["name"] in journal["fields"])
                with self.subTest(field=item["name"]):
                    self.assertEqual(item["journals"], expected)

    def test_group_counts_are_unions_not_sums(self) -> None:
        """Bir jurnal guruh ichidagi ikki sohaga tegishli bo'lsa, ikki marta sanalmasin."""
        facets = self.client.get("/api/facets").json()
        journals = self.client.get("/api/journals").json()
        for group in facets["fieldGroups"]:
            names = {item["name"] for item in group["fields"]}
            expected = sum(1 for journal in journals if names.intersection(journal["fields"]))
            with self.subTest(group=group["group"]):
                self.assertEqual(group["journals"], expected)

    def test_group_count_matches_filtered_journal_list(self) -> None:
        facets = self.client.get("/api/facets").json()
        for group in facets["fieldGroups"]:
            params = [("field", item["name"]) for item in group["fields"]] + [("limit", 500)]
            filtered = self.client.get("/api/journals", params=params).json()
            with self.subTest(group=group["group"]):
                self.assertEqual(group["journals"], len(filtered))

    def test_journals_filter_by_multiple_fields(self) -> None:
        response = self.client.get("/api/journals", params=[("field", "Tibbiyot"), ("field", "Filologiya")])
        self.assertEqual(response.status_code, 200)
        slugs = {journal["id"] for journal in response.json()}
        self.assertIn("acta-camu", slugs)
        self.assertIn("fardu-ilmiy-xabarlari", slugs)
        for journal in response.json():
            self.assertTrue({"Tibbiyot", "Filologiya"}.intersection(journal["fields"]))

    def test_journal_field_filter_is_not_truncated_by_limit(self) -> None:
        """Ilgari SQL limiti filtrdan oldin ishlardi.

        Natijada `limit=1` + soha filtri "alifboda birinchi jurnal shu sohada
        bo'lsagina" natija berardi, aks holda bo'sh ro'yxat qaytarardi.
        """
        journals = self.client.get("/api/journals").json()
        first = journals[0]
        # Birinchi jurnalda yo'q sohani tanlaymiz — eski kod aynan shunda yiqilardi.
        target = next(
            name
            for journal in journals
            for name in journal["fields"]
            if name not in first["fields"]
        )
        filtered = self.client.get("/api/journals", params=[("field", target), ("limit", 1)]).json()
        self.assertEqual(len(filtered), 1)
        self.assertIn(target, filtered[0]["fields"])

    def test_articles_filter_by_field_on_server(self) -> None:
        articles = self.client.get("/api/articles", params=[("field", "Tibbiyot")]).json()
        self.assertTrue(articles)
        for article in articles:
            self.assertIn("Tibbiyot", article["fields"])

    def test_city_variants_collapse_to_one_canonical_name(self) -> None:
        from backend.app.services.taxonomy import canonical_city, city_variants

        self.assertEqual(canonical_city("Тошкент"), "Toshkent")
        self.assertEqual(canonical_city("Toshkent"), "Toshkent")
        self.assertIn("Тошкент", city_variants("Toshkent"))
        self.assertIn("Toshkent", city_variants("Toshkent"))

    def test_journal_counts_are_aggregated(self) -> None:
        """`articleCount`/`issueCount` aggregate so'rovdan keladi, `journal.articles` dan emas."""
        journals = self.client.get("/api/journals").json()
        by_slug = {item["id"]: item for item in journals}
        stats = self.client.get("/api/stats").json()

        self.assertEqual(sum(item["articleCount"] for item in journals), stats["articles"])
        self.assertEqual(by_slug["fardu-ilmiy-xabarlari"]["articleCount"], 1)
        self.assertEqual(by_slug["fardu-ilmiy-xabarlari"]["issueCount"], 1)
        self.assertEqual(by_slug["acta-camu"]["articleCount"], 1)
        self.assertEqual(by_slug["adabiy-meros"]["articleCount"], 0)
        self.assertEqual(by_slug["adabiy-meros"]["issueCount"], 0)

    def test_journal_detail_counts_match_list(self) -> None:
        listed = {item["id"]: item for item in self.client.get("/api/journals").json()}
        detail = self.client.get("/api/journals/acta-camu").json()
        self.assertEqual(detail["articleCount"], listed["acta-camu"]["articleCount"])
        self.assertEqual(detail["issueCount"], listed["acta-camu"]["issueCount"])

    def test_articles_and_stats(self) -> None:
        articles = self.client.get("/api/articles").json()
        stats = self.client.get("/api/stats").json()
        self.assertEqual(len(articles), 2)
        self.assertEqual(stats["journals"], 6)
        self.assertEqual(stats["articles"], 2)
        self.assertIn("apa", articles[0]["citations"])
        self.assertIn("bibtex", articles[0]["citations"])
        self.assertIn("journalName", articles[0])

    def test_journal_detail_has_profile_and_registry_slots(self) -> None:
        catalog = self.client.get("/api/journals").json()
        response = self.client.get(f"/api/journals/{catalog[0]['id']}")
        self.assertEqual(response.status_code, 200)
        self.assertIn("profile", response.json())
        self.assertIn("oakRecords", response.json())


if __name__ == "__main__":
    unittest.main()
