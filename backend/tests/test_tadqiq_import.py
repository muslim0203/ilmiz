import os
import tempfile
import unittest
from datetime import datetime, timezone

database_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
database_file.close()
os.environ.setdefault("DATABASE_URL", f"sqlite:///{database_file.name}")

from backend.app.db import SessionLocal, engine, init_db  # noqa: E402
from backend.app.models import Journal, JournalProfileField  # noqa: E402
from backend.app.services.tadqiq_import import (  # noqa: E402
    MATCH_THRESHOLD,
    MatchResult,
    apply_match,
    containment,
    name_tokens,
    names_agree,
    normalize_name,
    split_languages,
    parse_detail,
)

DETAIL_HTML = """
<html><head>
<script type="application/ld+json">{"@context":"https://schema.org","@type":"WebSite","name":"Tadqiq.uz"}</script>
<script type="application/ld+json">{"@context":"https://schema.org","@type":"Periodical",
 "name":"Agro ILM (Oʻzbekiston qishloq xoʻjaligi jurnali ilmiy ilovasi)",
 "alternateName":"Agro ILM (Oʻzbekiston qishloq xoʻjaligi журнали илмий иловаси)",
 "issn":"2091-5616",
 "publisher":{"@type":"Organization","name":"Qishloq va suv xoʻjaligi vazirligi"},
 "locationCreated":{"@type":"Place","name":"Toshkent"},
 "url":"https://tadqiq.uz/mahalliy-oak-jurnallar/agro-ilm",
 "sameAs":"https://qxjurnal.uz/index.php/ai"}</script>
</head><body>
<a href="tel:+998712421354">+998712421354</a>
<p><span>Taqriz turi<!-- -->:</span> <!-- -->Koʻr-koʻrona taqriz</p>
<p><span>Bosh muharrir<!-- -->:</span> <!-- -->Tohir Doliyev</p>
<div><span>Indekslangan<!-- -->:</span><span class="b">Crossref</span><span class="b">OpenAlex</span></div>
<dl>
<dt>ISSN</dt><dd>2091-5616</dd>
<dt>e-ISSN</dt><dd>2181-189X</dd>
<dt>Soʻnggi son</dt><dd>2025 · 1-son · 5-jild</dd>
<dt>Shahar</dt><dd><a href="/x">Toshkent</a></dd>
<dt>Til</dt><dd>Oʻzbek, Rus, Ingliz</dd>
<dt>Chiqish davriyligi</dt><dd>Yiliga 6 marta</dd>
<dt>Asos solingan yil</dt><dd>2007</dd>
</dl>
<section><h2>Jurnal haqida</h2><p>Qishloq xoʻjaligi va agrotexnologiyalar boʻyicha ilmiy maqolalar chop etadi.</p></section>
</body></html>
"""

SPARSE_HTML = """
<html><head>
<script type="application/ld+json">{"@context":"https://schema.org","@type":"Periodical",
 "name":"Chorvachilik va naslchilik ishi","issn":"","publisher":{"@type":"Organization","name":"X"}}</script>
</head><body>
<p><span>Taqriz turi<!-- -->:</span> <span class="i">Maʼlumot topilmadi</span></p>
<section><h2>Jurnal haqida</h2><p>Chorvachilik va naslchilik ishi — Oʻzbekiston Oliy Attestatsiya Komissiyasi (OAK) tomonidan tasdiqlangan ilmiy jurnal. Nashriyot: X.</p></section>
<dl><dt>ISSN</dt><dd>—</dd><dt>Asos solingan yil</dt><dd>—</dd>
<dt>Til</dt><dd>Maʼlumot topilmadi</dd><dt>Chiqish davriyligi</dt><dd>Maʼlumot topilmadi</dd></dl>
</body></html>
"""


