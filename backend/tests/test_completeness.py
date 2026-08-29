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
        self.db.add(
            JournalContact(
                journal_id=self.journal.id, kind="address", label="Manzil",
                value="Toshkent, Universitet 4", source_url="https://a.uz",
            )
        )
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
        self.db.add(JournalProfile(journal_id=self.journal.id, summary="Tavsif"))
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
        journal_edit.apply_edits(self.db, self.journal, {"summary": "Jurnal tavsifi"})
        self.assertEqual(self.score(), 10.0)
        profile = self.db.query(JournalProfile).one()
        self.assertEqual(profile.summary, "Jurnal tavsifi")

    def test_profile_fields_are_tracked_as_manual(self) -> None:
        journal_edit.apply_edits(self.db, self.journal, {"address": "Toshkent, Universitet 4"})
        self.assertEqual(journal_edit.manually_edited(self.db, self.journal.id), {"address"})

    def test_contacts_change_updates_the_score(self) -> None:
        journal_edit.replace_contacts(
            self.db, self.journal, [{"kind": "email", "value": "a@b.uz", "label": None}]
        )
        self.assertEqual(self.score(), 10.0)

    def test_clearing_a_field_lowers_the_score(self) -> None:
        journal_edit.apply_edits(self.db, self.journal, {"summary": "Jurnal tavsifi"})
        self.assertEqual(self.score(), 10.0)
        journal_edit.apply_edits(self.db, self.journal, {"summary": ""})
        self.assertEqual(self.score(), 0.0)

    def test_profile_row_is_created_when_missing(self) -> None:
        other = make_journal(slug="other", name="Boshqa")
        self.db.add(other)
        self.db.commit()
        journal_edit.apply_edits(self.db, other, {"summary": "Tavsif"})
        profile = (
            self.db.query(JournalProfile).filter(JournalProfile.journal_id == other.id).one()
        )
        self.assertEqual(profile.summary, "Tavsif")
        self.assertEqual(profile.completeness_score, 10.0)


if __name__ == "__main__":
    unittest.main()
