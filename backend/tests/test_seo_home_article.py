"""Bosh sahifa va maqola sahifasining SEO mazmuni (jurnal sahifasi darajasida)."""
import json
import os
import re
import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.app.db import Base, get_db
from backend.app.models import Article, Journal, OakImportRun, OakRegistryEntry
from backend.app.seo_routes import router
from backend.app.services import seo
from backend.app.services.citations import citation_formats


def json_ld(html: str) -> list[dict]:
    return [json.loads(block) for block in re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.S)]


class HomeAndArticleSeoTest(unittest.TestCase):
    def setUp(self) -> None:
        self.env = patch.dict(os.environ, {"ILMIZ_SITE_URL": "https://seo.example", "ILMIZ_NOINDEX": ""})
        self.env.start()
        self.engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        journal = Journal(slug="fan-sportga", name="Фан спортга", short_name="ФС", publisher="O‘zDJTSU",
                          city="Тошкент", fields=["Pedagogika"], issn="2181-0001", website="https://fansportga.uz/")
        other = Journal(slug="pedagogika-jurnali", name="Pedagogika jurnali", short_name="P", publisher="X",
                        city="Самарқанд", fields=["Pedagogika"])
        self.db.add_all([journal, other])
        self.db.flush()
        run = OakImportRun(source_url="https://oak.test")
        self.db.add(run)
        self.db.flush()
        self.db.add(OakRegistryEntry(import_run_id=run.id, journal_id=other.id, source_key="r1", name=other.name,
                                     kind="Миллий", status="Қўшилди", year="2026", added="1 сентябрь 2026",
                                     decision="380/1", raw_payload={}))
        articles = [
            Article(journal_id=journal.id, title=f"Basketbol {index}", normalized_title=f"basketbol {index}",
                    authors=["Shaxnoza Nurmatova"], publication_year=2026, publication_date="2026-03-26",
                    volume="9", issue="3", pages=f"{index}-{index + 2}", language="O‘zbek",
                    doi=f"10.65149/fs.2026.{index}", keywords=["basketbol", "yuklama"],
                    abstract="Annotatsiya matni. " * 20 if index != 3 else None, fields=["Pedagogika"])
            for index in range(1, 8)
        ]
        articles.append(Article(journal_id=other.id, title="Pedagogik tajriba", normalized_title="pedagogik tajriba",
                                authors=["B. Karimov"], publication_year=2025, fields=["Pedagogika"]))
        self.db.add_all(articles)
        self.db.commit()
        seo.reset_cache()
        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_db] = lambda: self.db
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self.client.close()
        self.db.close()
        self.engine.dispose()
        seo.reset_cache()
        self.env.stop()

    # --- bosh sahifa ------------------------------------------------------------

    def test_home_has_explanatory_sections_and_faq(self) -> None:
        html = self.client.get("/").text
        for expected in (
            "Indeks holati", "IlmIz qanday ishlaydi", "Ko‘p so‘raladigan savollar",
            "OAK jurnallari ro‘yxati nima?", "OAK ro‘yxatiga 2026-yilda qo‘shilgan jurnallar",
            "Pedagogika jurnali", "Shaharlar bo‘yicha", "Pedagogika (2)",
        ):
            self.assertIn(expected, html, expected)
        types_ = {item["@type"] for item in json_ld(html)}
        self.assertIn("FAQPage", types_)
        page = next(item for item in json_ld(html) if item["@type"] == "CollectionPage")
        self.assertEqual(page["mainEntity"]["@type"], "ItemList")

    # --- maqola sahifasi ---------------------------------------------------------

    def test_article_title_and_language(self) -> None:
        html = self.client.get("/maqola/1-basketbol-1").text
        self.assertIn("<title>Basketbol 1 — Фан спортга, 2026</title>", html)
        self.assertNotIn("— IlmIz</title>", html)
        self.assertIn('<html lang="uz">', html)
        self.assertIn('href="/jurnal/fan-sportga/2026"', html)  # breadcrumb yil

    def test_article_has_citations_and_neighbours(self) -> None:
        html = self.client.get("/maqola/4-basketbol-4").text
        self.assertIn("Iqtibos keltirish", html)
        self.assertIn("GOST (OAK)", html)
        self.assertIn("@article{", html)
        # Ikki tomonlama qo'shnilar: 1,2,3 va 5,6,7.
        for neighbour in ("Basketbol 2", "Basketbol 3", "Basketbol 5", "Basketbol 6"):
            self.assertIn(neighbour, html, neighbour)
        self.assertIn("Pedagogika sohasidagi boshqa maqolalar", html)
        self.assertIn("Pedagogik tajriba", html)
        scholarly = next(item for item in json_ld(html) if item["@type"] == "ScholarlyArticle")
        self.assertEqual(scholarly["keywords"], ["basketbol", "yuklama"])
        self.assertEqual(scholarly["mainEntityOfPage"], "https://seo.example/maqola/4-basketbol-4")
        self.assertEqual(scholarly["publisher"]["url"], "https://fansportga.uz/")

    def test_article_without_abstract_gets_a_factual_description(self) -> None:
        html = self.client.get("/maqola/3-basketbol-3").text
        description = re.search(r'<meta name="description" content="([^"]*)"', html).group(1)
        self.assertIn("Shaxnoza Nurmatova", description)
        self.assertIn("Фан спортга (2026)", description)
        self.assertIn("jild 9", description)

    def test_gost_citation_format(self) -> None:
        article = self.db.get(Article, 1)
        gost = citation_formats(article)["gost"]
        self.assertEqual(gost, "Shaxnoza Nurmatova Basketbol 1 // Фан спортга. – 2026. – T. 9, № 3. – B. 1-3. – DOI: 10.65149/fs.2026.1.")


if __name__ == "__main__":
    unittest.main()