class ParseDetailTest(unittest.TestCase):
    def test_reads_json_ld_and_sidebar(self) -> None:
        record = parse_detail("agro-ilm", DETAIL_HTML)
        self.assertEqual(record.issn, "2091-5616")
        self.assertEqual(record.website, "https://qxjurnal.uz/index.php/ai")
        self.assertEqual(record.city, "Toshkent")
        self.assertEqual(record.publisher, "Qishloq va suv xoʻjaligi vazirligi")
        self.assertEqual(record.language, "Oʻzbek, Rus, Ingliz")
        self.assertEqual(record.frequency, "Yiliga 6 marta")
        self.assertEqual(record.founded, 2007)
        self.assertEqual(record.phone, "+998712421354")
        self.assertEqual(record.editor_in_chief, "Tohir Doliyev")
        self.assertEqual(record.peer_review, "Koʻr-koʻrona taqriz")
        self.assertEqual(record.indexed_in, ["Crossref", "OpenAlex"])
        self.assertEqual(record.eissn, "2181-189X")
        self.assertEqual(record.latest_issue, "2025 · 1-son · 5-jild")
        self.assertTrue(record.description.startswith("Qishloq xoʻjaligi"))

    def test_alternate_name_is_kept_for_matching(self) -> None:
        """Kirillcha muqobil nom bizdagi nomga mos kelishi mumkin."""
        record = parse_detail("agro-ilm", DETAIL_HTML)
        self.assertIn("журнали", record.alternate_name)

    def test_placeholder_values_are_not_stored(self) -> None:
        record = parse_detail("chorvachilik", SPARSE_HTML)
        self.assertEqual(record.name, "Chorvachilik va naslchilik ishi")
        self.assertEqual(record.issn, "")
        self.assertIsNone(record.founded)
        self.assertEqual(record.peer_review, "")
        # Sayt bo'sh maydonni "Maʼlumot topilmadi" deb yozadi — u qiymat emas.
        self.assertEqual(record.language, "")
        self.assertEqual(record.frequency, "")
        self.assertEqual(record.eissn, "")
        # Sayt maʼlumot bo'lmaganda shablon tavsif yozadi — u tavsif emas.
        self.assertEqual(record.description, "")

    def test_invalid_issn_is_rejected(self) -> None:
        html_text = DETAIL_HTML.replace('"issn":"2091-5616"', '"issn":"yo‘q"').replace(
            "<dt>ISSN</dt><dd>2091-5616</dd>", "<dt>ISSN</dt><dd>yo‘q</dd>"
        )
        self.assertEqual(parse_detail("x", html_text).issn, "")


class NameMatchingTest(unittest.TestCase):
    def test_cyrillic_and_latin_normalize_to_the_same_string(self) -> None:
        self.assertEqual(
            normalize_name("Ўзбекистон замини"),
            normalize_name("Oʻzbekiston zamini"),
        )

    def test_apostrophe_variants_are_equivalent(self) -> None:
        variants = ["Oʻzbekiston", "O'zbekiston", "O‘zbekiston", "O’zbekiston", "Ozbekiston"]
        self.assertEqual(len({normalize_name(item) for item in variants}), 1)

    def test_containment_matches_short_name_inside_long_one(self) -> None:
        """Bizdagi qisqa kirillcha nom ularning uzun nomiga to'liq kiradi."""
        short = name_tokens("Ўзбекистон замини")
        long = name_tokens("Oʻzbekiston zamini ilmiy-amaliy va innovatsion jurnali")
        self.assertGreaterEqual(containment(short, long), MATCH_THRESHOLD)

    def test_unrelated_journals_stay_below_threshold(self) -> None:
        """0.5 atrofidagi juftliklar noto'g'ri edi — chegara ularni kesishi kerak."""
        pairs = [
            ("Uzbek Biological Journal", "Oʻzbekiston qonunchiligi tahlili"),
            ("Pharmaceutical Bulletin of Uzbekistan", "Uzbekistan Journal of Polymers"),
            ("Zhamiyat va boshqaruv", "Kimyoviy texnologiya. Nazorat va boshqaruv"),
        ]
        for left, right in pairs:
            with self.subTest(pair=left):
                self.assertLess(containment(name_tokens(left), name_tokens(right)), MATCH_THRESHOLD)

    def test_stopwords_do_not_create_false_matches(self) -> None:
        """"Ilmiy jurnal" kabi so'zlar deyarli hamma nomda bor."""
        self.assertEqual(containment(name_tokens("Ilmiy jurnal"), name_tokens("Xalqaro ilmiy jurnal")), 0.0)

    def test_short_generic_name_does_not_swallow_long_one(self) -> None:
        """Bazadagi bir so'zli nomlar ("Moliya", "Psixologiya") eng xavfli holat.

        Ular boshqa jurnalning uzun nomida uchrab qolsa, containment 1.00 chiqib
        butunlay boshqa jurnalga bog'lanardi.
        """
        pairs = [
            ("Moliya", "Aktuar moliya va buxgalteriya hisobi ilmiy jurnali"),
            ("Psixologiya", "Buxoro psixologiya va xorijiy tillar instituti ilmiy axborotnomasi"),
            ("Pedagogika", "Filologiya va pedagogika elektron jurnali"),
            ("Toshkent davlat texnika universiteti xabarlari", "Ilmiy-texnika jurnali"),
        ]
        for ours, theirs in pairs:
            with self.subTest(pair=ours):
                self.assertLess(containment(name_tokens(theirs), name_tokens(ours)), MATCH_THRESHOLD)
                self.assertLess(containment(name_tokens(ours), name_tokens(theirs)), MATCH_THRESHOLD)

    def test_genuine_transliteration_pairs_still_match(self) -> None:
        pairs = [
            ("Фарғона методика мактаби", "Fargʻona metodika maktabi ilmiy-jurnali"),
            ("Камолиддин Беҳзод номидаги МРДИ Ахборотномаси",
             "Kamoliddin Behzod nomidagi Milliy rassomlik va dizayn instituti Axborotnomasi"),
            ("Ўзбекистон Республикаси Бош прокуратура Академияси Ахборотномаси",
             "Oʻzbekiston Respublikasi Bosh prokuraturasi Akademiyasi Axborotnomasi"),
            ("Agrobiznes, fan va texnologiyalar",
             "Agrobiznes, fan va texnologiyalar ilmiy-amaliy elektron jurnali"),
        ]
        for ours, theirs in pairs:
            with self.subTest(pair=ours[:30]):
                self.assertGreaterEqual(containment(name_tokens(theirs), name_tokens(ours)), MATCH_THRESHOLD)

    def test_empty_token_set_scores_zero(self) -> None:
        self.assertEqual(containment(set(), name_tokens("Agro ILM")), 0.0)


