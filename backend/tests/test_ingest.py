import os
import tempfile
import unittest

database_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
database_file.close()
os.environ["DATABASE_URL"] = f"sqlite:///{database_file.name}"

from harvester.oai_harvester import OAIRecord  # noqa: E402

from backend.app.db import SessionLocal, engine, init_db  # noqa: E402
from backend.app.models import Article, HarvestSource, Journal, SourceRecord  # noqa: E402
from harvester.oai_harvester import OAIError  # noqa: E402
from backend.app.services.ingest import _BatchCache, _bibliographic_parts, _upsert_record  # noqa: E402


def make_record(identifier: str, *, title: str | None = None, doi: str | None = None, deleted: bool = False) -> OAIRecord:
    metadata: dict[str, list[str]] = {}
    if title:
        metadata["title"] = [title]
        metadata["date"] = ["2025-03-01"]
    if doi:
        metadata.setdefault("identifier", []).append(f"https://doi.org/{doi}")
    return OAIRecord(
        identifier=identifier,
        datestamp="2025-03-01T00:00:00Z",
        set_specs=["demo"],
        deleted=deleted,
        metadata=metadata,
        raw_xml=f"<record>{identifier}</record>",
        metadata_hash=None if deleted else f"hash-{identifier}-{title}",
    )


class IngestBatchTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        init_db()

    @classmethod
    def tearDownClass(cls) -> None:
        engine.dispose()
        # WAL rejimida yonma-yon `-wal` va `-shm` fayllar ham qoladi.
        for suffix in ("", "-wal", "-shm"):
            try:
                os.unlink(database_file.name + suffix)
            except OSError:
                pass

    def setUp(self) -> None:
        self.db = SessionLocal()
        journal = Journal(
            slug=f"test-{id(self)}",
            name="Test jurnali",
            short_name="TEST",
            publisher="Test nashriyoti",
            city="Toshkent",
            fields=["Test"],
        )
        self.source = HarvestSource(journal=journal, base_url=f"https://example.test/{id(self)}/oai")
        self.db.add(self.source)
        self.db.commit()

    def tearDown(self) -> None:
        self.db.close()

    def test_duplicate_deleted_identifier_in_one_batch(self) -> None:
        """Bir commit oralig'ida takrorlangan identifier ikkinchi qatorni yaratmasin."""
        cache = _BatchCache()
        record = make_record("oai:test:article/1", deleted=True)
        _upsert_record(self.db, self.source, record, cache)
        _upsert_record(self.db, self.source, record, cache)
        self.db.commit()

        rows = self.db.query(SourceRecord).filter(SourceRecord.source_id == self.source.id).all()
        self.assertEqual(len(rows), 1)

    def test_duplicate_doi_in_one_batch(self) -> None:
        """Bir batchda takrorlangan DOI articles.doi unique constraintini buzmasin."""
        cache = _BatchCache()
        _upsert_record(self.db, self.source, make_record("oai:test:article/2", title="Birinchi maqola", doi="10.1234/abc"), cache)
        _upsert_record(self.db, self.source, make_record("oai:test:article/3", title="Birinchi maqola", doi="10.1234/abc"), cache)
        self.db.commit()

        articles = self.db.query(Article).filter(Article.doi == "10.1234/abc").all()
        self.assertEqual(len(articles), 1)

    def test_same_title_and_year_is_deduplicated_in_one_batch(self) -> None:
        cache = _BatchCache()
        _upsert_record(self.db, self.source, make_record("oai:test:article/4", title="Takroriy sarlavha"), cache)
        _upsert_record(self.db, self.source, make_record("oai:test:article/5", title="Takroriy sarlavha"), cache)
        self.db.commit()

        articles = self.db.query(Article).filter(Article.journal_id == self.source.journal_id).all()
        self.assertEqual(len(articles), 1)
        self.assertEqual(len(articles[0].source_records), 2)


