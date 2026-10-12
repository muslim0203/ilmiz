import unittest

from backend.app.services.field_classify import classify, scores

FIVE = ["Biologiya", "Filologiya", "Kimyo", "Pedagogika", "Tarix"]


class FieldClassifyTest(unittest.TestCase):
    def test_single_field_journal_keeps_its_field(self):
        self.assertEqual(classify("Har qanday sarlavha", [], None, ["Tibbiyot"]), ["Tibbiyot"])
        self.assertEqual(classify("Har qanday sarlavha", [], None, []), [])

    def test_philology_article_in_five_field_journal(self):
        """Muammoning asl misoli: filologiya maqolasiga beshta soha yopishtirilgan edi."""
        fields = classify(
            "O‘zbek tilshunosligida frazeologik birliklarning semantik tahlili",
            ["frazeologizm", "semantika", "lingvistika"],
            None,
            FIVE,
        )
        self.assertEqual(fields, ["Filologiya"])

    def test_cyrillic_and_russian_text(self):
        self.assertEqual(
            classify("Синтез и спектральный анализ новых полимеров", [], "Изучены кислотные свойства соединений.", FIVE),
            ["Kimyo"],
        )
        self.assertEqual(classify("Бошланғич синф ўқувчиларини тарбиялаш", [], None, FIVE), ["Pedagogika"])

    def test_field_outside_journal_is_never_assigned(self):
        """Fizika maqolasi Pedagogika/Psixologiya jurnalida — soha bo'sh qoladi."""
        self.assertEqual(classify("Magic numbers and nucleon shells in quantum physics", [], None, ["Pedagogika", "Psixologiya"]), [])

    def test_ambiguous_article_gets_no_field(self):
        # Pedagogika va Psixologiya teng — g'olib yo'q.
        self.assertEqual(classify("O‘quvchilar motivatsiyasi", [], None, ["Pedagogika", "Psixologiya"]), [])

    def test_phrase_stems(self):
        self.assertGreater(scores("Tashqi siyosat va xalqaro munosabatlar", [], None, ["Siyosiy fanlar"])["Siyosiy fanlar"], 0)


if __name__ == "__main__":
    unittest.main()
