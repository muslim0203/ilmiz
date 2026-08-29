import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.models import (
    Base,
    EditorialMember,
    Journal,
    JournalContact,
    JournalPolicy,
    JournalProfile,
)
from backend.app.services import completeness, journal_edit

# `prose` kamida 60 belgi talab qiladi — qisqa qoldiq tavsif emas.
REAL_SUMMARY = (
    "Jurnal tabiiy va aniq fanlar yo‘nalishida original ilmiy maqolalarni "
    "chop etadi va yiliga to‘rt marta nashr qilinadi."
)
REAL_ADDRESS = "100174, Toshkent shahri, Olmazor tumani, Universitet ko‘chasi, 4-uy"


def make_journal(**overrides) -> Journal:
    values = dict(
        slug="test", name="Jurnal", short_name="J", publisher="N", city="Toshkent",
        fields=[], languages=[], oak_status="active", access="unknown",
    )
    values.update(overrides)
    return Journal(**values)


class BreakdownTest(unittest.TestCase):
    def setUp(self) -> None:
        engine = create_engine("sqlite://")
        Base.metadata.create_all(engine)
        self.db = sessionmaker(bind=engine)()
        self.journal = make_journal()
        self.db.add(self.journal)
        self.db.commit()

    def tearDown(self) -> None:
        self.db.close()

    def test_empty_journal_scores_zero(self) -> None:
        self.assertEqual(completeness.score(self.db, self.journal), 0.0)

    def test_each_field_is_worth_ten_percent(self) -> None:
        self.journal.issn = "2181-8207"
        self.db.commit()
        self.assertEqual(completeness.score(self.db, self.journal), 10.0)

    def test_counts_related_rows(self) -> None:
        self.db.add_all([
            JournalContact(
                journal_id=self.journal.id, kind="email", label="Email",
                value="a@b.uz", source_url="https://a.uz",
            ),
            JournalPolicy(
                journal_id=self.journal.id, policy_type="submissions",
                title="Talablar", content="matn", source_url="https://a.uz",
            ),
            EditorialMember(journal_id=self.journal.id, name="Kimdir", source_url="https://a.uz"),
        ])
        self.db.commit()
        self.assertEqual(completeness.score(self.db, self.journal), 30.0)

    def test_address_comes_from_profile_not_contacts(self) -> None:
        """Ikkisi boshqa joy: aloqadagi manzil `address` belgisini yopmaydi."""
        self.db.add_all([
            JournalContact(
                journal_id=self.journal.id, kind="address", label="Manzil",
                value=REAL_ADDRESS, source_url="https://a.uz",
            ),
            JournalContact(
                journal_id=self.journal.id, kind="email", label="Email",
                value="a@b.uz", source_url="https://a.uz",
            ),
        ])
        self.db.commit()
        checks = completeness.breakdown(self.db, self.journal)
        self.assertTrue(checks["contacts"])
        self.assertFalse(checks["address"])

    def test_missing_labels_are_readable(self) -> None:
        self.journal.issn = "2181-8207"
        self.db.commit()
        missing = completeness.missing_labels(self.db, self.journal)
        self.assertNotIn("ISSN", missing)
        self.assertIn("Tavsif", missing)
        self.assertEqual(len(missing), 9)

    def test_refresh_without_profile_returns_none(self) -> None:
        self.assertIsNone(completeness.refresh(self.db, self.journal))

    def test_refresh_writes_the_score(self) -> None:
        self.db.add(JournalProfile(journal_id=self.journal.id, summary=REAL_SUMMARY))
        self.journal.issn = "2181-8207"
        self.db.commit()
        self.assertEqual(completeness.refresh(self.db, self.journal), 20.0)
        self.db.commit()
        profile = self.db.query(JournalProfile).one()
        self.assertEqual(profile.completeness_score, 20.0)


