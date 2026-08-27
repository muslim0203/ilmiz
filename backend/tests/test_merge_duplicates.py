import os
import tempfile
import unittest

database_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
database_file.close()
os.environ.setdefault("DATABASE_URL", f"sqlite:///{database_file.name}")

from sqlalchemy import select  # noqa: E402

from backend.app.db import SessionLocal, engine, init_db  # noqa: E402
from backend.app.models import (  # noqa: E402
    Article,
    HarvestSource,
    Journal,
    JournalContact,
    JournalProfile,
    SourceRecord,
)
from backend.app.services.merge_duplicates import (  # noqa: E402
    find_duplicate_groups,
    merge_group,
)

_counter = iter(range(1, 10_000))


class MergeDuplicatesTest(unittest.TestCase):
    """Bir jurnal kirill va lotin nomi bilan ikki marta ro'yxatga olingan."""

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
        self.tag = next(_counter)

    def tearDown(self) -> None:
        self.db.close()

    def make_journal(self, name: str) -> Journal:
        journal = Journal(
            slug=f"{name.lower().replace(' ', '-')}-{self.tag}",
            name=name,
            short_name="J",
            publisher="X",
            city="Toshkent",
            fields=["Test"],
        )
        self.db.add(journal)
        self.db.commit()
        return journal

    def make_article(self, journal: Journal, title: str, *, doi: str | None = None, year: int = 2025) -> Article:
        article = Article(
            journal=journal,
            title=title,
            normalized_title=title.casefold(),
            publication_year=year,
            doi=doi,
        )
        self.db.add(article)
        self.db.commit()
        return article

    def plan_for(self, canonical: Journal, duplicate: Journal):
        plans = [
            plan for plan in find_duplicate_groups(self.db)
            if {plan.canonical_id, *plan.duplicate_ids} == {canonical.id, duplicate.id}
        ]
        self.assertEqual(len(plans), 1, "guruh topilmadi")
        return plans[0]

    def test_cyrillic_and_latin_names_form_one_group(self) -> None:
        latin = self.make_journal(f"Meros {self.tag}")
        cyrillic = self.make_journal(f"Мерос {self.tag}")
        plan = self.plan_for(latin, cyrillic)
        self.assertEqual(len(plan.duplicate_ids), 1)

    def test_journal_with_more_articles_becomes_canonical(self) -> None:
        poor = self.make_journal(f"Nur {self.tag}")
        rich = self.make_journal(f"Нур {self.tag}")
        self.make_article(rich, "a")
        self.make_article(rich, "b")
        self.make_article(poor, "c")
        plan = self.plan_for(rich, poor)
        self.assertEqual(plan.canonical_id, rich.id)

    def test_articles_move_to_canonical(self) -> None:
        canonical = self.make_journal(f"Ilm {self.tag}")
        duplicate = self.make_journal(f"Илм {self.tag}")
        self.make_article(canonical, "birinchi")
        moved = self.make_article(duplicate, "ikkinchi")
        merge_group(self.db, self.plan_for(canonical, duplicate))
        self.db.commit()

        self.assertEqual(self.db.get(Article, moved.id).journal_id, canonical.id)
        self.assertIsNone(self.db.get(Journal, duplicate.id))

    def test_article_with_doi_moves_and_keeps_its_records(self) -> None:
        """`articles.doi` global unique, shuning uchun ikki jurnalda bir xil DOI
        bo'lishi mumkin emas — ko'chirish uni buzmasligini tekshiramiz."""
        canonical = self.make_journal(f"Fan {self.tag}")
        duplicate = self.make_journal(f"Фан {self.tag}")
        moved = self.make_article(duplicate, "maqola", doi=f"10.1234/x{self.tag}")
        self.db.add(SourceRecord(
            source=HarvestSource(journal=duplicate, base_url=f"https://a{self.tag}.test/oai"),
            oai_identifier=f"oai:{self.tag}:1",
            article=moved,
        ))
        self.db.commit()

        plan = self.plan_for(canonical, duplicate)
        merge_group(self.db, plan)
        self.db.commit()

        article = self.db.get(Article, moved.id)
        # Maqolasi bor jurnal kanonik bo'ladi, shuning uchun rejaga qaraymiz.
        self.assertEqual(article.journal_id, plan.canonical_id)
        self.assertEqual(article.doi, f"10.1234/x{self.tag}")
        record = self.db.scalar(select(SourceRecord).where(SourceRecord.oai_identifier == f"oai:{self.tag}:1"))
        self.assertEqual(record.article_id, moved.id)

    def test_same_title_and_year_is_merged(self) -> None:
        canonical = self.make_journal(f"Tib {self.tag}")
        duplicate = self.make_journal(f"Тиб {self.tag}")
        kept = self.make_article(canonical, "bir xil sarlavha", year=2024)
        self.make_article(duplicate, "bir xil sarlavha", year=2024)
        merge_group(self.db, self.plan_for(canonical, duplicate))
        self.db.commit()

        titles = self.db.scalars(
            select(Article).where(Article.journal_id == canonical.id, Article.publication_year == 2024)
        ).all()
        self.assertEqual([item.id for item in titles], [kept.id])

    def test_identical_oai_endpoint_is_merged(self) -> None:
        """`harvest_sources` da (journal_id, base_url, prefix) unique."""
        canonical = self.make_journal(f"Ziyo {self.tag}")
        duplicate = self.make_journal(f"Зиё {self.tag}")
        url = f"https://shared{self.tag}.test/oai"
        self.db.add(HarvestSource(journal=canonical, base_url=url))
        self.db.add(HarvestSource(journal=duplicate, base_url=url))
        self.db.commit()

        merge_group(self.db, self.plan_for(canonical, duplicate))
        self.db.commit()

        sources = self.db.scalars(select(HarvestSource).where(HarvestSource.base_url == url)).all()
        self.assertEqual(len(sources), 1)
        self.assertEqual(sources[0].journal_id, canonical.id)

    def test_duplicate_contacts_are_dropped_not_moved(self) -> None:
        """`journal_contacts` da (journal_id, kind, value) unique."""
        canonical = self.make_journal(f"Aloqa {self.tag}")
        duplicate = self.make_journal(f"Алоқа {self.tag}")
        self.db.add(JournalContact(journal=canonical, kind="email", value="a@b.uz", source_url="x"))
        self.db.add(JournalContact(journal=duplicate, kind="email", value="a@b.uz", source_url="y"))
        self.db.add(JournalContact(journal=duplicate, kind="email", value="c@d.uz", source_url="y"))
        self.db.commit()

        merge_group(self.db, self.plan_for(canonical, duplicate))
        self.db.commit()

        values = sorted(
            row.value for row in self.db.scalars(
                select(JournalContact).where(JournalContact.journal_id == canonical.id)
            )
        )
        self.assertEqual(values, ["a@b.uz", "c@d.uz"])

    def test_only_one_profile_survives(self) -> None:
        """`journal_profiles` da journal_id unique."""
        canonical = self.make_journal(f"Profil {self.tag}")
        duplicate = self.make_journal(f"Профил {self.tag}")
        self.db.add(JournalProfile(journal=canonical, summary="kanonik"))
        self.db.add(JournalProfile(journal=duplicate, summary="nusxa"))
        self.db.commit()

        merge_group(self.db, self.plan_for(canonical, duplicate))
        self.db.commit()

        profiles = self.db.scalars(
            select(JournalProfile).where(JournalProfile.journal_id == canonical.id)
        ).all()
        self.assertEqual(len(profiles), 1)
        self.assertEqual(profiles[0].summary, "kanonik")


if __name__ == "__main__":
    unittest.main()
