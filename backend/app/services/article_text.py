"""Maqola matnini tozalash: annotatsiyadagi HTML, bo'lingan so'zlar, BOSH HARFLI sarlavha.

OAI-PMH `dc:description` ko'p jurnallarda OJS muharriridan qanday kiritilgan
bo'lsa shunday keladi: `<p>`, `<em>`, `&nbsp;`, ba'zan ikki marta ekranlangan
(`&amp;nbsp;`). Ular sahifada matn sifatida ko'rinib turardi — bazada 5 751
annotatsiyada teg, 7 351 tasida entity bor edi.

PDF'dan ko'chirilgan matnda so'zlar bo'linib qoladi ("met hods", "Х ОРАЗМ").
Ularni lug'atsiz to'g'rilab bo'lmaydi, shuning uchun `SplitWordFixer` lug'atni
korpusning o'zidan oladi: birlashmasi ko'p uchraydigan, bo'laklari esa kam
uchraydigan juftlar tuzatiladi.
"""
from __future__ import annotations

import html
import re
from collections import Counter
from collections.abc import Iterable

# ------------------------------------------------------------------ HTML

# Faqat haqiqiy HTML teglar. Umumiy `<[^>]+>` "a<b va c>d" kabi formulalarni
# ham yeb qo'yardi.
_TAG_NAMES = (
    "p|br|em|strong|b|i|u|s|sup|sub|span|div|a|li|ul|ol|font|h[1-6]|table|tr|td|th|"
    "tbody|thead|small|big|blockquote|hr|img|mark|abbr|cite|code|pre|center|section|"
    "article|header|footer|figure|figcaption|strike|del|ins|wbr|nobr|label|o:p|st1:\\w+"
)
# Atribut bo'lsa unda `=` bor: `<p class="x">`. "a<b va c>d" dagi `<b va c>`
# teg emas — u formula.
_ATTRS = r"(?:\s+[^<>]*=[^<>]*)?\s*"
_COMMENT = re.compile(r"<!--.*?-->", re.S)
_BLOCK_BREAK = re.compile(rf"</?(?:p|div|li|ul|ol|h[1-6]|blockquote|table|tr|section|article){_ATTRS}>", re.I)
_LINE_BREAK = re.compile(r"<br\s*/?>", re.I)
_SUP_DIGITS = re.compile(r"<sup>\s*([0-9+\-]{1,4})\s*</sup>", re.I)
_SUB_DIGITS = re.compile(r"<sub>\s*([0-9]{1,4})\s*</sub>", re.I)
_TAG = re.compile(rf"</?(?:{_TAG_NAMES}){_ATTRS}/?>|</?\w+:\w+{_ATTRS}/?>", re.I)
_INVISIBLE = dict.fromkeys(map(ord, "​‌‍⁠﻿­"))
_SUPERSCRIPT = str.maketrans("0123456789+-", "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻")
_SUBSCRIPT = str.maketrans("0123456789", "₀₁₂₃₄₅₆₇₈₉")
_PARAGRAPH = "\n\n"

# Tozalashdan keyin ham qolgan teg yoki entity — "HTML-xatosiz" mezoni uchun.
HTML_ARTIFACT = re.compile(rf"</?(?:{_TAG_NAMES}){_ATTRS}/?>|&(?:[a-z]{{2,8}}|#\d{{2,5}}|#x[0-9a-f]{{2,4}});", re.I)


def _unescape(value: str) -> str:
    # `&amp;nbsp;` → `&nbsp;` → bo'shliq: ikki qavat ekranlash ham uchraydi.
    for _ in range(2):
        unescaped = html.unescape(value)
        if unescaped == value:
            break
        value = unescaped
    return value


