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
from backend.app.models import Journal, JournalContact, JournalLink, JournalProfile
from backend.app.seo_routes import router
from backend.app.services import journal_edit, seo
from backend.app.services.journal_edit import ValidationError, apply_edits, foreign_scraped, manually_edited


class JournalBlocksTest(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {"ILMIZ_SITE_URL": "https://seo.example", "ILMIZ_NOINDEX": ""})
        self.env.start()
        self.engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.journal = Journal(
            slug="tarix", name="Tarix jurnali", short_name="T", publisher="Universitet", city="Toshkent",
            fields=["Tarix"], website="https://tarix.uz",
        )
        self.db.add(self.journal)
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

    def test_editorial_blocks_render_with_json_ld(self):
        about = "Jurnal tarix fanining dolzarb masalalariga bag‘ishlangan. " * 66
        applied, warnings = apply_edits(self.db, self.journal, {
            "about": about,
            "chief_editor": "Prof. A. Karimov",
            "submission_info": "Maqola elektron tizim orqali yuboriladi.\nHajmi 10–15 bet.",
            "deadlines": "Har chorak oxirigacha",
            "fees": "Bepul",
            "indexing": ["Google Scholar", "RINC (eLibrary)"],
            "publication_frequency": "Yiliga 4 marta",
        })
        self.assertIn("about", applied)
        self.assertEqual(warnings, [])  # 396 so‘z — tavsiya etilgan oraliqda
        self.assertIn("about", manually_edited(self.db, self.journal.id))
        page = self.client.get("/jurnal/tarix").text
        for text in ("<h2>Jurnal haqida</h2>", "Maqola topshirish tartibi", "Muddatlar va to‘lov",
                     "Prof. A. Karimov", "Google Scholar, RINC (eLibrary)", "pullikmi?"):
            self.assertIn(text, page)
        self.assertEqual(page.count("<p>Maqola elektron tizim orqali yuboriladi.</p>"), 1)
        graph = [json.loads(block) for block in re.findall(r'<script type="application/ld\+json">(.*?)</script>', page, re.S)]
        periodical = next(item for item in graph if item.get("@type") == "Periodical")
        self.assertEqual(periodical["editor"][0]["name"], "Prof. A. Karimov")
        self.assertEqual(periodical["publicationFrequency"], "Yiliga 4 marta")
        self.assertTrue(periodical["description"].startswith("Jurnal tarix fanining"))

    def test_about_word_count_warning_and_indexing_choices(self):
        _, warnings = apply_edits(self.db, self.journal, {"about": "Qisqa tavsif."})
        self.assertTrue(any("so‘z" in item for item in warnings))
        with self.assertRaises(ValidationError):
            apply_edits(self.db, self.journal, {"indexing": ["Astrology Index"]})

    def test_foreign_scraped_data_detected_and_purged(self):
        self.db.add_all([
            JournalLink(journal_id=self.journal.id, kind="submission", url="https://begona.uz/submit", source_url="https://begona.uz/about"),
            JournalLink(journal_id=self.journal.id, kind="archive", url="https://tarix.uz/archive", source_url="https://journal.tarix.uz/"),
            JournalContact(journal_id=self.journal.id, kind="email", value="x@begona.uz", source_url="https://begona.uz/contact"),
            JournalContact(journal_id=self.journal.id, kind="email", value="ed@tarix.uz", source_url=journal_edit.MANUAL_SOURCE),
            JournalContact(journal_id=self.journal.id, kind="phone", value="+998 71 200 00 00", source_url="https://tadqiq.uz/j/1"),
        ])
        self.db.commit()
        found = foreign_scraped(self.db, self.journal)
        self.assertEqual(found["total"], 2)
        self.assertEqual(found["hosts"], ["begona.uz"])
        foreign_scraped(self.db, self.journal, purge=True)
        self.assertEqual(foreign_scraped(self.db, self.journal)["total"], 0)
        self.db.refresh(self.journal)
        self.assertEqual(sorted(item.value for item in self.journal.contacts), ["+998 71 200 00 00", "ed@tarix.uz"])

    def test_manual_website_survives_tadqiq_import(self):
        """«Sayt ishlamayapti» rejimi ham admin kiritgan manzilni almashtirmasin."""
        from datetime import datetime, timezone

        from backend.app.services.tadqiq_import import MatchResult, TadqiqJournal, apply_match

        apply_edits(self.db, self.journal, {"website": "https://togri.uz"})
        record = TadqiqJournal(slug="t", name="Tarix jurnali", website="https://begona.uz")
        match = MatchResult(record=record, journal_id=self.journal.id, journal_name=self.journal.name, method="issn", score=1.0)
        applied = apply_match(self.db, match, now=datetime.now(timezone.utc), replace_dead_site=True)
        self.db.refresh(self.journal)
        self.assertEqual(self.journal.website, "https://togri.uz")
        self.assertNotIn("website (almashtirildi)", applied)

    def test_missing_about_csv(self):
        self.db.add(Journal(slug="b", name="B jurnal", short_name="B", publisher="P", city="Toshkent"))
        self.db.add(JournalProfile(journal_id=self.journal.id, about="Yozilgan tavsif"))
        self.db.commit()
        csv_text = journal_edit.missing_about_csv(self.db)
        self.assertIn("B jurnal", csv_text)
        self.assertNotIn("Tarix jurnali", csv_text)


if __name__ == "__main__":
    unittest.main()
