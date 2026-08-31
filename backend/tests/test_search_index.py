import unittest

from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker

from backend.app.models import Article, Base, Journal
from backend.app.services import search_index

# Bazadagi haqiqiy holatlar: qo'shma so'zlar va kirill matn.
SAMPLES = [
    "raqamli pedagogika asoslari",
    "artpedagogikaning imkoniyatlari",
    "xalqpedagogikasi manbalari",
    "oligofrenopedagogika masalalari",
    "iqtisodiy tahlil metodikasi",
    "iqtisodiyot va tahlil",
    "morfologiya va anatomiya",
]


def make_journal() -> Journal:
    return Journal(
        slug="test", name="Jurnal", short_name="J", publisher="N", city="Toshkent",
        fields=[], languages=[], oak_status="active", access="unknown",
    )


class MatchExpressionTest(unittest.TestCase):
    def test_words_become_quoted_phrases(self) -> None:
        self.assertEqual(
            search_index.match_expression("iqtisodiy tahlil"), '"iqtisodiy" "tahlil"'
        )

    def test_fts_operators_are_neutralised(self) -> None:
        """Foydalanuvchi kiritgan matn FTS ifodasi sifatida bajarilmasin."""
        self.assertEqual(search_index.match_expression("pedagogika AND fizika"),
                         '"pedagogika" "and" "fizika"')

    def test_two_letter_word_falls_back(self) -> None:
        """«OR» ikki belgi — trigram uni indekslamaydi, eski yo'l ishlaydi."""
        self.assertIsNone(search_index.match_expression("pedagogika OR fizika"))

    def test_quotes_are_escaped(self) -> None:
        expression = search_index.match_expression('ta"lim tizimi')
        self.assertIsNotNone(expression)
        self.assertIn('""', expression)

    def test_short_word_falls_back(self) -> None:
        """Trigram uch belgidan qisqasini topa olmaydi."""
        self.assertIsNone(search_index.match_expression("va tahlil"))

    def test_empty_query(self) -> None:
        self.assertIsNone(search_index.match_expression("   "))

    def test_cyrillic_is_transliterated(self) -> None:
        """`search_text` lotinlashtirilgan, so'rov ham shunday bo'lishi kerak."""
        self.assertEqual(search_index.match_expression("морфология"), '"morfologiya"')


class FtsQueryTest(unittest.TestCase):
    """FTS natijasi hozirgi `LIKE` yo'li bilan bir xil bo'lishi kerak.

    Trigram tokenizatori aynan shu uchun tanlangan: `unicode61` prefiksdan
    qidiradi va "artpedagogika" kabi qo'shma so'zlarni topmasdi.
    """

    def setUp(self) -> None:
        engine = create_engine("sqlite://")
        Base.metadata.create_all(engine)
        self.db = sessionmaker(bind=engine)()
        journal = make_journal()
        self.db.add(journal)
        self.db.commit()
        for index, value in enumerate(SAMPLES):
            self.db.add(Article(
                journal_id=journal.id, title=value, normalized_title=value,
                authors=[], keywords=[], fields=[], search_text=value, is_deleted=False,
            ))
        self.db.commit()
        self.db.execute(text(
            "CREATE VIRTUAL TABLE articles_fts USING fts5("
            "search_text, content='articles', content_rowid='id', tokenize='trigram')"))
        self.db.execute(text("INSERT INTO articles_fts(articles_fts) VALUES('rebuild')"))
        # Triggerlar migratsiyada yaratiladi; bu yerda ular takrorlanadi.
        # `test_migrations.py` migratsiyadagi variantni alohida tekshiradi.
        self.db.execute(text("""
            CREATE TRIGGER articles_fts_insert AFTER INSERT ON articles BEGIN
                INSERT INTO articles_fts(rowid, search_text) VALUES (new.id, new.search_text);
            END"""))
        self.db.execute(text("""
            CREATE TRIGGER articles_fts_delete AFTER DELETE ON articles BEGIN
                INSERT INTO articles_fts(articles_fts, rowid, search_text)
                VALUES ('delete', old.id, old.search_text);
            END"""))
        self.db.execute(text("""
            CREATE TRIGGER articles_fts_update AFTER UPDATE ON articles BEGIN
                INSERT INTO articles_fts(articles_fts, rowid, search_text)
                VALUES ('delete', old.id, old.search_text);
                INSERT INTO articles_fts(rowid, search_text) VALUES (new.id, new.search_text);
            END"""))
        self.db.commit()

    def tearDown(self) -> None:
        self.db.close()

    def fts_titles(self, query: str) -> set[str]:
        expression = search_index.match_expression(query)
        statement = search_index.apply(
            select(Article).where(Article.is_deleted.is_(False)), expression
        )
        return {article.title for article in self.db.scalars(statement)}

    def like_titles(self, query: str) -> set[str]:
        from backend.app.services.search_text import query_words

        statement = select(Article).where(Article.is_deleted.is_(False))
        for word in query_words(query):
            statement = statement.where(Article.search_text.like(f"%{word}%"))
        return {article.title for article in self.db.scalars(statement)}

    def test_available_detects_the_table(self) -> None:
        self.assertTrue(search_index.available(self.db))

    def test_finds_compound_words(self) -> None:
        """Prefiks qidiruvi buni topmasdi — trigram topadi."""
        found = self.fts_titles("pedagogika")
        self.assertIn("artpedagogikaning imkoniyatlari", found)
        self.assertIn("xalqpedagogikasi manbalari", found)
        self.assertIn("oligofrenopedagogika masalalari", found)

    def test_matches_the_like_path_exactly(self) -> None:
        for query in ("pedagogika", "iqtisodiy tahlil", "morfologiya", "tahlil"):
            with self.subTest(query=query):
                self.assertEqual(self.fts_titles(query), self.like_titles(query))

    def test_all_words_must_match(self) -> None:
        found = self.fts_titles("iqtisodiy tahlil")
        self.assertIn("iqtisodiy tahlil metodikasi", found)
        self.assertNotIn("morfologiya va anatomiya", found)

    def test_cyrillic_query_finds_latin_text(self) -> None:
        self.assertIn("morfologiya va anatomiya", self.fts_titles("морфология"))

    def test_ranking_puts_denser_match_first(self) -> None:
        self.db.add(Article(
            journal_id=1, title="pedagogika pedagogika pedagogika", normalized_title="p",
            authors=[], keywords=[], fields=[],
            search_text="pedagogika pedagogika pedagogika", is_deleted=False,
        ))
        self.db.commit()
        expression = search_index.match_expression("pedagogika")
        statement = search_index.apply(
            select(Article).where(Article.is_deleted.is_(False)), expression
        )
        first = self.db.scalars(statement).first()
        self.assertEqual(first.title, "pedagogika pedagogika pedagogika")

    def test_triggers_keep_the_index_in_sync(self) -> None:
        article = Article(
            journal_id=1, title="yangi", normalized_title="yangi", authors=[], keywords=[],
            fields=[], search_text="noyobkalimatekshiruv", is_deleted=False,
        )
        self.db.add(article)
        self.db.commit()
        self.assertEqual(len(self.fts_titles("noyobkalima")), 1)

        article.search_text = "ozgartirilganmatn"
        self.db.commit()
        self.assertEqual(len(self.fts_titles("noyobkalima")), 0)
        self.assertEqual(len(self.fts_titles("ozgartirilgan")), 1)

        self.db.delete(article)
        self.db.commit()
        self.assertEqual(len(self.fts_titles("ozgartirilgan")), 0)
        self.assertTrue(search_index.check_integrity(self.db))


if __name__ == "__main__":
    unittest.main()
