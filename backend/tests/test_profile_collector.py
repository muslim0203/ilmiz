import unittest

from backend.app.services.profile_collector import (
    clean_address,
    compact,
    extract_editorial_members,
    parse_page,
    prose,
    strip_boilerplate,
)


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


class BoilerplateTest(unittest.TestCase):
    """Sahifadan yig'ilgan matndan sayt axlatini ajratish."""

    def test_cuts_at_inline_script(self) -> None:
        text = (
            "Jurnal tabiiy fanlar bo'yicha maqolalar chop etadi va yiliga to'rt marta "
            'chiqadi. $(function () { $(".header").removeClass("bg-dark"); });'
        )
        self.assertEqual(
            strip_boilerplate(text),
            "Jurnal tabiiy fanlar bo'yicha maqolalar chop etadi va yiliga to'rt marta chiqadi.",
        )

    def test_cuts_at_copyright_footer(self) -> None:
        kept = "Nashr ijtimoiy va gumanitar fanlar yo'nalishida ilmiy maqolalarni qabul qiladi."
        self.assertEqual(strip_boilerplate(kept + " Copyright © 2026 Journal"), kept)

    def test_drops_breadcrumb_prefix(self) -> None:
        self.assertEqual(strip_boilerplate("Главная / О журнале"), "О журнале")

    def test_keeps_ordinary_prose_untouched(self) -> None:
        text = "Jurnal 2013-yilda tashkil etilgan va yiliga to'rt marta nashr qilinadi."
        self.assertEqual(strip_boilerplate(text), text)

    def test_prose_rejects_javascript_warning(self) -> None:
        self.assertIsNone(prose("You need to enable JavaScript to run this app."))

    def test_prose_rejects_bare_heading(self) -> None:
        self.assertIsNone(prose("Home / About the Journal About the Journal"))

    def test_prose_rejects_navigation_dump(self) -> None:
        self.assertIsNone(
            prose(
                "Уменьшить размер шрифта Увеличить размер шрифта "
                "Клавиатурная навигация Переключить подчеркивание"
            )
        )

    def test_prose_keeps_real_description(self) -> None:
        text = (
            "Jurnal ikki asosiy yo'nalishda ilmiy maqolalar chop etadi: "
            "tabiiy fanlar va qishloq xo'jaligi fanlari."
        )
        self.assertEqual(prose(text), text)

    def test_compact_keeps_short_fields(self) -> None:
        """`prose` dan farqli, `compact` qisqa maydonlarni kesib tashlamaydi."""
        self.assertEqual(compact("Yiliga 4 marta", 200), "Yiliga 4 marta")

class CleanAddressTest(unittest.TestCase):
    """Aloqa sahifasidan manzil bilan birga begona matn ham tushib qoladi."""

    def test_keeps_address_and_drops_editorial_list(self) -> None:
        value = (
            "Hojiyev Muhsin Tojiyevich – texnika.f.d.prof.(GulDU) "
            "Mahmudov Ravshanbek Jalilovich – falsafa.f.n., prof. (GulDU) "
            "Tahririyat manzili: 120100, Guliston shahri, 4-mavze, Bosh bino, 110-xona. "
            "Tel.: (67) 2250554"
        )
        self.assertEqual(
            clean_address(value),
            "120100, Guliston shahri, 4-mavze, Bosh bino, 110-xona.",
        )

    def test_takes_the_last_address_marker(self) -> None:
        """«telegram manzili:» ham mos keladi — kerakli belgi oxirgisi."""
        value = (
            "Jurnalning telegram manzili: @innoist_uz "
            "Manzil: Toshkent shahri, Yunusobod tumani, Xidiraliyev ko‘chasi, 18-uy. "
            "Principal Contact Yaxshiboyev Rustam"
        )
        self.assertEqual(
            clean_address(value),
            "Toshkent shahri, Yunusobod tumani, Xidiraliyev ko‘chasi, 18-uy.",
        )

    def test_cuts_obfuscated_email_script(self) -> None:
        value = (
            "Amir Temur pr.1, building 2 str., Tashkent Republic of Uzbekistan "
            "Представитель редакции Tadqiqot.uz Телефон +998944040000 "
            "document.write(unescape('%3c%61'))"
        )
        self.assertEqual(
            clean_address(value),
            "Amir Temur pr.1, building 2 str., Tashkent Republic of Uzbekistan",
        )

    def test_rejects_submission_rules(self) -> None:
        value = (
            "6. Maqolaning original tilida, maqolaning oxirida mualliflar to‘g‘risida "
            "to‘liq ma’lumot (familiyasi, ismi, ilmiy darajasi va unvoni, lavozimi)."
        )
        self.assertIsNone(clean_address(value))

    def test_rejects_privacy_policy(self) -> None:
        value = (
            "1.1.2. Foydalanuvchi qurilmasida o’rnatilgan dasturiy ta’minotdan "
            "foydalangan holda saytga avtomatik ravishda uzatiladigan ma’lumotlar, "
            "shu jumladan IP-manzili va cookie-fayllari."
        )
        self.assertIsNone(clean_address(value))

    def test_rejects_bare_label(self) -> None:
        self.assertIsNone(clean_address("Bizning manzil"))
        self.assertIsNone(clean_address("ish joyi manzili (indeks bilan);"))

    def test_keeps_address_without_street_word(self) -> None:
        """Qoida ehtiyotkor: ko'cha so'zi yo'q bo'lsa ham manzil bo'lishi mumkin."""
        self.assertEqual(
            clean_address("114, Shota Rustaveli, Tashkent, Uzbekistan"),
            "114, Shota Rustaveli, Tashkent, Uzbekistan",
        )

    def test_keeps_address_without_digits(self) -> None:
        self.assertEqual(
            clean_address("г.Ташкент, М.Улугбекский район"),
            "г.Ташкент, М.Улугбекский район",
        )

    def test_keeps_bare_postal_code(self) -> None:
        """To'liq manzil emas, lekin xato ham emas — o'chirsak ma'lumot yo'qoladi."""
        self.assertEqual(clean_address("100197"), "100197")

    def test_empty_value(self) -> None:
        self.assertIsNone(clean_address(None))
        self.assertIsNone(clean_address(""))


class BalanceParensTest(unittest.TestCase):
    def test_drops_unmatched_closing(self) -> None:
        from backend.app.services.profile_collector import balance_parens

        self.assertEqual(balance_parens("+99871) 262-31-69"), "+99871 262-31-69")

if __name__ == "__main__":
    unittest.main()