def clean_markup(value: str | None) -> str | None:
    """HTML'ni toza matnga aylantiradi; abzaslar bo'sh qator bilan ajraladi.

    Natija matn — render qilganda baribir ekranlanadi, shuning uchun bu yerda
    xavfsiz HTML saqlab qolishga urinilmaydi.
    """
    if not value:
        return None
    text = _unescape(value)
    text = _COMMENT.sub(" ", text)
    text = _SUP_DIGITS.sub(lambda m: m.group(1).translate(_SUPERSCRIPT), text)
    text = _SUB_DIGITS.sub(lambda m: m.group(1).translate(_SUBSCRIPT), text)
    text = _LINE_BREAK.sub("\n", text)
    text = _BLOCK_BREAK.sub(_PARAGRAPH, text)
    text = _TAG.sub("", text)
    # Teglar ichida ekranlangan entity'lar bo'lishi mumkin edi.
    text = _unescape(text).replace("\xa0", " ").translate(_INVISIBLE)
    paragraphs = []
    for block in re.split(r"\n\s*\n", text):
        line = re.sub(r"\s+", " ", block).strip()
        if line:
            paragraphs.append(line)
    return _PARAGRAPH.join(paragraphs) or None


def clean_title(value: str | None) -> str:
    """Sarlavhada abzas bo'lmaydi — bitta qator."""
    cleaned = clean_markup(value) or ""
    return re.sub(r"\s+", " ", cleaned).strip()


def paragraphs(value: str | None) -> list[str]:
    return [part for part in (value or "").split(_PARAGRAPH) if part.strip()]


def has_html_artifacts(value: str | None) -> bool:
    return bool(value and HTML_ARTIFACT.search(value))


# ------------------------------------------------------- bo'lingan so'zlar

_WORD = re.compile(r"[^\W\d_]+", re.U)
_APOSTROPHE_WORD = re.compile(r"[^\W\d_][^\W\d_ʻʼ'‘’`]*", re.U)


def _case_shape(part: str) -> str:
    if part.isupper():
        return "upper"
    if part.islower():
        return "lower"
    if part[:1].isupper() and part[1:].islower():
        return "title"
    return "mixed"


def _consistent_case(parts: list[str]) -> bool:
    """"met hods", "Х ОРАЗМ", "The oretical" — bitta so'z bo'laklari.

    "The IR", "in NER" esa ikki alohida so'z: registr almashgan joyda so'z
    chegarasi bor.
    """
    shapes = [_case_shape(part) for part in parts]
    if "mixed" in shapes:
        return False
    if all(shape == "upper" for shape in shapes) or all(shape == "lower" for shape in shapes):
        return True
    # Birinchisi bosh harfli, qolgani kichik: "The oretical", "B ahauddin".
    return shapes[0] in ("title", "upper") and all(shape == "lower" for shape in shapes[1:])


