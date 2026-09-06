"""Jurnal sahifasining SEO mazmuni: to'liq nom, boy profil, OAK reestri, til.

tadqiq.uz jurnal nomi bo'yicha so'rovda oldinda edi: ularning sahifasida
~500 so'z (nashriyot, qaror, ixtisoslik, aloqa, FAQ, o'xshash jurnallar),
bizda esa nom + 4 qatorli jadval, sarlavha 46 belgida kesilgan, yuzlab
jurnalda bir xil "OAK reestridan import qilingan" tavsif bo'lgan.
"""
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
from backend.app.models import (
    Article,
    EditorialMember,
    Journal,
    JournalContact,
    JournalPolicy,
    JournalProfile,
    OakImportRun,
    OakRegistryEntry,
)
from backend.app.seo_routes import router
from backend.app.services import seo, translit


def json_ld(html: str) -> list[dict]:
    return [json.loads(block) for block in re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.S)]


class TransliterationTest(unittest.TestCase):
    def test_uzbek_cyrillic_names_get_latin_alias(self) -> None:
        for name, expected in (
            ("Водийнома", "Vodiynoma"),
            ("ТАТУ хабарлари", "TATU xabarlari"),
            ("Ўзбекистон суғурта бозори", "O‘zbekiston sug‘urta bozori"),
            ("Ер ва ер ости", "Yer va yer osti"),
        ):
            self.assertEqual(translit.alternate_names(name), [expected], name)

    def test_russian_and_latin_names_have_no_alias(self) -> None:
        self.assertEqual(translit.alternate_names("Химия природных соединений"), [])
        self.assertEqual(translit.alternate_names("FarDU ilmiy xabarlari"), [])
        self.assertEqual(translit.alternate_names("Вестник науки", ["Rus"]), [])


class JournalTitleTest(unittest.TestCase):
    def test_name_is_never_clipped(self) -> None:
        long_name = "Scientific Journal of Science, Research and Development"
        title = seo.journal_title(long_name, "2181-1253")
        self.assertTrue(title.startswith(long_name))
        self.assertNotIn("…", title)
        self.assertIn("OAK jurnali", title)
        very_long = "Бердақ номидаги Қорақалпоқ давлат университетининг ахборотномаси"
        self.assertEqual(seo.journal_title(very_long, "1234-5678"), very_long)
        short = seo.journal_title("Водийнома", "1234-5678", suffix=" — 2-sahifa")
        self.assertEqual(short, "Водийнома — OAK jurnali, ISSN 1234-5678 — 2-sahifa")


