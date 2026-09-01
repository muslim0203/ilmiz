import unittest

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from backend.app.models import Article, Base, HarvestSource, Journal, SourceRecord
from backend.app.services import openalex


def work(**overrides) -> dict:
    """OpenAlex javobining bir yozuvi."""
    base = {
        "id": "https://openalex.org/W123",
        "doi": "https://doi.org/10.70189/1992-9498.1016",
        "title": "Grinding process of cotton seed kernels",
        "publication_date": "2019-10-18",
        "publication_year": 2019,
        "language": "en",
        "type": "article",
        "biblio": {"volume": "2018", "issue": "3", "first_page": "63", "last_page": "67"},
        "authorships": [
            {"author": {"display_name": "Azimjon Akhmedov"}},
            {"author": {"display_name": "Saidakbar Abdurakhimov"}},
        ],
        "abstract_inverted_index": {"It": [0], "is": [1], "established": [2]},
        "primary_location": {"landing_page_url": "https://doi.org/10.70189/1992-9498.1016"},
        "best_oa_location": {"pdf_url": None},
    }
    base.update(overrides)
    return base


class NormaliseTest(unittest.TestCase):
    def test_maps_the_fields(self) -> None:
        record = openalex.normalise(work())
        self.assertEqual(record["title"], "Grinding process of cotton seed kernels")
        self.assertEqual(record["authors"], ["Azimjon Akhmedov", "Saidakbar Abdurakhimov"])
        self.assertEqual(record["publication_date"], "2019-10-18")
        self.assertEqual(record["volume"], "2018")
        self.assertEqual(record["pages"], "63-67")
        self.assertEqual(record["openalex_id"], "W123")

    def test_doi_prefix_is_stripped(self) -> None:
        """Bizda DOI `10.xxxx/yyy` shaklida saqlanadi."""
        self.assertEqual(openalex.normalise(work())["doi"], "10.70189/1992-9498.1016")

    def test_missing_doi(self) -> None:
        self.assertIsNone(openalex.normalise(work(doi=None))["doi"])

    def test_single_page_is_kept(self) -> None:
        record = openalex.normalise(work(biblio={"first_page": "63"}))
        self.assertEqual(record["pages"], "63")

    def test_untitled_work_is_skipped(self) -> None:
        self.assertIsNone(openalex.normalise(work(title=None)))

    def test_non_article_types_are_skipped(self) -> None:
        """Tahririyat xati yoki datasetni indeksga qo'shmaymiz."""
        self.assertIsNone(openalex.normalise(work(type="dataset")))
        self.assertIsNone(openalex.normalise(work(type="editorial")))

    def test_review_is_kept(self) -> None:
        self.assertIsNotNone(openalex.normalise(work(type="review")))

    def test_authors_without_names_are_dropped(self) -> None:
        record = openalex.normalise(work(authorships=[{"author": {}}]))
        self.assertEqual(record["authors"], [])


class AbstractTest(unittest.TestCase):
    def test_reconstructs_word_order(self) -> None:
        inverted = {"quyosh": [1], "Bugun": [0], "chiqdi": [2]}
        self.assertEqual(openalex.reconstruct_abstract(inverted), "Bugun quyosh chiqdi")

    def test_repeated_word_appears_twice(self) -> None:
        self.assertEqual(
            openalex.reconstruct_abstract({"ha": [0, 2], "yo": [1]}), "ha yo ha"
        )

    def test_empty(self) -> None:
        self.assertIsNone(openalex.reconstruct_abstract(None))
        self.assertIsNone(openalex.reconstruct_abstract({}))


class ImportTest(unittest.TestCase):
    """Import mavjud ma'lumot ustiga yozmasligi kerak.

    OAI orqali yig'ilgan yozuv nashriyotning birlamchi ma'lumoti;
    OpenAlex uchinchi tomon indeksi va faqat bo'sh joyni to'ldiradi.
    """

    def setUp(self) -> None:
        engine = create_engine("sqlite://")
        Base.metadata.create_all(engine)
        self.db = sessionmaker(bind=engine)()
        self.journal = Journal(
            slug="test", name="Jurnal", short_name="J", publisher="N", city="Toshkent",
            fields=[], languages=[], oak_status="active", access="unknown",
            issn="1992-9498",
        )
        self.db.add(self.journal)
        self.db.commit()

    def tearDown(self) -> None:
        self.db.close()

    def test_source_row_marks_the_origin(self) -> None:
        source = openalex._harvest_source(self.db, self.journal, "S42")
        self.db.commit()
        self.assertEqual(source.metadata_prefix, "openalex")
        self.assertEqual(source.repository_name, "OpenAlex")
        self.assertIn("api.openalex.org", source.base_url)

    def test_source_row_is_reused(self) -> None:
        first = openalex._harvest_source(self.db, self.journal, "S42")
        self.db.commit()
        second = openalex._harvest_source(self.db, self.journal, "S42")
        self.db.commit()
        self.assertEqual(first.id, second.id)
        self.assertEqual(
            self.db.scalar(select(HarvestSource).where(HarvestSource.journal_id == self.journal.id)).id,
            first.id,
        )

    def test_openalex_source_is_not_an_oai_source(self) -> None:
        """`harvest-all` faqat `oai_dc` ni oladi — bu manba unga tushmasin."""
        openalex._harvest_source(self.db, self.journal, "S42")
        self.db.commit()
        oai = self.db.scalars(
            select(HarvestSource.id).where(HarvestSource.metadata_prefix == "oai_dc")
        ).all()
        self.assertEqual(oai, [])

    def test_both_issns_are_tried(self) -> None:
        """Bosma ISSN ko'pincha OpenAlex'da yo'q — e-ISSN ham sinalsin.

        «Adabiy meros» aynan shu sababli topilmay qolgan edi.
        """
        from backend.app.services import openalex as module

        asked: list[str] = []

        def fake_find(issn, **kwargs):
            asked.append(issn)
            return {"id": "S1", "name": "X", "works_count": 0} if issn == "3093-916X" else None

        original_find, original_iter = module.find_source, module.iter_works
        module.find_source = fake_find
        module.iter_works = lambda *args, **kwargs: iter(())  # tarmoqqa chiqmasin
        try:
            self.journal.issn = "2181-1320"
            self.journal.eissn = "3093-916X"
            self.db.commit()
            result = module.import_journal(self.db, self.journal, dry_run=True)
        finally:
            module.find_source, module.iter_works = original_find, original_iter
        self.assertEqual(asked, ["2181-1320", "3093-916X"])
        self.assertEqual(result["status"], "ok")

    def test_journal_without_issn_is_refused(self) -> None:
        self.journal.issn = None
        self.db.commit()
        self.assertEqual(
            openalex.import_journal(self.db, self.journal)["status"], "issn yo‘q"
        )


if __name__ == "__main__":
    unittest.main()