class SplitWordFixer:
    """Korpus chastotasi bo'yicha bo'lingan so'zlarni birlashtiradi.

    Juftlik (yoki uchlik) tuzatiladi, agar:
    - birlashmasi korpusda kamida `min_joined` marta alohida so'z sifatida uchrasa;
    - eng qisqa bo'lak `max_fragment` harfdan oshmasa;
    - qisqa bo'lak birlashmaga nisbatan kam uchrasa (`rare_ratio`) — "hold a"
      dagi "a" juda ko'p uchraydi, demak u haqiqiy so'z va tegilmaydi;
    - registr bir xil bo'lsa (`_consistent_case`);
    - bo'laklarning hammasi ham ko'p uchraydigan so'z bo'lmasa ("так же").
    """

    def __init__(
        self,
        frequency: Counter[str],
        *,
        min_joined: int = 20,
        max_fragment: int = 3,
        rare_ratio: float = 0.05,
        common_floor: int = 50,
    ):
        self.frequency = frequency
        self.min_joined = min_joined
        self.max_fragment = max_fragment
        self.rare_ratio = rare_ratio
        # Har bir bo'lak o'zi ham ko'p uchraydigan so'z bo'lsa ("так же") —
        # bu ikki so'z, birlashtirilmaydi.
        self.common_floor = common_floor

    @classmethod
    def from_texts(cls, texts: Iterable[str | None], **options) -> "SplitWordFixer":
        frequency: Counter[str] = Counter()
        for text in texts:
            if text:
                frequency.update(word.casefold() for word in _APOSTROPHE_WORD.findall(text))
        return cls(frequency, **options)

    @staticmethod
    def _split_edges(tokens: list[str]) -> tuple[str, list[str], str] | None:
        """Birinchi bo'lak oldidagi va oxirgisi ortidagi tinish belgisini ajratadi.

        "met hods," → ("", ["met", "hods"], ","). Ichki bo'lakda belgi bo'lsa —
        bu ikki alohida so'z.
        """
        lead, first, first_trail = _EDGE.match(tokens[0]).groups()
        last_lead, last, trail = _EDGE.match(tokens[-1]).groups()
        if first_trail or last_lead:
            return None
        return lead, [first, *tokens[1:-1], last], trail

    def _joinable(self, parts: list[str]) -> bool:
        if not all(_WORD.fullmatch(part) for part in parts):
            return False
        if min(len(part) for part in parts) > self.max_fragment or not _consistent_case(parts):
            return False
        joined = self.frequency["".join(parts).casefold()]
        if joined < self.min_joined:
            return False
        if all(self.frequency[part.casefold()] >= self.common_floor for part in parts):
            return False
        shortest = min(parts, key=len)
        return self.frequency[shortest.casefold()] < joined * self.rare_ratio

    def fix(self, text: str | None) -> tuple[str | None, list[tuple[str, str]]]:
        """Tuzatilgan matn va `(asl, tuzatilgan)` juftlari ro'yxati."""
        if not text:
            return text, []
        changes: list[tuple[str, str]] = []
        out_blocks = []
        for block in text.split(_PARAGRAPH):
            tokens = block.split(" ")
            result: list[str] = []
            i = 0
            while i < len(tokens):
                for size in (3, 2):
                    window = tokens[i:i + size]
                    edges = self._split_edges(window) if len(window) == size else None
                    if edges and self._joinable(edges[1]):
                        lead, parts, trail = edges
                        joined = lead + "".join(parts) + trail
                        changes.append((" ".join(window), joined))
                        result.append(joined)
                        i += size
                        break
                else:
                    result.append(tokens[i])
                    i += 1
            out_blocks.append(" ".join(result))
        return _PARAGRAPH.join(out_blocks), changes


# Tuzatilmay qolgan, lekin bo'lingan bo'lishi ehtimoli katta joy: ketma-ket
# uch va undan ortiq 1–3 harfli bo'lak, ulardan kamida bittasi yakka harf
# ("b ayo n"). Avtomatik tuzatilmaydi — qo'lda ko'rish uchun ro'yxatga yoziladi.
SUSPECT_FRAGMENTS = re.compile(r"(?<!\S)(?:[^\W\d_]{1,3} ){2,}[^\W\d_]{1,3}(?!\S)", re.U)
_COMMON_SHORT = frozenset(
    """a an i o u e va da de di bu bir biz siz ul men sen in on at to of is it as or by be we no so do if my
    the and for are was not but has had can its our all who how new two one may per via
    и в с к о у а на по за из от до не но же ли бы то как так что при для это все его они ва ҳам бу бир""".split()
)


def suspect_fragments(text: str | None) -> list[str]:
    found = []
    for match in SUSPECT_FRAGMENTS.finditer(text or ""):
        pieces = match.group(0).split()
        uncommon = [piece for piece in pieces if piece.casefold() not in _COMMON_SHORT]
        if len(uncommon) >= 2 and any(len(piece) == 1 for piece in uncommon):
            found.append(match.group(0))
    return found


# ------------------------------------------------------ sarlavha registri

