import unittest

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from backend.app.models import Base, Journal, JournalProfileField
from backend.app.services import journal_edit
from backend.app.services.journal_edit import ValidationError, clean


class CleanTest(unittest.TestCase):
    def test_issn_is_uppercased_and_checked(self) -> None:
        self.assertEqual(clean("issn", "1234-567x"), "1234-567X")

    def test_issn_with_en_dash_is_accepted(self) -> None:
        """Nusxa ko'chirganda oddiy chiziqcha o'rniga tire tushib qoladi."""
        self.assertEqual(clean("issn", "2181–8207"), "2181-8207")

    def test_bad_issn_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            clean("issn", "12345678")

    def test_empty_issn_clears(self) -> None:
        self.assertIsNone(clean("issn", ""))

    def test_founded_year_range(self) -> None:
        self.assertEqual(clean("founded", "2013"), 2013)
        with self.assertRaises(ValidationError):
            clean("founded", 1200)
        with self.assertRaises(ValidationError):
            clean("founded", "kecha")

    def test_website_requires_scheme(self) -> None:
        self.assertEqual(clean("website", " https://a.uz "), "https://a.uz")
        with self.assertRaises(ValidationError):
            clean("website", "a.uz")

    def test_website_can_be_cleared(self) -> None:
        self.assertIsNone(clean("website", ""))

    def test_lists_drop_blanks_and_duplicates(self) -> None:
        self.assertEqual(clean("fields", [" Tarix ", "Tarix", "", "Texnika"]), ["Tarix", "Texnika"])

    def test_required_text_cannot_be_emptied(self) -> None:
        with self.assertRaises(ValidationError):
            clean("name", "   ")

    def test_enum_values_are_checked(self) -> None:
        self.assertEqual(clean("oak_status", "removed"), "removed")
        with self.assertRaises(ValidationError):
            clean("oak_status", "faol")
        with self.assertRaises(ValidationError):
            clean("access", "ochiq")

    def test_unknown_field_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            clean("slug", "boshqa")


class ApplyEditsTest(unittest.TestCase):
    def setUp(self) -> None:
        engine = create_engine("sqlite://")
        Base.metadata.create_all(engine)
        self.db = sessionmaker(bind=engine)()
        self.journal = Journal(
            slug="test", name="Eski nom", short_name="Eski", publisher="Nashriyot",
            city="Toshkent", fields=["Tarix"], languages=[], oak_status="active",
            access="unknown", website=None, description=None,
        )
        self.db.add(self.journal)
        self.db.commit()

    def tearDown(self) -> None:
        self.db.close()

    def test_applies_and_reports_changes(self) -> None:
        applied, warnings = journal_edit.apply_edits(
            self.db, self.journal, {"name": "Yangi nom", "issn": "2181-8207"}
        )
        self.assertEqual(sorted(applied), ["issn", "name"])
        self.assertEqual(warnings, [])
        self.assertEqual(self.journal.name, "Yangi nom")

    def test_unchanged_value_is_not_recorded(self) -> None:
        """Tegilmagan maydon "qo'lda tahrirlangan" deb belgilanmasin."""
        applied, _ = journal_edit.apply_edits(self.db, self.journal, {"name": "Eski nom"})
        self.assertEqual(applied, {})
        self.assertEqual(journal_edit.manually_edited(self.db, self.journal.id), set())

    def test_manual_edits_are_tracked(self) -> None:
        journal_edit.apply_edits(self.db, self.journal, {"city": "Samarqand"})
        self.assertEqual(journal_edit.manually_edited(self.db, self.journal.id), {"city"})

    def test_repeated_edit_updates_one_row(self) -> None:
        journal_edit.apply_edits(self.db, self.journal, {"city": "Samarqand"})
        journal_edit.apply_edits(self.db, self.journal, {"city": "Buxoro"})
        rows = self.db.scalars(
            select(JournalProfileField).where(
                JournalProfileField.journal_id == self.journal.id
            )
        ).all()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].value, "Buxoro")

    def test_duplicate_issn_warns_without_blocking(self) -> None:
        other = Journal(
            slug="other", name="Boshqa jurnal", short_name="Boshqa", publisher="N",
            city="Toshkent", fields=[], languages=[], oak_status="active",
            access="unknown", issn="3060-4958",
        )
        self.db.add(other)
        self.db.commit()

        applied, warnings = journal_edit.apply_edits(
            self.db, self.journal, {"issn": "3060-4958"}
        )
        self.assertEqual(sorted(applied), ["issn"])
        self.assertEqual(len(warnings), 1)
        self.assertIn("Boshqa jurnal", warnings[0])

    def test_invalid_value_changes_nothing(self) -> None:
        with self.assertRaises(ValidationError):
            journal_edit.apply_edits(
                self.db, self.journal, {"name": "Yangi", "issn": "buzuq"}
            )
        self.db.rollback()
        self.assertEqual(self.journal.name, "Eski nom")

    def test_unknown_field_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            journal_edit.apply_edits(self.db, self.journal, {"slug": "yangi"})

    def test_payload_lists_manual_fields(self) -> None:
        journal_edit.apply_edits(self.db, self.journal, {"website": "https://a.uz"})
        payload = journal_edit.editable_payload(self.db, self.journal)
        self.assertEqual(payload["manualFields"], ["website"])
        self.assertEqual(payload["values"]["website"], "https://a.uz")


if __name__ == "__main__":
    unittest.main()
