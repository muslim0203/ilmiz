import os
import tempfile
import unittest

database_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
database_file.close()
os.environ.setdefault("DATABASE_URL", f"sqlite:///{database_file.name}")

from sqlalchemy import func, select  # noqa: E402

from backend.app.db import SessionLocal, engine, init_db  # noqa: E402
from backend.app.models import Article, Journal  # noqa: E402


class UnicodeSearchTest(unittest.TestCase):
    """SQLite'ning o'rnatilgan `lower()` faqat ASCII bilan ishlaydi, shuning
    uchun kirill sarlavhalarni kichik harf bilan qidirib bo'lmasdi."""

    @classmethod
    def setUpClass(cls) -> None:
        init_db()
        with SessionLocal() as db:
            journal = Journal(
                slug="unicode-test", name="Тест журнали", short_name="T",
                publisher="X", city="Toshkent", fields=[],
            )
            db.add(journal)
            db.flush()
            for title in (
                "МОРФОФУНКЦИОНАЛЬНАЯ ДИАГНОСТИКА ПРЕДРАКОВЫХ ПРОЦЕССОВ",
                "МЕТАБОЛИК СИНДРОМДА ОШҚОЗОН ШИЛЛИҚ ҚАВАТИДА",
                "ISHEMIK INSULTDA MIYA TO‘QIMASI",
            ):
                db.add(Article(journal=journal, title=title, normalized_title=title.casefold()))
            db.commit()

    @classmethod
    def tearDownClass(cls) -> None:
        engine.dispose()
        for suffix in ("", "-wal", "-shm"):
            try:
                os.unlink(database_file.name + suffix)
            except OSError:
                pass

    def count(self, needle: str) -> int:
        with SessionLocal() as db:
            return db.scalar(
                select(func.count()).select_from(Article).where(Article.title.ilike(f"%{needle}%"))
            )

    def test_sqlite_lower_handles_cyrillic(self) -> None:
        with SessionLocal() as db:
            self.assertEqual(db.scalar(select(func.lower("МОРФО"))), "морфо")

    def test_russian_lowercase_query_finds_uppercase_title(self) -> None:
        self.assertEqual(self.count("морфофункциональная"), 1)
        self.assertEqual(self.count("МОРФОФУНКЦИОНАЛЬНАЯ"), 1)
        self.assertEqual(self.count("Морфофункциональная"), 1)

    def test_uzbek_cyrillic_with_special_letters(self) -> None:
        """Ў, Қ, Ҳ, Ғ harflari ham to'g'ri kichiklashishi kerak."""
        self.assertEqual(self.count("ошқозон"), 1)
        self.assertEqual(self.count("метаболик синдромда"), 1)

    def test_latin_search_still_works(self) -> None:
        for needle in ("ishemik", "ISHEMIK", "Ishemik"):
            with self.subTest(needle=needle):
                self.assertEqual(self.count(needle), 1)

    def test_unrelated_query_finds_nothing(self) -> None:
        self.assertEqual(self.count("топилмайдиган"), 0)


if __name__ == "__main__":
    unittest.main()
