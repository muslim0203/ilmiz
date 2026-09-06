"""Harvest'ning o'z-o'zini tiklashi va inkremental rejimi.

Muammo: `harvest-all` faqat `healthy` manbalarni olardi, har qanday xato esa
manbani darhol `failed` qilardi — hech narsa uni qaytarmasdi, shuning uchun
har yurgizishda to'plam kichrayib borgan (11 ta ishlagan manba shu tarzda
"o'lgan"). Inkremental `from` ham qo'lda berilishi kerak edi.
"""
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

database_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
database_file.close()
os.environ["DATABASE_URL"] = f"sqlite:///{database_file.name}"

from backend.app.db import SessionLocal, engine, init_db  # noqa: E402
from backend.app.models import HarvestRun, HarvestSource, Journal  # noqa: E402
from backend.app.services import ingest  # noqa: E402


class HarvestScheduleTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        init_db()

    @classmethod
    def tearDownClass(cls) -> None:
        engine.dispose()
        for suffix in ("", "-wal", "-shm"):
            try:
                os.unlink(database_file.name + suffix)
            except OSError:
                pass

    def setUp(self) -> None:
        self.db = SessionLocal()
        self.journal = Journal(
            slug=f"sched-{id(self)}", name="Jadval jurnali", short_name="J",
            publisher="X", city="Toshkent", fields=[],
        )
        self.db.add(self.journal)
        self.db.commit()

    def tearDown(self) -> None:
        self.db.close()

    def source(self, **kwargs) -> HarvestSource:
        defaults = dict(journal=self.journal, base_url=f"https://s-{id(self)}-{len(self.journal.harvest_sources)}.test/oai")
        defaults.update(kwargs)
        source = HarvestSource(**defaults)
        self.db.add(source)
        self.db.commit()
        return source

    # --- inkremental sana ---------------------------------------------------

    def test_incremental_from_date_uses_last_success_with_overlap(self) -> None:
        source = self.source(status="healthy", last_success_at=datetime(2026, 9, 5, 3, 10, tzinfo=timezone.utc))
        self.assertEqual(ingest.incremental_from_date(source), "2026-09-04")

    def test_never_harvested_source_gets_full_harvest(self) -> None:
        source = self.source(status="healthy", last_success_at=None)
        self.assertIsNone(ingest.incremental_from_date(source))

    # --- degraded va backoff ---------------------------------------------------

    def test_first_failure_degrades_instead_of_failing(self) -> None:
        source = self.source(status="healthy")
        run = HarvestRun(source=source)
        self.db.add(run)
        self.db.commit()
        self.assertTrue(ingest._mark_run_failed(run.id, source.id, "HTTP Error 500"))
        self.db.expire_all()
        self.assertEqual(source.status, "degraded")
        self.assertEqual(source.consecutive_failures, 1)
        self.assertEqual(self.db.get(HarvestRun, run.id).status, "failed")

    def test_failed_only_after_threshold(self) -> None:
        source = self.source(status="degraded", consecutive_failures=ingest.FAILED_AFTER - 1)
        run = HarvestRun(source=source)
        self.db.add(run)
        self.db.commit()
        ingest._mark_run_failed(run.id, source.id, "HTTP Error 500")
        self.db.expire_all()
        self.assertEqual(source.status, "failed")

    def test_backoff_grows_with_failures_and_caps_at_a_week(self) -> None:
        attempted = datetime(2026, 9, 6, 0, 0, tzinfo=timezone.utc)
        self.assertIsNone(ingest.backoff_until(self.source(status="healthy", consecutive_failures=3, last_attempt_at=attempted)))
        one = self.source(status="degraded", consecutive_failures=1, last_attempt_at=attempted)
        self.assertEqual(ingest.backoff_until(one), attempted + timedelta(hours=2))
        many = self.source(status="degraded", consecutive_failures=20, last_attempt_at=attempted)
        self.assertEqual(ingest.backoff_until(many), attempted + timedelta(hours=ingest.MAX_BACKOFF_HOURS))

    # --- manba tanlash ------------------------------------------------------

    def test_selection_includes_degraded_and_skips_backoff(self) -> None:
        now = datetime(2026, 9, 6, 12, 0, tzinfo=timezone.utc)
        healthy = self.source(status="healthy")
        due = self.source(status="degraded", consecutive_failures=1, last_attempt_at=now - timedelta(hours=3))
        waiting = self.source(status="degraded", consecutive_failures=3, last_attempt_at=now - timedelta(hours=1))
        failed = self.source(status="failed", last_success_at=now - timedelta(days=30))
        never = self.source(status="failed", last_success_at=None)
        openalex = self.source(status="healthy", metadata_prefix="openalex")
        self.source(status="pending")

        # Baza testlar orasida umumiy, shuning uchun aniq ro'yxat emas, a'zolik.
        chosen, skipped = ingest.select_harvest_sources(self.db, now=now)
        self.assertIn(healthy.id, chosen)
        self.assertIn(due.id, chosen)
        self.assertIn(waiting.id, skipped)
        self.assertNotIn(waiting.id, chosen)
        for excluded in (failed.id, never.id, openalex.id):
            self.assertNotIn(excluded, chosen)

        chosen, skipped = ingest.select_harvest_sources(self.db, now=now, respect_backoff=False)
        self.assertIn(waiting.id, chosen)
        self.assertEqual(skipped, [])

        chosen, _ = ingest.select_harvest_sources(self.db, now=now, retry_failed=True)
        self.assertIn(failed.id, chosen)
        self.assertNotIn(never.id, chosen)

    def test_degraded_endpoint_still_counts_as_taken(self) -> None:
        """`degraded` manba boshqa jurnalga qayta biriktirilmasin."""
        from harvester.oai_harvester import OAIError

        url = f"https://taken-{id(self)}.test/oai"
        self.source(status="degraded", base_url=url)
        other = Journal(slug=f"other-{id(self)}", name="Boshqa", short_name="B", publisher="X", city="Toshkent", fields=[])
        self.db.add(other)
        self.db.commit()
        with self.assertRaises(OAIError):
            ingest.audit_source(self.db, other, url)


if __name__ == "__main__":
    unittest.main()
