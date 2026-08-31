import os
import sqlite3
import tempfile
import unittest
from pathlib import Path

from sqlalchemy import create_engine, inspect

from backend.app.db import BASELINE_REVISION
from backend.app.models import Base

ROOT = Path(__file__).resolve().parents[2]


def alembic_config(url: str):
    from alembic.config import Config

    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "backend" / "migrations"))
    config.set_main_option("sqlalchemy.url", url)
    return config


class MigrationTest(unittest.TestCase):
    """Migratsiyalar modellar bilan bir qadamda turishi kerak.

    Modelga jadval yoki ustun qo'shilib, migratsiya yozilmasa, bu testlar
    yiqiladi — ilgari bunday nomuvofiqlik sezilmay qolardi va jonli bazada
    ikkita indeks yo'q bo'lib ketgan edi.
    """

    def setUp(self) -> None:
        handle, self.path = tempfile.mkstemp(suffix=".db")
        os.close(handle)
        os.unlink(self.path)  # Alembic o'zi yaratsin
        self.url = f"sqlite:///{self.path}"

    def tearDown(self) -> None:
        Path(self.path).unlink(missing_ok=True)

    def upgrade(self) -> None:
        """Migratsiyalarni vaqtinchalik bazaga qo'llaydi.

        Manzil `alembic.ini` orqali beriladi — `env.py` uni ilovaning
        `DATABASE_URL` idan ustun qo'yadi, ya'ni jonli bazaga tegilmaydi.
        """
        from alembic import command

        command.upgrade(alembic_config(self.url), "head")

    def test_migrations_build_the_same_tables_as_the_models(self) -> None:
        self.upgrade()
        engine = create_engine(self.url)
        migrated = set(inspect(engine).get_table_names()) - {"alembic_version"}
        engine.dispose()
        self.assertEqual(migrated, set(Base.metadata.tables))

    def test_expression_indexes_are_created(self) -> None:
        """SQLite ularni aks ettira olmaydi, ya'ni autogenerate o'tkazadi."""
        self.upgrade()
        connection = sqlite3.connect(self.path)
        names = {row[1] for row in connection.execute("pragma index_list(articles)")}
        connection.close()
        self.assertIn("ix_articles_feed", names)
        self.assertIn("ix_articles_journal_feed", names)

    def test_declared_indexes_exist(self) -> None:
        """Modelda `index=True` bo'lgan ustunning indeksi bazada bo'lsin."""
        self.upgrade()
        connection = sqlite3.connect(self.path)
        articles = {row[1] for row in connection.execute("pragma index_list(articles)")}
        users = {row[1] for row in connection.execute("pragma index_list(users)")}
        connection.close()
        self.assertIn("ix_articles_publication_date", articles)
        self.assertIn("ix_users_is_admin", users)

    def test_baseline_revision_exists(self) -> None:
        """`init_db` mavjud bazani shu versiyada belgilaydi."""
        from alembic.script import ScriptDirectory

        script = ScriptDirectory.from_config(alembic_config(self.url))
        revisions = {revision.revision for revision in script.walk_revisions()}
        self.assertIn(BASELINE_REVISION, revisions)

    def test_single_head(self) -> None:
        """Ikki boshli tarix qo'shilib ketmasin."""
        from alembic.script import ScriptDirectory

        script = ScriptDirectory.from_config(alembic_config(self.url))
        self.assertEqual(len(script.get_heads()), 1)


if __name__ == "__main__":
    unittest.main()