class IssnCorroborationTest(unittest.TestCase):
    """ISSN faqat bizdagi qiymat to'g'ri bo'lsagina ishonchli kalit.

    Seed'dagi demo jurnallarda ISSN qo'lda yozilgan; bir nechtasi boshqa
    jurnalniki bo'lib chiqdi va ISSN moslashtirish butunlay boshqa jurnalga
    bog'lab qo'ygan edi.
    """

    def test_rejects_issn_match_when_names_are_unrelated(self) -> None:
        cases = [
            (["Inter education & global study ilmiy-nazariy va metodik jurnali"], "Acta CAMU"),
            (["Lingvospektr"], "Infolib"),
            (["Ilm sarchashmalari"], "Zamonaviy fan, ta'lim va tarbiyaning dolzarb muammolari"),
            (["Markaziy Osiyo endokrinologik jurnali"], "Bolalar milliy tibbiyot markazining axborotnomasi"),
        ]
        for candidates, our_name in cases:
            with self.subTest(pair=candidates[0][:30]):
                self.assertFalse(names_agree(candidates, our_name))

    def test_accepts_single_token_name_inside_longer_one(self) -> None:
        """"Nordik" / "Komparativistika" kabi qisqa nomlar to'g'ri mos keladi."""
        self.assertTrue(names_agree(["Nordik ilmiy-amaliy elektron jurnali"], "Нордик"))
        self.assertTrue(names_agree(["Komparativistika (Comparative Studies) ilmiy-elektron jurnali"], "Komparativistika"))

    def test_accepts_translated_title_via_alternate_name(self) -> None:
        """Inglizcha sarlavha kirillcha nomimizga mos kelmaydi, muqobil nom mos keladi."""
        candidates = ["Chemistry of Natural Compounds", "Химия природных соединений"]
        self.assertTrue(names_agree(candidates, "Химия природных соединений"))
        self.assertFalse(names_agree(["Chemistry of Natural Compounds"], "Химия природных соединений"))


