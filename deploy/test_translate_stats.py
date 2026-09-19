import json
import unittest

from deploy.translate_stats import translate

# GoAccess hisobotining tuzilishi: yorliqlar ichma-ich JSON sozlamada.
REPORT = (
    '{"panels":{"visitors":{"head": "Unique visitors per day",'
    '"desc": "Hits having the same IP, date and agent are a unique visit.",'
    '"items":[{"label": "Hits"},{"label": "Tx. Amount"}]},'
    '"yangi":{"head": "Brand New Panel","desc": "","label": "Unknown Column"}}}'
)


class TranslateTests(unittest.TestCase):
    def test_known_labels_become_uzbek(self) -> None:
        result = translate(REPORT)
        self.assertIn('"head": "Kunlik tashrifchilar"', result)
        self.assertIn("Uzatilgan hajm", result)
        self.assertIn("bitta tashrif deb hisoblanadi", result)

    def test_unknown_strings_are_left_alone(self) -> None:
        """GoAccess yangilanib, yangi panel qo'shsa hisobot buzilmasin."""
        result = translate(REPORT)
        self.assertIn('"head": "Brand New Panel"', result)
        self.assertIn('"label": "Unknown Column"', result)

    def test_crawlers_only_suffix_is_translated(self) -> None:
        """`--crawlers-only` sarlavhaga "- Including spiders" qo'shadi."""
        source = '{"head": "Unique visitors per day - Including spiders"}'
        self.assertEqual(
            json.loads(translate(source))["head"], "Kunlik tashrifchilar (robotlar bilan)")

    def test_result_is_still_valid_json(self) -> None:
        json.loads(translate(REPORT))

    def test_escaped_quotes_are_kept(self) -> None:
        source = '{"head": "Not Found URLs (404s)", "desc": "matn \\"ichki\\" qo\'shtirnoq bilan"}'
        result = translate(source)
        self.assertIn('"head": "Topilmagan manzillar (404)"', result)
        self.assertEqual(json.loads(result)["desc"], 'matn "ichki" qo\'shtirnoq bilan')


if __name__ == "__main__":
    unittest.main()
