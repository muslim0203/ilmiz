import unittest
from collections import Counter

from backend.app.services.article_text import (
    SplitWordFixer,
    clean_markup,
    clean_title,
    display_title,
    has_html_artifacts,
    is_shouting,
    paragraphs,
    sentence_case,
    suspect_fragments,
)
from backend.app.services.seo import TITLE_LIMIT, article_title_tag


class CleanMarkupTest(unittest.TestCase):
    def test_tags_and_entities_become_plain_paragraphs(self):
        raw = "<p>Birinchi&nbsp;<em>abzas</em>.</p><p><strong>Ikkinchi</strong> abzas.</p>"
        self.assertEqual(clean_markup(raw), "Birinchi abzas.\n\nIkkinchi abzas.")

    def test_double_escaped_entities(self):
        self.assertEqual(clean_markup("Matn&amp;nbsp;davomi &amp;amp; oxiri"), "Matn davomi & oxiri")

    def test_escaped_tags_are_removed_too(self):
        self.assertEqual(clean_markup("&lt;p&gt;Annotatsiya&lt;/p&gt;"), "Annotatsiya")

    def test_math_comparison_is_not_mistaken_for_a_tag(self):
        self.assertEqual(clean_markup("agar a<b va c>d bo‘lsa"), "agar a<b va c>d bo‘lsa")

    def test_superscript_digits_and_word_markup(self):
        self.assertEqual(clean_markup("maydon 5 m<sup>2</sup><o:p></o:p>"), "maydon 5 m²")

    def test_line_breaks_and_invisible_characters(self):
        self.assertEqual(clean_markup("bir<br/>ikki​ uch­"), "bir ikki uch")

    def test_empty_values(self):
        self.assertIsNone(clean_markup(None))
        self.assertIsNone(clean_markup("<p>&nbsp;</p>"))

    def test_title_is_single_line(self):
        self.assertEqual(clean_title("<p>Sarlavha</p><p>davomi</p>"), "Sarlavha davomi")

    def test_paragraphs_and_artifact_check(self):
        self.assertEqual(paragraphs("a\n\nb"), ["a", "b"])
        self.assertTrue(has_html_artifacts("matn <em>qism</em>"))
        self.assertTrue(has_html_artifacts("matn&nbsp;qism"))
        self.assertFalse(has_html_artifacts(clean_markup("matn&nbsp;<em>qism</em>")))


class SplitWordTest(unittest.TestCase):
    def setUp(self):
        frequency = Counter({
            "methods": 400, "met": 3, "hods": 0, "samples": 300, "sam": 2,
            "holda": 500, "hold": 4, "a": 90000, "хоразм": 80, "х": 2,
            "также": 900, "так": 70, "же": 1200, "the": 50000, "ir": 6, "their": 40,
        })
        self.fixer = SplitWordFixer(frequency)

    def test_joins_fragments_with_trailing_punctuation(self):
        text, changes = self.fixer.fix("New met hods, and sam ples.")
        self.assertEqual(text, "New methods, and samples.")
        self.assertEqual(changes, [("met hods,", "methods,"), ("sam ples.", "samples.")])

    def test_uppercase_fragments(self):
        self.assertEqual(self.fixer.fix("Х ОРАЗМ vohasi")[0], "ХОРАЗМ vohasi")

    def test_real_words_are_left_alone(self):
        for text in ("hold a meeting", "The IR spectrum", "так же как"):
            with self.subTest(text=text):
                self.assertEqual(self.fixer.fix(text), (text, []))

    def test_paragraphs_survive(self):
        self.assertEqual(self.fixer.fix("met hods\n\nsam ples")[0], "methods\n\nsamples")

    def test_from_texts_builds_frequency(self):
        fixer = SplitWordFixer.from_texts(["methods " * 30, "met hods"], min_joined=20)
        self.assertEqual(fixer.fix("met hods")[0], "methods")

    def test_suspect_fragments_report(self):
        self.assertEqual(suspect_fragments("so‘z b ayo n qilingan"), ["b ayo n"])
        self.assertEqual(suspect_fragments("bu va u da"), [])


class SentenceCaseTest(unittest.TestCase):
    def test_shouting_detection(self):
        self.assertTrue(is_shouting("O‘ZBEKISTONDA RAQAMLI IQTISODIYOT"))
        self.assertFalse(is_shouting("O‘zbekistonda raqamli iqtisodiyot"))
        self.assertFalse(is_shouting("DNK VA RNK"))  # juda qisqa

    def test_proper_nouns_acronyms_and_numbers_survive(self):
        self.assertEqual(
            sentence_case("O‘ZBEKISTON RESPUBLIKASIDA COVID-19 DAVRIDA OAK TALABLARI VA XXI ASR"),
            "O‘zbekiston Respublikasida COVID-19 davrida OAK talablari va XXI asr",
        )

    def test_cyrillic_and_known_forms(self):
        self.assertEqual(
            sentence_case("ТОШКЕНТ ШАҲРИДА PHD ДАРАЖАСИ ВА ЯИМ"),
            "Тошкент шаҳрида PhD даражаси ва ЯИМ",
        )

    def test_quoted_names_and_university_abbreviations(self):
        self.assertEqual(
            sentence_case("ВОЗМОЖНОСТИ УМК «PREPARE» В РАЗВИТИИ НАВЫКОВ"),
            "Возможности УМК «Prepare» в развитии навыков",
        )
        self.assertEqual(sentence_case("SAMDU VA O‘ZMU TALABALARI"), "SamDU va O‘zMU talabalari")

    def test_mixed_case_tokens_and_quotes_are_kept(self):
        self.assertEqual(sentence_case("«TALIM» TIZIMIDA mRNA VA IoT"), "«Talim» tizimida mRNA va IoT")

    def test_new_sentence_after_period(self):
        self.assertEqual(sentence_case("TAHLIL. YANGI YONDASHUV"), "Tahlil. Yangi yondashuv")

    def test_display_title_only_touches_shouting_titles(self):
        self.assertEqual(display_title("Normal sarlavha HTML bilan"), "Normal sarlavha HTML bilan")
        self.assertEqual(display_title("PEDAGOGIK TEXNOLOGIYALAR&nbsp;TAHLILI"), "Pedagogik texnologiyalar tahlili")


class TitleTagTest(unittest.TestCase):
    def test_journal_and_year_dropped_before_title_is_cut(self):
        self.assertEqual(article_title_tag("Qisqa sarlavha", "Jurnal", 2024), "Qisqa sarlavha — Jurnal, 2024")
        long_journal = "Juda uzun nomli ilmiy-amaliy jurnal"
        self.assertEqual(article_title_tag("O‘rtacha uzunlikdagi sarlavha", long_journal, 2024), "O‘rtacha uzunlikdagi sarlavha")
        long_title = "Bu sarlavha shunchalik uzunki u oltmish belgilik chegaraga sig‘maydi va kesiladi"
        tag = article_title_tag(long_title, "Jurnal", 2024)
        self.assertLessEqual(len(tag), TITLE_LIMIT)
        self.assertTrue(tag.endswith("…"))


if __name__ == "__main__":
    unittest.main()
