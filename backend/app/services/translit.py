"""Jurnal nomining ikkinchi yozuvdagi varianti (SEO uchun).

Bazadagi 467 jurnalning 314 tasi kirill yozuvida ("Водийнома", "ТАТУ
хабарлари"), foydalanuvchi esa Google'da ko'pincha lotinda yozadi
("Vodiynoma"). Sahifada faqat bitta yozuv bo'lsa, ikkinchisidagi so'rovga
mos kelmaydi — tadqiq.uz aynan shu sabab `alternateName` beradi.

Bu modul ko'rsatish uchun (katta-kichik harf saqlanadi) o'zbek kirill
yozuvini rasmiy lotin alifbosiga o'giradi. `search_text.normalize` dan
farqi: u faqat qidiruv indeksi uchun kichik harfli va apostrofsiz shakl
beradi.

Ruscha nomlar ("Химия природных соединений") lotinga o'girilmaydi — bunday
transliteratsiyani hech kim qidirmaydi va u sahifada begona ko'rinadi.
"""
from __future__ import annotations

import re

# O'zbek lotin alifbosidagi rasmiy apostrof (oʻ, gʻ) — sahifada ham,
# JSON-LD'da ham bitta belgi ishlatiladi; qidiruv indeksi uni tashlab yuboradi.
TURNED_COMMA = "‘"

_SINGLE = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "ж": "j", "з": "z", "и": "i",
    "й": "y", "к": "k", "л": "l", "м": "m", "н": "n", "о": "o", "п": "p", "р": "r",
    "с": "s", "т": "t", "у": "u", "ф": "f", "х": "x", "ъ": "ʼ", "ь": "",
    "э": "e", "ы": "i",
    "ғ": "g" + TURNED_COMMA, "қ": "q", "ҳ": "h", "ў": "o" + TURNED_COMMA,
}
_DIGRAPH = {
    "ё": "yo", "ю": "yu", "я": "ya", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "sh",
}
# So'z boshida va unlidan keyin "е" = "ye" ("Ер" → "Yer", "тоер" → "toyer"),
# undoshdan keyin oddiy "e" ("Мен" → "Men").
_VOWELS = set("аеёиоуэюяўАЕЁИОУЭЮЯЎ")
# Faqat rus tilida uchraydigan belgilar — bunday nom o'girilmaydi.
_RUSSIAN_ONLY = re.compile(r"[ыщЫЩ]")
# Ruscha bog'lovchi/ko'makchi so'zlar: "Вестник науки и практики" da ы/щ yo'q,
# lekin " и " uni ruscha deb beradi. O'zbek kirillida bular "ва", "ҳақида".
_RUSSIAN_WORDS = re.compile(r"(?<![а-яё])(и|в|на|по|для|об|из|при|науки|наука|науке|вестник|известия|проблемы|вопросы)(?![а-яё])", re.IGNORECASE)
_CYRILLIC = re.compile(r"[а-яА-ЯёЁўғқҳЎҒҚҲ]")


def _map_one(char: str, previous: str | None) -> str:
    lower = char.lower()
    upper = char != lower
    if lower == "е":
        out = "ye" if previous is None or not previous.isalpha() or previous in _VOWELS else "e"
    elif lower in _DIGRAPH:
        out = _DIGRAPH[lower]
    elif lower in _SINGLE:
        out = _SINGLE[lower]
    else:
        return char
    if not out:
        return ""
    if upper:
        # "ТАТУ" kabi to'liq bosh harfli so'zlarda digraf ham bosh harfda: "SH".
        return out.upper() if _all_caps_context(previous) else out[0].upper() + out[1:]
    return out


def _all_caps_context(previous: str | None) -> bool:
    return bool(previous and previous.isalpha() and previous == previous.upper())


def cyrillic_to_latin(value: str) -> str:
    """O'zbek kirill matnini lotinga o'giradi (katta-kichik harf saqlanadi)."""
    out: list[str] = []
    previous: str | None = None
    for char in value:
        out.append(_map_one(char, previous))
        previous = char
    return "".join(out)


def looks_russian(value: str) -> bool:
    return bool(_RUSSIAN_ONLY.search(value) or _RUSSIAN_WORDS.search(value))


def has_cyrillic(value: str) -> bool:
    return bool(_CYRILLIC.search(value))


def alternate_names(name: str | None, languages: list[str] | None = None) -> list[str]:
    """Nomning boshqa yozuvdagi varianti (bo'lsa).

    Kirillcha o'zbek nom → lotin. Ruscha nom (ы/щ bor yoki tillar faqat rus)
    o'girilmaydi. Lotincha nom uchun kirill varianti berilmaydi: lotin →
    kirill ko'p ma'noli (sh/ch/ng, apostrof) va xato variant zarar qiladi.
    """
    text = (name or "").strip()
    if not text or not has_cyrillic(text) or looks_russian(text):
        return []
    langs = {item.casefold() for item in (languages or [])}
    if langs and langs <= {"rus", "ru"}:
        return []
    latin = cyrillic_to_latin(text)
    return [latin] if latin and latin != text else []