# Qisqartmalar BOSH HARFLI sarlavhada ham shundayligicha qolishi kerak.
# Kalit — katta harfdagi shakl, qiymat — to'g'ri yozilishi.
_ACRONYM_FORMS = {
    "PHD": "PhD", "DSC": "DSc", "YAIM": "YaIM", "IOT": "IoT", "O'ZR": "O‘zR", "O‘ZR": "O‘zR",
    "ЎЗР": "ЎзР", "PH": "pH", "MRNA": "mRNA", "MCHJ": "MChJ",
    "SAMDU": "SamDU", "САМДУ": "СамДУ", "NAMDU": "NamDU", "НАМДУ": "НамДУ", "FARDU": "FarDU",
    "ФАРДУ": "ФарДУ", "BUXDU": "BuxDU", "БУХДУ": "БухДУ", "O‘ZMU": "O‘zMU", "O'ZMU": "O‘zMU",
    "ЎЗМУ": "ЎзМУ", "O‘ZFA": "O‘zFA", "O'ZFA": "O‘zFA", "ЎЗФА": "ЎзФА",
}
_ACRONYMS = frozenset(
    """OAK ОАК ВАК AQSH АҚШ США BMT БМТ ООН MDH МДҲ СНГ DNK ДНК RNK РНК DNA RNA IT AT AKT АКТ
    ИКТ ICT AI ИИ GDP ВВП ЯИМ NATO НАТО UNESCO ЮНЕСКО YUNESKO HIV ВИЧ OITS ОИТС СПИД COVID SARS
    STEM PISA TIMSS PIRLS CEFR IELTS TOEFL SWOT ERP CRM PR SMM MOOC GPS GIS ГИС EAEU ЕАЭС SCO ШОС
    ШҲТ WTO ВТО JST ЖСТ IMF МВФ XVF FAO OECD ОЭСР SSSR СССР РФ RF KPI ESG SDG BRICS БРИКС MRI МРТ
    KT КТ EKG ЭКГ ЭЭГ УЗИ PCR ПЦР WHO ВОЗ JSST ЖССТ ICU AIDS IQ EQ CNC CAD CAM GSM LTE IP TCP HTML
    SQL API XX XXI XIX XVIII XVII XVI XV XIV XIII XII XI IX VIII VII VI IV III II UZ USA UK EU ЕИ
    УМК ЎМК O‘MK ООО АО ЖШС AJ ОТМ OTM ТДПУ TDPU ТАТУ TATU ТДТУ TDTU ТТА TTA ТДЮУ TDYU ТДИУ TDIU
    ФА FA""".split()
)
_OPENING_QUOTES = "«\"“„‘'"
_ROMAN = re.compile(r"^M{0,3}(?:CM|CD|D?C{0,3})(?:XC|XL|L?X{0,3})(?:IX|IV|V?I{0,3})$")
# Atoqli otlar o'zagi (normallashtirilgan: kichik harf, apostrofsiz). Qo'shimcha
# qo'shilsa ham mos keladi: "O'ZBEKISTONDA" → "O'zbekistonda".
_PROPER_STEMS = tuple(
    """ozbekiston узбекистан ўзбекистон uzbekistan qoraqalpogiston қорақалпоғистон каракалпакстан
    toshkent тошкент ташкент tashkent samarqand самарқанд самарканд samarkand buxoro бухоро бухар bukhara
    xorazm хоразм хорезм khorezm fargona фарғона фергана fergana andijon андижон андижан andijan
    namangan наманган navoiy навоий навои qashqadaryo қашқадарё кашкадар surxondaryo сурхондарё сурхандар
    jizzax жиззах джизак sirdaryo сирдарё сырдар nukus нукус termiz термиз термез qarshi қарши карши
    guliston гулистон urganch урганч chirchiq чирчиқ qoqon қўқон коканд margilon марғилон shahrisabz
    шаҳрисабз xiva хива khiva rossiya россия россий russia qozogiston қозоғистон казахстан kazakhstan
    qirgiziston қирғизистон кыргызстан tojikiston тожикистон таджикистан turkmaniston туркманистон
    туркменистан afgoniston афғонистон афганистан xitoy хитой китай china yaponiya япония japan koreya
    корея korea germaniya германия germany fransiya франция france angliya англия england britaniya
    британ britain amerika америк america turkiya туркия турци turkey hindiston ҳиндистон индия india
    eron эрон иран iran yevropa европ europe osiyo осиё азия asia temur темур тимур alisher алишер
    ulugbek улуғбек улугбек bobur бобур бабур beruniy беруний бируни forobiy форобий фараби xorazmiy
    хоразмий qodiriy қодирий cholpon чўлпон fitrat фитрат avloniy авлоний behbudiy беҳбудий
    quron қуръон коран alloh аллоҳ аллах muhammad муҳаммад мухаммад amudaryo амударё амудар orol орол арал""".split()
)
# Atoqli ot ortidan kelsa, bu so'zlar ham bosh harf bilan: "O‘zbekiston Respublikasi".
_PROPER_FOLLOWERS = ("respublika", "республик", "federatsiya", "федерац", "viloyat", "вилоят", "област")
_EDGE = re.compile(r"^([^\w]*)(.*?)([^\w]*)$", re.S | re.U)


