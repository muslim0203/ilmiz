import unittest

from sqlalchemy import create_engine, delete, select
from sqlalchemy.orm import sessionmaker

from backend.app.models import Base, Journal, JournalContact, JournalProfileField
from backend.app.services import journal_edit
from backend.app.services.journal_edit import (
    ValidationError,
    _balance_parens,
    clean,
    clean_contact,
)


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


class BalanceParensTest(unittest.TestCase):
    """Scraper qavs bilan boshlanadigan raqamlarni kesib olgan."""

    def test_drops_unmatched_closing(self) -> None:
        self.assertEqual(_balance_parens("+99871) 262-31-69"), "+99871 262-31-69")

    def test_drops_unmatched_opening(self) -> None:
        self.assertEqual(_balance_parens("(0367 225-40-42"), "0367 225-40-42")

    def test_keeps_balanced_pair(self) -> None:
        self.assertEqual(_balance_parens("+998(71) 262-31-69"), "+998(71) 262-31-69")

    def test_collapses_double_spaces(self) -> None:
        self.assertEqual(_balance_parens("71)  244  35"), "71 244 35")


class CleanContactTest(unittest.TestCase):
    def test_email_is_lowercased(self) -> None:
        kind, value, label = clean_contact("email", "  INFO@Test.UZ ", None)
        self.assertEqual((kind, value, label), ("email", "info@test.uz", "Email"))

    def test_bad_email_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            clean_contact("email", "info@test", None)

    def test_phone_is_normalised(self) -> None:
        _, value, _ = clean_contact("phone", "0367) 225-40-42", None)
        self.assertEqual(value, "0367 225-40-42")

    def test_issn_is_not_a_phone(self) -> None:
        with self.assertRaises(ValidationError):
            clean_contact("phone", "3093-8805", None)

    def test_date_is_not_a_phone(self) -> None:
        with self.assertRaises(ValidationError):
            clean_contact("phone", "2024-07-08 04", None)

    def test_long_address_rejected(self) -> None:
        """Ba'zi «manzil» maydonlariga butun tahririyat ro'yxati tushib qolgan."""
        with self.assertRaises(ValidationError) as caught:
            clean_contact("address", "A" * 500, None)
        self.assertIn("Tahririyat ro‘yxati manzil emas", str(caught.exception))

    def test_custom_label_is_kept(self) -> None:
        _, _, label = clean_contact("email", "a@b.uz", " Bosh muharrir ")
        self.assertEqual(label, "Bosh muharrir")

    def test_unknown_kind_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            clean_contact("telegram", "@kanal", None)

    def test_empty_value_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            clean_contact("email", "   ", None)