class JournalPageContentTest(unittest.TestCase):
    def setUp(self) -> None:
        self.env = patch.dict(os.environ, {"ILMIZ_SITE_URL": "https://seo.example", "ILMIZ_NOINDEX": ""})
        self.env.start()
        self.engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        journal = Journal(
            slug="vodiynoma", name="Водийнома", short_name="Водийнома", publisher="Наманган давлат университети",
            city="Наманган", fields=["Filologiya"], issn="2181-0001", languages=["O‘zbek", "Rus"],
            description=seo.OAK_PLACEHOLDER, website="https://vodiynoma.uz/",
        )
        other = Journal(slug="boshqa", name="Boshqa filologiya jurnali", short_name="B", publisher="X",
                        city="Тошкент", fields=["Filologiya"], description=seo.OAK_PLACEHOLDER)
        russian = Journal(slug="vestnik", name="Вестник науки и практики", short_name="В", publisher="Y",
                          city="Тошкент", fields=["Texnika"], description=seo.OAK_PLACEHOLDER)
        self.db.add_all([journal, other, russian])
        self.db.flush()
        run = OakImportRun(source_url="https://oak.test")
        self.db.add(run)
        self.db.flush()
        self.db.add_all([
            JournalProfile(journal_id=journal.id, summary="Filologiya va tilshunoslik bo‘yicha ilmiy jurnal.",
                           aims_scope="Jurnal o‘zbek tilshunosligi va adabiyotshunosligi bo‘yicha maqolalar chop etadi.",
                           peer_review="Ikki tomonlama yopiq taqriz.", publication_frequency="Yiliga 4 marta",
                           address="Namangan sh., Uychi ko‘chasi 316", completeness_score=80),
            JournalContact(journal_id=journal.id, kind="email", value="editor@vodiynoma.uz", source_url="https://vodiynoma.uz/"),
            EditorialMember(journal_id=journal.id, name="Alisher Karimov", role="Bosh muharrir", source_url="https://vodiynoma.uz/"),
            JournalPolicy(journal_id=journal.id, policy_type="peer_review", title="Taqriz siyosati",
                          url="https://vodiynoma.uz/about/peer", source_url="https://vodiynoma.uz/"),
            OakRegistryEntry(import_run_id=run.id, journal_id=journal.id, source_key="k1", name="Водийнома",
                             specialty_code="10.00.00", area="Филология фанлари", kind="Миллий", status="Қўшилди",
                             added="25 август 2025", year="2025", decision="374/5", link="https://vodiynoma.uz/",
                             raw_payload={}),
            Article(journal_id=journal.id, title="Maqola", normalized_title="maqola", authors=["A"],
                    publication_year=2025, publication_date="2025-01-01"),
        ])
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

    def test_rich_profile_is_server_rendered(self) -> None:
        html = self.client.get("/jurnal/vodiynoma").text
        self.assertIn("<title>Водийнома — OAK jurnali, ISSN 2181-0001</title>", html)
        for expected in (
            "Boshqa yozuvda", "Vodiynoma",                # lotin varianti
            "Maqsad va yo‘nasish".replace("nasish", "nalish"), "tilshunosligi",
            "Taqriz tartibi", "Tahririyat", "Alisher Karimov", "Bosh muharrir",
            "OAK reestri yozuvlari", "10.00.00", "№374/5", "25 август 2025",
            "Nashr siyosati", "Taqriz siyosati",
            "Aloqa", "editor@vodiynoma.uz", "Uychi",
            "Ko‘p so‘raladigan savollar", "OAK ro‘yxatida bormi",
            "Shu sohadagi boshqa OAK jurnallari", "Boshqa filologiya jurnali",
        ):
            self.assertIn(expected, html, expected)
        self.assertNotIn(seo.OAK_PLACEHOLDER, html)
        # Rasmiy sayt nofollow emas.
        self.assertRegex(html, r'<a href="https://vodiynoma.uz/" rel="noopener"')

    def test_jsonld_periodical_is_enriched(self) -> None:
        html = self.client.get("/jurnal/vodiynoma").text
        periodical = next(item for item in json_ld(html) if item["@type"] == "Periodical")
        self.assertEqual(periodical["alternateName"], ["Vodiynoma"])
        self.assertIn("https://portal.issn.org/resource/ISSN/2181-0001", periodical["sameAs"])
        self.assertEqual(periodical["editor"][0]["name"], "Alisher Karimov")
        self.assertEqual(periodical["contactPoint"]["email"], "editor@vodiynoma.uz")
        self.assertEqual(periodical["publisher"]["url"], "https://vodiynoma.uz/")
        self.assertEqual(periodical["identifier"][0]["value"], "2181-0001")

    def test_placeholder_description_is_replaced_by_facts(self) -> None:
        html = self.client.get("/jurnal/boshqa").text
        description = re.search(r'<meta name="description" content="([^"]*)"', html).group(1)
        self.assertNotIn("reestridan import", description)
        self.assertIn("Boshqa filologiya jurnali", description)
        self.assertIn("OAK ro‘yxatidagi", description)

    def test_language_follows_the_journal(self) -> None:
        uzbek = self.client.get("/jurnal/vodiynoma").text
        self.assertIn('<html lang="uz">', uzbek)
        self.assertIn('hreflang="uz"', uzbek)
        russian = self.client.get("/jurnal/vestnik").text
        self.assertIn('<html lang="ru">', russian)
        self.assertIn('og:locale" content="ru_RU"', russian)

    def test_paginated_title_keeps_page_suffix(self) -> None:
        with self.db.begin_nested():
            journal = self.db.scalar(self.db.query(Journal).filter_by(slug="vodiynoma").statement)
            self.db.add_all([
                Article(journal_id=journal.id, title=f"M{i}", normalized_title=f"m{i}", authors=["A"], publication_year=2025)
                for i in range(seo.ARTICLES_PER_PAGE + 2)
            ])
        self.db.commit()
        seo.reset_cache()
        html = self.client.get("/jurnal/vodiynoma?sahifa=2").text
        self.assertIn("<title>Водийнома — OAK jurnali, ISSN 2181-0001 — 2-sahifa</title>", html)

    def test_sitemap_year_lastmod_comes_from_articles(self) -> None:
        xml = self.client.get("/sitemap-journals.xml").text
        entry = re.search(r"<url><loc>https://seo.example/jurnal/vodiynoma/2025</loc><lastmod>([^<]+)</lastmod>", xml)
        self.assertIsNotNone(entry)


if __name__ == "__main__":
    unittest.main()
