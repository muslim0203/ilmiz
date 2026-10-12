import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.app.db import Base, get_db
from backend.app.models import Article, Journal
from backend.app.seo_routes import router
from backend.app.services import seo
from backend.app.services.citations import gost_citation
from backend.app.services.language_detect import detect_language, effective_language


class DetectTest(unittest.TestCase):
    def test_titles_mislabelled_in_production(self):
        """Prod'dagi haqiqiy noto'g'ri belgilangan sarlavhalar."""
        cases = {
            "Green energy transition in central asia: capacity growth": "en",
            "Buxoro viloyatida elektron xizmatlarni rivojlantirishning hududiy": "uz",
            "QORAQALPOQ XALQ PEDAGOGIKASIDA AXLOQIY TARBIYA MAZMUNI VA TAMOYILLARI": "uz",
            "РАЗЛИЧИЯ ОБХВАТОВ ПРАВЫХ И ЛЕВЫХ КОНЕЧНОСТЕЙ У УЧАЩИХСЯ": "ru",
            "Дуккакли дон экинлари орасида учрайдиган бегона ўтлар": "uz",
            "Molecular mechanisms of cardiovascular disease in particular cases": "en",
        }
        for title, expected in cases.items():
            with self.subTest(title=title):
                self.assertEqual(detect_language(title), expected)

    def test_uncertain_text_falls_back_to_metadata(self):
        self.assertIsNone(detect_language("Deep learning"))
        self.assertEqual(effective_language("Deep learning", None, "ru"), "ru")
        self.assertEqual(effective_language("Green energy transition in central asia", None, "uz"), "en")
        self.assertEqual(effective_language("Raqamli iqtisodiyot sharoitida kichik biznes", None, "uz-Latn"), "uz-Latn")

    def test_karakalpak_metadata_is_kept(self):
        title = "MEKTEPKE ShEKEMGI JASTAǴÍ BALALARDÍŃ MUZÍKALÍQ-PSIXOLOGIYALÍQ RAWAJLANÍW"
        self.assertEqual(effective_language(title, None, "kaa"), "kaa")

    def test_gost_page_marker_follows_detected_language(self):
        article = SimpleNamespace(
            title="Maktabgacha ta’limda o‘yin texnologiyalaridan foydalanish", abstract=None, language="en",
            authors=["Karimova D."], journal=SimpleNamespace(name="Pedagogika"), publication_year=2025,
            volume=None, issue=None, pages="12-18", doi=None,
        )
        self.assertIn("– B. 12-18.", gost_citation(article))


class PageLanguageTest(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {"ILMIZ_SITE_URL": "https://seo.example", "ILMIZ_NOINDEX": ""})
        self.env.start()
        self.engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        journal = Journal(slug="j", name="J", short_name="J", publisher="P", city="Toshkent")
        self.db.add(journal)
        self.db.flush()
        self.article = Article(journal_id=journal.id, title="The role of communication in business relationships",
                               normalized_title="x", language="O‘zbek", authors=["A"], publication_year=2025)
        self.db.add(self.article)
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
        self.env.stop()

    def test_english_article_with_uzbek_metadata_gets_lang_en(self):
        page = self.client.get(f"/maqola/{self.article.id}", follow_redirects=True).text
        self.assertIn('<html lang="en">', page)
        self.assertIn('content="en_US"', page)
        self.assertIn("<tr><th>Til</th><td>Ingliz</td></tr>", page)


if __name__ == "__main__":
    unittest.main()
