"""Maqola ro'yxatlarining nashr sanasi bo'yicha tartibi (`services/feed.py`)."""
import unittest

from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session, selectinload
from sqlalchemy.pool import StaticPool

from backend.app.db import Base
from backend.app.models import Article, Journal
from backend.app.services import feed

DAY = "2026-09-11"


class FeedOrderTest(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        journal = Journal(slug="j", name="J", short_name="J", publisher="P", city="Тошкент", fields=["Pedagogika"])
        other = Journal(slug="k", name="K", short_name="K", publisher="P", city="Тошкент", fields=["Pedagogika"])
        self.db.add_all([journal, other])
        self.db.flush()
        self.journal_id, self.other_id = journal.id, other.id
        # Qo'shilish tartibi ataylab nashr tartibiga teskari: ilgari tartib
        # `publication_year, id` bo'lgani uchun oxirgi qo'shilgan tepada edi.
        rows = [
            ("bugun", "2026-09-11", journal.id),
            ("kelajak", "2026-09-20", journal.id),
            ("sanasiz", None, journal.id),
            ("otgan-yil", "2025-12-31", other.id),
            ("ikki-sentabr", "2026-09-02", journal.id),
            ("uzoq-kelajak", "2026-12-31", other.id),
        ]
        self.ids = {}
        for title, date, journal_id in rows:
            article = Article(journal_id=journal_id, title=title, normalized_title=title, authors=["A"],
                              publication_date=date, publication_year=int(date[:4]) if date else 2026)
            self.db.add(article)
            self.db.flush()
            self.ids[title] = article.id
        self.db.commit()
        self.base = select(Article).options(selectinload(Article.journal)).where(Article.is_deleted.is_(False))

    def tearDown(self) -> None:
        self.db.close()
        self.engine.dispose()

    def titles(self, **kwargs) -> list[str]:
        return [item.title for item in feed.page(self.db, self.base, day=DAY, **kwargs)]

    def test_published_first_by_date_then_future_then_undated(self) -> None:
        self.assertEqual(
            self.titles(limit=10),
            ["bugun", "ikki-sentabr", "otgan-yil", "kelajak", "uzoq-kelajak", "sanasiz"],
        )

    def test_pages_join_without_gaps_or_overlap(self) -> None:
        full = self.titles(limit=10)
        for size in (1, 2, 4):
            pages = []
            for offset in range(0, len(full), size):
                pages.extend(self.titles(limit=size, offset=offset))
            self.assertEqual(pages, full, size)
        self.assertEqual(self.titles(limit=5, offset=10), [])

    def test_future_article_takes_its_place_when_the_day_comes(self) -> None:
        order = [item.title for item in feed.page(self.db, self.base, day="2026-09-20", limit=3)]
        self.assertEqual(order, ["kelajak", "bugun", "ikki-sentabr"])

    def test_filters_are_kept(self) -> None:
        only = self.base.where(Article.journal_id == self.other_id)
        self.assertEqual([item.title for item in feed.page(self.db, only, day=DAY, limit=10)],
                         ["otgan-yil", "uzoq-kelajak"])

    def test_default_day_is_uzbekistan_date(self) -> None:
        self.assertRegex(feed.today(), r"^\d{4}-\d{2}-\d{2}$")

    def test_published_part_uses_the_expression_index(self) -> None:
        """Literal `substr(..., 1, 10)` bo'lmasa SQLite indeksni tanimay, butun jadvalni saralardi."""
        captured: list[tuple[str, object]] = []

        def capture(conn, cursor, statement, parameters, context, executemany):
            captured.append((statement, parameters))

        event.listen(self.engine, "before_cursor_execute", capture)
        try:
            feed.page(self.db, select(Article).where(Article.is_deleted.is_(False)), day=DAY, limit=2)
        finally:
            event.remove(self.engine, "before_cursor_execute", capture)
        sql, params = captured[0]
        with self.engine.connect() as connection:
            plan = " ".join(str(row) for row in connection.exec_driver_sql("EXPLAIN QUERY PLAN " + sql, params))
        self.assertIn("ix_articles_published", plan)
        self.assertNotIn("TEMP B-TREE", plan)


if __name__ == "__main__":
    unittest.main()
