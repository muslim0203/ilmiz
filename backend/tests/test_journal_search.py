"""Jurnal qidiruvi ikkala yozuvda ham ishlashi kerak (kirill <-> lotin)."""
import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.app.db import Base
from backend.app.models import Journal
from backend.app.services import journal_search


class JournalSearchTest(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        rows = [
            ("vodiynoma", "Водийнома", "В", "Наманган давлат университети", "2181-0001"),
            ("ozbekiston-tarixi", "Oʻzbekiston tarixi", "OT", "OʻzMU", "2181-0002"),
            ("fardu", "FarDU ilmiy xabarlari", "FarDU", "Farg‘ona davlat universiteti", "2181-0003"),
            ("tatu", "ТАТУ хабарлари", "ТАТУ", "Toshkent axborot texnologiyalari universiteti", "2181-0004"),
        ]
        for slug, name, short_name, publisher, issn in rows:
            self.db.add(Journal(slug=slug, name=name, short_name=short_name, publisher=publisher,
                                city="Тошкент", fields=["Filologiya"], issn=issn))
        self.db.commit()

    def tearDown(self) -> None:
        self.db.close()
        self.engine.dispose()

    def slugs(self, query: str) -> set[str]:
        ids = journal_search.matching_ids(self.db, query)
        if ids is None:
            return set()
        return {self.db.get(Journal, item).slug for item in ids}

    def test_latin_query_finds_cyrillic_name(self) -> None:
        self.assertEqual(self.slugs("Vodiynoma"), {"vodiynoma"})
        self.assertEqual(self.slugs("tatu xabarlari"), {"tatu"})

    def test_cyrillic_query_finds_latin_name(self) -> None:
        self.assertEqual(self.slugs("ФарДУ"), {"fardu"})
        self.assertEqual(self.slugs("Ўзбекистон тарихи"), {"ozbekiston-tarixi"})

    def test_apostrophes_do_not_block_the_match(self) -> None:
        """Lotin yozuvida "oʻ"/"gʻ" har xil apostrof bilan yoziladi."""
        self.assertEqual(self.slugs("ozbekiston"), {"ozbekiston-tarixi"})
        self.assertEqual(self.slugs("o'zbekiston tarixi"), {"ozbekiston-tarixi"})
        self.assertEqual(self.slugs("fargona"), {"fardu"})

    def test_every_word_must_match(self) -> None:
        self.assertEqual(self.slugs("fardu ilmiy"), {"fardu"})
        self.assertEqual(self.slugs("fardu tibbiyot"), set())

    def test_publisher_and_issn_are_searchable(self) -> None:
        self.assertEqual(self.slugs("наманган"), {"vodiynoma"})
        self.assertEqual(self.slugs("namangan"), {"vodiynoma"})
        self.assertEqual(self.slugs("2181-0004"), {"tatu"})

    def test_short_query_keeps_the_old_behaviour(self) -> None:
        """Bir harfli so'rov filtrsiz qoladi — chaqiruvchi hammasini ko'rsatadi."""
        self.assertIsNone(journal_search.matching_ids(self.db, "a"))
        self.assertIsNone(journal_search.matching_ids(self.db, "   "))


if __name__ == "__main__":
    unittest.main()