class BibliographicPartsTest(unittest.TestCase):
    """Jild/son/betlarni ajratish. Word boundary yo'q edi: "ECONOMY" dagi "no"
    son = "MY" ni, "INNOVATION" dagi "no" son = "vation" ni berardi."""

    def parts(self, source: str) -> tuple[str | None, str | None, str | None]:
        return _bibliographic_parts({"source": [source]})

    def test_words_containing_markers_are_not_parsed(self) -> None:
        for source in (
            "ECONOMY AND DEVELOPMENT",
            "INNOVATION journal",
            "Journal of evolution studies",
            "Personality research",
            "Автоматики ва информатика",
            "2 person study",
        ):
            with self.subTest(source=source):
                self.assertEqual(self.parts(source), (None, None, None))

    def test_english_prefix_form(self) -> None:
        self.assertEqual(self.parts("Vol. 4, No. 2, pp. 15-27"), ("4", "2", "15-27"))
        self.assertEqual(self.parts("Volume 12 Issue 3 pages 1-9"), ("12", "3", "1-9"))

    def test_russian_prefix_form(self) -> None:
        self.assertEqual(
            self.parts("Том 5, выпуск 2, с. 40-51"),
            ("5", "2", "40-51"),
        )

    def test_ojs_source_form(self) -> None:
        """OJS `dc:source` da betlar markersiz oxirgi segmentda turadi."""
        self.assertEqual(
            self.parts("AGRO INFORM JOURNAL; No. 3 (2022); 37-40 | AGRO INFORM jurnali; No. 3 (2022); 37-40"),
            (None, "3", "37-40"),
        )
        self.assertEqual(
            self.parts("Agro science; Vol. 122 No. 2 (2026): AGRO ILM 2-son [122], 2026; 118-121 | x"),
            ("122", "2", "118-121"),
        )

    def test_year_range_is_not_pages(self) -> None:
        self.assertEqual(self.parts("Some Journal; 2019-2020"), (None, None, None))

    def test_uzbek_postfix_form(self) -> None:
        self.assertEqual(self.parts("4-jild, 2-son, 10-20 bet"), ("4", "2", "10-20"))
        self.assertEqual(self.parts("5-jild 3-son"), ("5", "3", None))
        self.assertEqual(self.parts("Innovatsion iqtisodiyot 2-son 15-22 betlar"), (None, "2", "15-22"))


if __name__ == "__main__":
    unittest.main()


class SourceOwnershipTest(unittest.TestCase):
    """OJS `/index.php/index/oai` butun saytni qaytaradi. U to'rtta jurnalga
    biriktirilib, aynan bir xil 22 ta maqola to'rt marta yozilgan edi."""

    @classmethod
    def setUpClass(cls) -> None:
        init_db()

    def setUp(self) -> None:
        self.db = SessionLocal()
        self.journals = []
        for index in range(2):
            journal = Journal(
                slug=f"own-{id(self)}-{index}",
                name=f"Jurnal {index}",
                short_name="J",
                publisher="X",
                city="Toshkent",
                fields=[],
            )
            self.db.add(journal)
            self.journals.append(journal)
        self.db.commit()

    def tearDown(self) -> None:
        self.db.close()

    def test_healthy_endpoint_cannot_be_reused_by_another_journal(self) -> None:
        from backend.app.services.ingest import audit_source

        url = f"https://platform-{id(self)}.test/index.php/index/oai"
        self.db.add(HarvestSource(journal=self.journals[0], base_url=url, status="healthy"))
        self.db.commit()

        with self.assertRaises(OAIError) as caught:
            audit_source(self.db, self.journals[1], url)
        self.assertIn("boshqa jurnalga biriktirilgan", str(caught.exception))

    def test_same_journal_may_re_audit_its_own_endpoint(self) -> None:
        from backend.app.services.ingest import audit_source

        url = f"https://own-{id(self)}.test/oai"
        self.db.add(HarvestSource(journal=self.journals[0], base_url=url, status="healthy"))
        self.db.commit()
        # Tarmoqqa chiqmasdan faqat guardni tekshiramiz: o'z jurnali uchun
        # guard ishlamasligi kerak, shuning uchun xato tarmoqdan keladi.
        with self.assertRaises(Exception) as caught:
            audit_source(self.db, self.journals[0], url, timeout=1)
        self.assertNotIn("boshqa jurnalga biriktirilgan", str(caught.exception))
