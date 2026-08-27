import unittest

from backend.app.services.search_text import article_search_text, normalize, query_words


class NormalizeTest(unittest.TestCase):
    def test_cyrillic_and_latin_meet_in_the_middle(self) -> None:
        self.assertEqual(normalize("Сулайманова"), normalize("Sulaymanova"))
        self.assertEqual(normalize("СУЛАЙМАНОВА"), normalize("sulaymanova"))

    def test_uzbek_cyrillic_letters(self) -> None:
        self.assertEqual(normalize("ОШҚОЗОН"), "oshqozon")
        self.assertEqual(normalize("Ўзбекистон"), "ozbekiston")
        self.assertEqual(normalize("ТИББИЁТ"), "tibbiyot")

    def test_apostrophe_variants_collapse(self) -> None:
        variants = ["O‘zbekiston", "O'zbekiston", "Oʻzbekiston", "Ozbekiston"]
        self.assertEqual(len({normalize(item) for item in variants}), 1)

    def test_whitespace_is_collapsed(self) -> None:
        self.assertEqual(normalize("  ikki   so‘z  "), "ikki soz")

    def test_empty_input(self) -> None:
        self.assertEqual(normalize(None), "")
        self.assertEqual(normalize(""), "")


class QueryWordsTest(unittest.TestCase):
    def test_words_are_split_and_normalized(self) -> None:
        self.assertEqual(query_words("Kamoliddin Sharofiddinov"), ["kamoliddin", "sharofiddinov"])
        self.assertEqual(query_words("Мария Сулайманова"), ["mariya", "sulaymanova"])

    def test_single_letters_are_dropped(self) -> None:
        """Bitta harf butun bazaga mos keladi — foydasi yo'q."""
        self.assertEqual(query_words("a b to"), ["to"])

    def test_word_order_does_not_matter(self) -> None:
        self.assertEqual(
            sorted(query_words("Sharofiddinov Kamoliddin")),
            sorted(query_words("Kamoliddin Sharofiddinov")),
        )


class ArticleSearchTextTest(unittest.TestCase):
    def test_includes_title_abstract_and_authors(self) -> None:
        text = article_search_text(
            "ИШЕМИК ИНСУЛТ",
            "Тадқиқот натижалари",
            ["Шарофиддинов, Камолиддин"],
        )
        for needle in ("ishemik", "insult", "tadqiqot", "sharofiddinov", "kamoliddin"):
            with self.subTest(needle=needle):
                self.assertIn(needle, text)

    def test_surname_first_storage_is_findable_by_full_name(self) -> None:
        """Mualliflar familiya-birinchi saqlanadi; to'liq ism topilishi kerak."""
        text = article_search_text("Sarlavha", None, ["Sharofiddinov, Kamoliddin"])
        self.assertTrue(all(word in text for word in query_words("Kamoliddin Sharofiddinov")))

    def test_cyrillic_author_matches_latin_query(self) -> None:
        text = article_search_text("X", None, ["Сулайманова, Мария"])
        self.assertTrue(all(word in text for word in query_words("Mariya Sulaymanova")))

    def test_missing_fields_are_tolerated(self) -> None:
        self.assertEqual(article_search_text(None, None, None), "")
        self.assertEqual(article_search_text("Bor", None, []), "bor")


if __name__ == "__main__":
    unittest.main()
