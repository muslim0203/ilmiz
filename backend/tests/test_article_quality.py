import os
import re
import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.app.db import Base, get_db
from backend.app.models import Article, HarvestSource, Journal, SourceRecord, User, UserArticle
from backend.app.seo_routes import router
from backend.app.services import article_quality, seo
from backend.app.services.article_dedupe import dedupe_articles

GOOD_ABSTRACT = "Mazmunli annotatsiya matni. " * 20  # > 400 belgi


def make_article(journal_id: int, index: int, **overrides) -> Article:
    values = dict(
        journal_id=journal_id,
        title=f"Ilmiy maqola sarlavhasi raqam {index}",
        normalized_title=f"ilmiy maqola sarlavhasi raqam {index}",
        authors=["Muallif, Birinchi"],
        abstract=GOOD_ABSTRACT,
        keywords=["kalit"],
        publication_year=2025,
        publication_date="2025-03-01",
    )
    values.update(overrides)
    return Article(**values)


class QualityTest(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {"ILMIZ_SITE_URL": "https://seo.example", "ILMIZ_NOINDEX": ""})
        self.env.start()
        self.engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.journal = Journal(slug="j", name="Jurnal", short_name="J", publisher="P", city="Toshkent", fields=["Tarix"])
        self.db.add(self.journal)
        self.db.flush()
        self.articles = {
            "good": make_article(self.journal.id, 1),
            "short": make_article(self.journal.id, 2, abstract="Qisqa."),
            "no_authors": make_article(self.journal.id, 3, authors=[]),
            "no_year": make_article(self.journal.id, 4, publication_year=None),
            "no_kw_no_doi": make_article(self.journal.id, 5, keywords=[]),
            "doi_only": make_article(self.journal.id, 6, keywords=[], doi="10.1/x"),
            "html": make_article(self.journal.id, 7, abstract=GOOD_ABSTRACT + "<em>qolgan teg</em>"),
        }
        self.db.add_all(self.articles.values())
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

    def test_issues(self):
        self.assertEqual(article_quality.issues(self.articles["good"]), [])
        self.assertEqual(article_quality.issues(self.articles["doi_only"]), [])
        self.assertIn("annotatsiya_qisqa", article_quality.issues(self.articles["short"]))
        self.assertIn("muallifsiz", article_quality.issues(self.articles["no_authors"]))
        self.assertIn("yilsiz", article_quality.issues(self.articles["no_year"]))
        self.assertIn("kalit_soz_va_doi_yoq", article_quality.issues(self.articles["no_kw_no_doi"]))
        self.assertIn("annotatsiyada_html", article_quality.issues(self.articles["html"]))

    def test_sql_clause_matches_python_rule(self):
        """Sitemap (SQL) va sahifa robots'i (Python) bir xil qaror qilishi shart (HTML'dan tashqari)."""
        in_sql = set(self.db.scalars(select(Article.id).where(article_quality.indexable_clause())))
        in_python = {a.id for name, a in self.articles.items() if name == "html" or article_quality.is_indexable(a)}
        self.assertEqual(in_sql, in_python)

    def test_page_robots_and_sitemap(self):
        def robots(article):
            page = self.client.get(f"/maqola/{article.id}", follow_redirects=True).text
            return re.search(r'name="robots" content="([^"]+)"', page).group(1)

        self.assertTrue(robots(self.articles["good"]).startswith("index"))
        self.assertTrue(robots(self.articles["short"]).startswith("noindex, follow"))
        sitemap = self.client.get("/sitemap-articles-1.xml").text
        self.assertIn(f"/maqola/{self.articles['good'].id}-", sitemap)
        self.assertNotIn(f"/maqola/{self.articles['short'].id}-", sitemap)

    def test_duplicates_merge_into_canonical_with_redirect(self):
        canonical = make_article(self.journal.id, 50, doi="10.1/canonical")
        duplicate = make_article(self.journal.id, 50, abstract=GOOD_ABSTRACT * 2)
        source = HarvestSource(journal_id=self.journal.id, base_url="https://j.example/oai")
        user = User(provider="google", provider_subject="1", email="m@example.uz", display_name="Muallif")
        self.db.add_all([canonical, duplicate, source, user])
        self.db.flush()
        record = SourceRecord(source_id=source.id, article_id=duplicate.id, oai_identifier="oai:j:1")
        self.db.add_all([record, UserArticle(user_id=user.id, article_id=duplicate.id)])
        self.db.commit()

        dry = dedupe_articles(self.db)
        self.assertEqual((dry["guruh"], dry["takror"]), (1, 1))
        self.db.refresh(duplicate)
        self.assertFalse(duplicate.is_deleted)  # quruq yurish hech narsa yozmaydi

        dedupe_articles(self.db, dry_run=False)
        self.db.refresh(duplicate)
        self.db.refresh(record)
        self.assertTrue(duplicate.is_deleted)
        self.assertEqual(duplicate.duplicate_of, canonical.id)  # DOI'lisi kanonik
        self.assertEqual(record.article_id, canonical.id)
        self.assertEqual(self.db.scalar(select(UserArticle.article_id)), canonical.id)

        response = self.client.get(f"/maqola/{duplicate.id}", follow_redirects=False)
        self.assertEqual(response.status_code, 301)
        self.assertTrue(response.headers["location"].startswith(f"/maqola/{canonical.id}-"))

    def test_same_title_different_articles_are_not_merged(self):
        """Sarlavha bir xil, annotatsiya boshqa — alohida maqolalar."""
        self.db.add_all([
            make_article(self.journal.id, 60, abstract="Birinchi tadqiqot haqida. " * 20),
            make_article(self.journal.id, 60, abstract="Butunlay boshqa mavzu. " * 20),
        ])
        self.db.commit()
        result = dedupe_articles(self.db)
        self.assertEqual((result["guruh"], result["otkazildi_guruh"]), (0, 1))

    def test_two_dois_with_identical_abstract_are_merged(self):
        """Jurnal va Zenodo DOI'si — bitta maqola."""
        self.db.add_all([
            make_article(self.journal.id, 70, doi="10.1/journal"),
            make_article(self.journal.id, 70, doi="10.5281/zenodo.1"),
        ])
        self.db.commit()
        self.assertEqual(dedupe_articles(self.db)["guruh"], 1)

    def test_short_generic_titles_are_not_merged(self):
        self.db.add_all([
            make_article(self.journal.id, 0, title="Kirish", normalized_title="kirish"),
            make_article(self.journal.id, 0, title="Kirish", normalized_title="kirish"),
        ])
        self.db.commit()
        result = dedupe_articles(self.db)
        self.assertEqual((result["guruh"], result["otkazildi_guruh"]), (0, 1))


if __name__ == "__main__":
    unittest.main()