class ReplaceContactsTest(unittest.TestCase):
    def setUp(self) -> None:
        engine = create_engine("sqlite://")
        Base.metadata.create_all(engine)
        self.db = sessionmaker(bind=engine)()
        self.journal = Journal(
            slug="test", name="Jurnal", short_name="J", publisher="N", city="Toshkent",
            fields=[], languages=[], oak_status="active", access="unknown",
        )
        self.db.add(self.journal)
        self.db.commit()
        self.db.add(
            JournalContact(
                journal_id=self.journal.id, kind="email", label="Email",
                value="eski@test.uz", source_url="https://jurnal.uz/contact",
            )
        )
        self.db.commit()

    def tearDown(self) -> None:
        self.db.close()

    def test_replaces_the_list(self) -> None:
        contacts, warnings = journal_edit.replace_contacts(
            self.db, self.journal,
            [{"kind": "phone", "value": "0367) 225-40-42", "label": None}],
        )
        self.assertEqual(warnings, [])
        self.assertEqual(len(contacts), 1)
        self.assertEqual(contacts[0]["value"], "0367 225-40-42")
        self.assertTrue(contacts[0]["isManual"])

    def test_unchanged_row_keeps_its_source(self) -> None:
        """Tegilmagan yozuv qayerdan olingani ma'lum bo'lib qolsin."""
        contacts, _ = journal_edit.replace_contacts(
            self.db, self.journal,
            [{"kind": "email", "value": "eski@test.uz", "label": "Email"}],
        )
        self.assertEqual(contacts[0]["sourceUrl"], "https://jurnal.uz/contact")
        self.assertFalse(contacts[0]["isManual"])

    def test_duplicates_are_dropped_with_a_warning(self) -> None:
        contacts, warnings = journal_edit.replace_contacts(
            self.db, self.journal,
            [
                {"kind": "email", "value": "a@b.uz", "label": None},
                {"kind": "email", "value": "a@b.uz", "label": None},
            ],
        )
        self.assertEqual(len(contacts), 1)
        self.assertEqual(len(warnings), 1)

    def test_invalid_row_changes_nothing(self) -> None:
        with self.assertRaises(ValidationError):
            journal_edit.replace_contacts(
                self.db, self.journal,
                [
                    {"kind": "email", "value": "yangi@test.uz", "label": None},
                    {"kind": "email", "value": "buzuq", "label": None},
                ],
            )
        self.db.rollback()
        remaining = [contact.value for contact in self.journal.contacts]
        self.assertEqual(remaining, ["eski@test.uz"])

    def test_empty_list_clears_contacts(self) -> None:
        contacts, _ = journal_edit.replace_contacts(self.db, self.journal, [])
        self.assertEqual(contacts, [])

class ManualDataSurvivesRecollectionTest(unittest.TestCase):
    """Profil qayta yig'ilganda admin kiritgani o'chib ketmasin.

    `collect_profile` aloqa yozuvlari va provenance qatorlarini butunlay
    o'chirib qayta yozardi — ya'ni qo'lda kiritilgan tuzatish ham,
    "bu maydonga tegmang" belgisi ham yo'qolardi.
    """

    def setUp(self) -> None:
        engine = create_engine("sqlite://")
        Base.metadata.create_all(engine)
        self.db = sessionmaker(bind=engine)()
        self.journal = Journal(
            slug="test", name="Jurnal", short_name="J", publisher="N", city="Toshkent",
            fields=[], languages=[], oak_status="active", access="unknown",
        )
        self.db.add(self.journal)
        self.db.commit()

    def tearDown(self) -> None:
        self.db.close()

    def test_delete_query_keeps_manual_contacts(self) -> None:
        self.db.add_all([
            JournalContact(
                journal_id=self.journal.id, kind="phone", label="Telefon",
                value="+998 71 262-31-69", source_url=journal_edit.MANUAL_SOURCE,
            ),
            JournalContact(
                journal_id=self.journal.id, kind="email", label="Email",
                value="scraped@test.uz", source_url="https://jurnal.uz/contact",
            ),
        ])
        self.db.commit()

        # `collect_profile` ichidagi tozalash shartining aynan o'zi.
        self.db.execute(
            delete(JournalContact).where(
                JournalContact.journal_id == self.journal.id,
                JournalContact.source_url != journal_edit.MANUAL_SOURCE,
            )
        )
        self.db.commit()

        remaining = [contact.value for contact in self.journal.contacts]
        self.assertEqual(remaining, ["+998 71 262-31-69"])

    def test_delete_query_keeps_manual_provenance(self) -> None:
        journal_edit.apply_edits(self.db, self.journal, {"city": "Samarqand"})
        self.db.add(
            JournalProfileField(
                journal_id=self.journal.id, field_name="summary", value="yig‘ilgan",
                source_url="https://jurnal.uz", verification_status="collected",
            )
        )
        self.db.commit()

        self.db.execute(
            delete(JournalProfileField).where(
                JournalProfileField.journal_id == self.journal.id,
                JournalProfileField.verification_status != journal_edit.MANUAL_STATUS,
            )
        )
        self.db.commit()

        self.assertEqual(journal_edit.manually_edited(self.db, self.journal.id), {"city"})

if __name__ == "__main__":
    unittest.main()
