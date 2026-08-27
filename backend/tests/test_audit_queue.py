import unittest

from backend.app.services.audit_queue import endpoint_candidates, is_aggregator


class AggregatorGuardTest(unittest.TestCase):
    """Bir marta cyberleninka.ru/oai jurnal endpointi deb qabul qilinib,
    9 192 ta begona maqola bitta jurnalga yozilgan edi."""

    def test_known_aggregators_are_recognised(self) -> None:
        for url in (
            "https://cyberleninka.ru/journal/n/sovremennoe-obrazovanie-uzbekistan",
            "https://www.cyberleninka.ru/oai",
            "https://elibrary.ru/title_about.asp?id=1",
            "https://portal.issn.org/resource/ISSN/2181-1725",
            "https://core.ac.uk/search",
            "https://slib.uz/journal",
            "https://uzjournals.edu.uz/tashiit/",
        ):
            with self.subTest(url=url):
                self.assertTrue(is_aggregator(url))

    def test_journal_domains_are_not_aggregators(self) -> None:
        for url in (
            "https://maturidijournal.org/index.php/moturidiylik",
            "https://agro-inform.uz/index.php/agro-inform",
            "https://journals.nuu.uz/index.php/actanuuz",
            "https://inlibrary.uz/index.php/stomatologiya",
        ):
            with self.subTest(url=url):
                self.assertFalse(is_aggregator(url))

    def test_no_candidates_are_built_for_aggregator_sites(self) -> None:
        website = "https://cyberleninka.ru/journal/n/sovremennoe-obrazovanie-uzbekistan"
        self.assertEqual(endpoint_candidates(website), [])

    def test_normal_site_still_produces_candidates(self) -> None:
        candidates = endpoint_candidates("https://maturidijournal.org/index.php/moturidiylik")
        self.assertIn("https://maturidijournal.org/index.php/moturidiylik/oai", candidates)


if __name__ == "__main__":
    unittest.main()
