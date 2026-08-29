import unittest

from backend.app.services.authorship import EXACT, PARTIAL, _matches, name_words


class NameWordsTest(unittest.TestCase):
    def test_splits_on_punctuation(self) -> None:
        """Mualliflar "Familiya, Ism" shaklida saqlanadi."""
        self.assertEqual(name_words("Sharofiddinov, Kamoliddin"), ["sharofiddinov", "kamoliddin"])

    def test_initials_lose_the_dot(self) -> None:
        self.assertEqual(name_words("Sharofiddinov K."), ["sharofiddinov", "k"])

    def test_cyrillic_becomes_latin(self) -> None:
        self.assertEqual(name_words("Шарофиддинов Камолиддин"), ["sharofiddinov", "kamoliddin"])

    def test_apostrophes_are_dropped(self) -> None:
        self.assertEqual(name_words("Do‘stmuhammad Ulug‘bek"), ["dostmuhammad", "ulugbek"])

    def test_empty_name(self) -> None:
        self.assertEqual(name_words(None), [])
        self.assertEqual(name_words("   "), [])


class MatchTest(unittest.TestCase):
    """Moslik tartibga bog'liq bo'lmasligi kerak."""

    def setUp(self) -> None:
        self.user = name_words("Kamoliddin Sharofiddinov")

    def test_reversed_order_matches(self) -> None:
        self.assertEqual(_matches(self.user, name_words("Sharofiddinov, Kamoliddin")), EXACT)

    def test_same_order_matches(self) -> None:
        self.assertEqual(_matches(self.user, name_words("Kamoliddin Sharofiddinov")), EXACT)

    def test_cyrillic_author_matches_latin_user(self) -> None:
        self.assertEqual(_matches(self.user, name_words("Шарофиддинов Камолиддин")), EXACT)

    def test_middle_name_in_author_is_allowed(self) -> None:
        """Muallifda ortiqcha so'z bo'lishi mumkin — otasining ismi."""
        self.assertEqual(
            _matches(self.user, name_words("Sharofiddinov Kamoliddin Anvarovich")), EXACT
        )

    def test_initial_only_is_partial(self) -> None:
        """"Sharofiddinov K." Kamoliddin ham, Kamola ham bo'lishi mumkin."""
        self.assertEqual(_matches(self.user, name_words("Sharofiddinov K.")), PARTIAL)

    def test_different_surname_does_not_match(self) -> None:
        self.assertIsNone(_matches(self.user, name_words("Karimov, Kamoliddin")))

    def test_missing_given_name_does_not_match(self) -> None:
        self.assertIsNone(_matches(self.user, name_words("Sharofiddinov")))

    def test_wrong_initial_does_not_match(self) -> None:
        self.assertIsNone(_matches(self.user, name_words("Sharofiddinov A.")))

    def test_one_word_cannot_be_consumed_twice(self) -> None:
        """Ikkala so'z bitta muallif so'ziga mos kelib qolmasin."""
        self.assertIsNone(_matches(name_words("Anvar Anvarov"), name_words("Anvarov")))

    def test_partial_needs_every_word_paired(self) -> None:
        self.assertIsNone(_matches(name_words("Kamoliddin Sharofiddinov"), name_words("K. A.")))


if __name__ == "__main__":
    unittest.main()
