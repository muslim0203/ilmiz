import unittest

from backend.app.services.profile_collector import extract_editorial_members, parse_page


class ProfileCollectorTest(unittest.TestCase):
    def test_parses_ojs_main_content_and_contact(self) -> None:
        page = parse_page(
            "https://journal.example/about/contact",
            """
            <html><head><title>Contact</title></head><body>
              <div class="pkp_structure_main" role="main">
                <h1>Aloqa</h1>
                <div class="address">Toshkent, Universitet ko'chasi 4</div>
                <p>Bosh muharrir: Ali Valiyev; Universitet</p>
                <a href="mailto:journal@example.uz">Email</a>
              </div>
            </body></html>
            """,
        )
        self.assertIn("Toshkent", page.main_text)
        self.assertEqual(page.address, "Toshkent, Universitet ko'chasi 4")
        self.assertEqual(page.emails, ["journal@example.uz"])

    def test_extracts_editor_role_and_name(self) -> None:
        page = parse_page(
            "https://journal.example/editorial",
            '<main><h1>Tahririyat</h1><p>Главный редактор Рустамов Сирожиддин Ташниязович.</p></main>',
        )
        members = extract_editorial_members(page)
        self.assertEqual(members[0]["name"], "Рустамов Сирожиддин Ташниязович")
        self.assertEqual(members[0]["role"].lower(), "главный редактор")


if __name__ == "__main__":
    unittest.main()