class ManualEditUpdatesScoreTest(unittest.TestCase):
    """Qo'lda kiritilgan ma'lumot ballga darhol ta'sir qilishi kerak.

    Ilgari ball faqat `collect_profile` da hisoblanardi, ya'ni admin
    ma'lumot kiritsa ham raqam eski holida qolardi.
    """

    def setUp(self) -> None:
        engine = create_engine("sqlite://")
        Base.metadata.create_all(engine)
        self.db = sessionmaker(bind=engine)()
        self.journal = make_journal()
        self.db.add(self.journal)
        self.db.commit()
        self.db.add(JournalProfile(journal_id=self.journal.id))
        self.db.commit()

    def tearDown(self) -> None:
        self.db.close()

    def score(self) -> float:
        return self.db.query(JournalProfile).one().completeness_score

    def test_editing_issn_raises_the_score(self) -> None:
        self.assertEqual(self.score(), 0.0)
        journal_edit.apply_edits(self.db, self.journal, {"issn": "2181-8207"})
        self.assertEqual(self.score(), 10.0)

    def test_editing_profile_summary_raises_the_score(self) -> None:
        journal_edit.apply_edits(self.db, self.journal, {"summary": REAL_SUMMARY})
        self.assertEqual(self.score(), 10.0)
        profile = self.db.query(JournalProfile).one()
        self.assertEqual(profile.summary, REAL_SUMMARY)

    def test_profile_fields_are_tracked_as_manual(self) -> None:
        journal_edit.apply_edits(self.db, self.journal, {"address": REAL_ADDRESS})
        self.assertEqual(journal_edit.manually_edited(self.db, self.journal.id), {"address"})

    def test_contacts_change_updates_the_score(self) -> None:
        journal_edit.replace_contacts(
            self.db, self.journal, [{"kind": "email", "value": "a@b.uz", "label": None}]
        )
        self.assertEqual(self.score(), 10.0)

    def test_clearing_a_field_lowers_the_score(self) -> None:
        journal_edit.apply_edits(self.db, self.journal, {"summary": REAL_SUMMARY})
        self.assertEqual(self.score(), 10.0)
        journal_edit.apply_edits(self.db, self.journal, {"summary": ""})
        self.assertEqual(self.score(), 0.0)

    def test_profile_row_is_created_when_missing(self) -> None:
        other = make_journal(slug="other", name="Boshqa")
        self.db.add(other)
        self.db.commit()
        journal_edit.apply_edits(self.db, other, {"summary": REAL_SUMMARY})
        profile = (
            self.db.query(JournalProfile).filter(JournalProfile.journal_id == other.id).one()
        )
        self.assertEqual(profile.summary, REAL_SUMMARY)
        self.assertEqual(profile.completeness_score, 10.0)


class QualityChecksTest(unittest.TestCase):
    """Ball to'ldirilganini emas, qiymat haqiqatan shu maydonga
    o'xshashini talab qiladi. Aks holda axlat ballni ko'tarardi."""

    def setUp(self) -> None:
        engine = create_engine("sqlite://")
        Base.metadata.create_all(engine)
        self.db = sessionmaker(bind=engine)()
        self.journal = make_journal()
        self.db.add(self.journal)
        self.db.commit()

    def tearDown(self) -> None:
        self.db.close()

    def checks(self, **profile_values) -> dict[str, bool]:
        self.db.query(JournalProfile).delete()
        self.db.add(JournalProfile(journal_id=self.journal.id, **profile_values))
        self.db.commit()
        return completeness.breakdown(self.db, self.journal)

    def test_short_summary_does_not_count(self) -> None:
        self.assertFalse(self.checks(summary="Jurnal haqida")["summary"])

    def test_page_script_summary_does_not_count(self) -> None:
        junk = '$(function () { $(".header").removeClass("bg-dark"); }); ' * 2
        self.assertFalse(self.checks(summary=junk)["summary"])

    def test_real_summary_counts(self) -> None:
        self.assertTrue(self.checks(summary=REAL_SUMMARY)["summary"])

    def test_submission_rules_are_not_an_address(self) -> None:
        rules = (
            "6. Maqolaning original tilida, maqolaning oxirida mualliflar "
            "to‘g‘risida to‘liq ma’lumot berilishi kerak."
        )
        self.assertFalse(self.checks(address=rules)["address"])

    def test_real_address_counts(self) -> None:
        self.assertTrue(self.checks(address=REAL_ADDRESS)["address"])

    def test_latest_issue_needs_a_number(self) -> None:
        """Scraper 238 tadan 48 tasiga sahifa tugmasini yozib qo'ygan."""
        for junk in ("Login", "Maqolalar", "Full Issue"):
            self.assertFalse(self.checks(latest_issue=junk)["latest_issue"], junk)
        self.assertTrue(self.checks(latest_issue="Том 28 № 2 (2026)")["latest_issue"])

    def test_address_alone_is_not_contact_info(self) -> None:
        self.db.add(
            JournalContact(
                journal_id=self.journal.id, kind="address", label="Manzil",
                value=REAL_ADDRESS, source_url="https://a.uz",
            )
        )
        self.db.commit()
        self.assertFalse(completeness.breakdown(self.db, self.journal)["contacts"])

    def test_email_counts_as_contact_info(self) -> None:
        self.db.add(
            JournalContact(
                journal_id=self.journal.id, kind="email", label="Email",
                value="a@b.uz", source_url="https://a.uz",
            )
        )
        self.db.commit()
        self.assertTrue(completeness.breakdown(self.db, self.journal)["contacts"])

    def test_empty_policy_does_not_count(self) -> None:
        self.db.add(
            JournalPolicy(
                journal_id=self.journal.id, policy_type="submissions",
                title="Talablar", content="", source_url="https://a.uz",
            )
        )
        self.db.commit()
        self.assertFalse(completeness.breakdown(self.db, self.journal)["policies"])

    def test_malformed_issn_does_not_count(self) -> None:
        self.journal.issn = "12345678"
        self.db.commit()
        self.assertFalse(completeness.breakdown(self.db, self.journal)["issn"])

if __name__ == "__main__":
    unittest.main()