class ApplyMatchTest(unittest.TestCase):
    """tadqiq.uz da bir jurnal ikki slug bilan uchraydi, bazamizda ham
    dublikatlar bor — bitta jurnalga ikki marta yozish yiqilmasligi kerak."""

    @classmethod
    def setUpClass(cls) -> None:
        init_db()

    @classmethod
    def tearDownClass(cls) -> None:
        engine.dispose()
        for suffix in ("", "-wal", "-shm"):
            try:
                os.unlink(database_file.name + suffix)
            except OSError:
                pass

    def setUp(self) -> None:
        self.db = SessionLocal()
        self.journal = Journal(
            slug=f"apply-{id(self)}",
            name="Agro ILM",
            short_name="AI",
            publisher="X",
            city="Toshkent",
            fields=["Qishloq xo‘jaligi"],
        )
        self.db.add(self.journal)
        self.db.commit()

    def tearDown(self) -> None:
        self.db.close()

    def result_for(self, slug: str) -> MatchResult:
        record = parse_detail(slug, DETAIL_HTML)
        return MatchResult(record, self.journal.id, self.journal.name, "aniq-nom", 1.0)

    def test_same_journal_twice_in_one_transaction(self) -> None:
        cache: dict[tuple[int, str], JournalProfileField] = {}
        now = datetime.now(timezone.utc)
        apply_match(self.db, self.result_for("agro-ilm"), now=now, provenance_cache=cache)
        apply_match(self.db, self.result_for("agro-ilm-nusxa"), now=now, provenance_cache=cache)
        self.db.commit()

        rows = self.db.query(JournalProfileField).filter(
            JournalProfileField.journal_id == self.journal.id,
            JournalProfileField.field_name == "tadqiq:issn",
        ).all()
        self.assertEqual(len(rows), 1)

    def test_existing_values_are_not_overwritten(self) -> None:
        self.journal.issn = "1111-2222"
        self.journal.website = "https://mavjud.example"
        self.db.commit()

        applied = apply_match(self.db, self.result_for("agro-ilm"), now=datetime.now(timezone.utc))
        self.db.commit()

        self.assertEqual(self.journal.issn, "1111-2222")
        self.assertEqual(self.journal.website, "https://mavjud.example")
        self.assertNotIn("issn", applied)
        self.assertNotIn("website", applied)
        # Bo'sh maydon esa to'ldirilishi kerak.
        self.assertEqual(self.journal.founded, 2007)

    def test_languages_are_split_into_a_list(self) -> None:
        """Sayt tillarni bitta satrda beradi; ro'yxat bo'lib saqlanishi kerak."""
        self.assertEqual(split_languages("Oʻzbek, Rus, Ingliz"), ["Oʻzbek", "Rus", "Ingliz"])
        self.assertEqual(split_languages("Ingliz"), ["Ingliz"])
        self.assertEqual(split_languages("Oʻzbek; Rus / Ingliz"), ["Oʻzbek", "Rus", "Ingliz"])
        self.assertEqual(split_languages(""), [])

    def test_profile_languages_are_stored_as_list(self) -> None:
        apply_match(self.db, self.result_for("agro-ilm"), now=datetime.now(timezone.utc))
        self.db.commit()
        self.assertEqual(self.journal.profile.submission_languages, ["Oʻzbek", "Rus", "Ingliz"])

    def test_placeholder_description_is_replaced(self) -> None:
        """OAK importimiz har bir jurnalga bir xil shablon matn yozgan (487/493)."""
        self.journal.description = "OAK rasmiy elektron reestridan import qilingan jurnal."
        self.db.commit()
        apply_match(self.db, self.result_for("agro-ilm"), now=datetime.now(timezone.utc))
        self.db.commit()
        self.assertTrue(self.journal.description.startswith("Qishloq xoʻjaligi"))

    def test_real_description_is_not_replaced(self) -> None:
        self.journal.description = "Tahririyat yozgan haqiqiy tavsif."
        self.db.commit()
        apply_match(self.db, self.result_for("agro-ilm"), now=datetime.now(timezone.utc))
        self.db.commit()
        self.assertEqual(self.journal.description, "Tahririyat yozgan haqiqiy tavsif.")

    def test_dead_site_is_replaced_only_when_allowed(self) -> None:
        """maturidijournal.uz o'lgan, haqiqiysi .org — lekin faqat so'ralganda."""
        self.journal.website = "https://eski-domen.example/jurnal"
        self.db.commit()

        apply_match(self.db, self.result_for("agro-ilm"), now=datetime.now(timezone.utc))
        self.db.commit()
        self.assertEqual(self.journal.website, "https://eski-domen.example/jurnal")

        apply_match(
            self.db, self.result_for("agro-ilm"),
            now=datetime.now(timezone.utc), replace_dead_site=True,
        )
        self.db.commit()
        self.assertEqual(self.journal.website, "https://qxjurnal.uz/index.php/ai")

    def test_same_host_is_never_replaced(self) -> None:
        """Faqat yo'l qismi farq qilsa, o'zgartirmaymiz."""
        self.journal.website = "https://qxjurnal.uz/boshqa-yol"
        self.db.commit()
        apply_match(
            self.db, self.result_for("agro-ilm"),
            now=datetime.now(timezone.utc), replace_dead_site=True,
        )
        self.db.commit()
        self.assertEqual(self.journal.website, "https://qxjurnal.uz/boshqa-yol")

    def test_provenance_is_recorded_with_source_url(self) -> None:
        apply_match(self.db, self.result_for("agro-ilm"), now=datetime.now(timezone.utc))
        self.db.commit()

        row = self.db.query(JournalProfileField).filter(
            JournalProfileField.journal_id == self.journal.id,
            JournalProfileField.field_name == "tadqiq:website",
        ).one()
        self.assertEqual(row.source_url, "https://tadqiq.uz/mahalliy-oak-jurnallar/agro-ilm")
        self.assertEqual(row.verification_status, "external")


if __name__ == "__main__":
    unittest.main()