def _stem_key(word: str) -> str:
    return re.sub(r"[ʻʼ'‘’`]", "", word.casefold())


def is_shouting(title: str | None, threshold: float = 0.8, min_letters: int = 12) -> bool:
    letters = [ch for ch in title or "" if ch.isalpha()]
    return len(letters) >= min_letters and sum(ch.isupper() for ch in letters) / len(letters) > threshold


def _capitalize_first(word: str) -> str:
    for index, char in enumerate(word):
        if char.isalpha():
            return word[:index] + char.upper() + word[index + 1:]
    return word


def sentence_case(title: str) -> str:
    """BOSH HARFLI sarlavhani gap registriga keltiradi.

    Qisqartmalar, rim raqamlari, raqamli belgilar (COVID-19, H2O) va
    atoqli otlar o'zgarmaydi; aralash registrli so'z (mRNA, iPhone) ataylab
    shunday yozilgan deb hisoblanadi.
    """
    out: list[str] = []
    sentence_start = True
    previous_proper = False
    for token in re.split(r"(\s+)", title):
        if not token or token.isspace():
            out.append(token)
            continue
        lead, core, trail = _EDGE.match(token).groups()
        upper_core = core.upper()
        proper = False
        if not core:
            word = token
        elif any(ch.islower() for ch in core):
            word = lead + core + trail
        elif upper_core in _ACRONYM_FORMS:
            word = lead + _ACRONYM_FORMS[upper_core] + trail
        elif upper_core in _ACRONYMS or any(ch.isdigit() for ch in core) or (
            len(core) > 1 and _ROMAN.match(core) and core.isascii()
        ):
            word = token
        else:
            lowered = core.lower()
            key = _stem_key(lowered)
            proper = key.startswith(_PROPER_STEMS) or (previous_proper and key.startswith(_PROPER_FOLLOWERS))
            # Qo'shtirnoq ichidagisi odatda nom: «Prepare» darsligi, "Navro‘z" bayrami.
            if proper or sentence_start or any(mark in lead for mark in _OPENING_QUOTES):
                lowered = _capitalize_first(lowered)
            word = lead + lowered + trail
        if sentence_start and core:
            word = _capitalize_first(word) if not any(ch.isdigit() for ch in word[:1]) else word
            sentence_start = False
        out.append(word)
        previous_proper = proper
        if re.search(r"[.!?]$", token):
            sentence_start = True
    return "".join(out)


def display_title(title: str | None) -> str:
    """Sahifada ko'rsatiladigan sarlavha. Bazadagi asl sarlavha o'zgarmaydi."""
    text = clean_title(title)
    return sentence_case(text) if is_shouting(text) else text
