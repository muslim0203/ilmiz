"""Qidiruv uchun matn normalizatsiyasi.

Bir maqolaning mualliflari bir jurnalda kirillda, boshqasida lotinda
yoziladi; foydalanuvchi esa bittasini yozadi. Ikkala tomonni ham bitta
shaklga keltirsak, ular o'rtada uchrashadi.

Bu ustun ishlatilgani uchun so'rovda `ilike` kerak emas — SQLite'da `lower()`
Python callback'i 106 000 qator uchun chaqirilib, qidiruvni 0.18s dan 1.2s ga
sekinlashtirardi.
"""
from __future__ import annotations

import re

CYRILLIC_TO_LATIN = str.maketrans({
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "yo", "ж": "j",
    "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m", "н": "n", "о": "o",
    "п": "p", "р": "r", "с": "s", "т": "t", "у": "u", "ф": "f", "х": "x", "ц": "ts",
    "ч": "ch", "ш": "sh", "щ": "sh", "ъ": "", "ы": "i", "ь": "", "э": "e", "ю": "yu",
    "я": "ya", "ғ": "g", "қ": "q", "ҳ": "h", "ў": "o",
})
APOSTROPHES = "ʻʼ'‘’`"
_SPACES = re.compile(r"\s+")


def normalize(value: str | None) -> str:
    """Kichik harf + kirilldan lotinga + apostroflarni tozalash."""
    if not value:
        return ""
    text = value.casefold()
    for mark in APOSTROPHES:
        text = text.replace(mark, "")
    text = text.translate(CYRILLIC_TO_LATIN)
    return _SPACES.sub(" ", text).strip()


def article_search_text(title: str | None, abstract: str | None, authors: list[str] | None) -> str:
    """Maqolaning qidiriladigan matni: sarlavha + annotatsiya + mualliflar."""
    parts = [title or "", abstract or "", " ".join(authors or [])]
    return normalize(" ".join(part for part in parts if part))


LIKE_ESCAPE = "\\"


def escape_like(value: str) -> str:
    """`LIKE` joker belgilarini ekranlaydi; `.like(..., escape=LIKE_ESCAPE)` bilan ishlatiladi.

    Foydalanuvchi so'zi to'g'ridan-to'g'ri patternga qo'shilardi: `%%%%`
    to'liq skan va nomaqbul mosliklar berardi, `_` esa istalgan belgiga mos kelardi.
    """
    return (
        value.replace(LIKE_ESCAPE, LIKE_ESCAPE + LIKE_ESCAPE)
        .replace("%", LIKE_ESCAPE + "%")
        .replace("_", LIKE_ESCAPE + "_")
    )


def query_words(query: str) -> list[str]:
    """So'rovni normallashtirib so'zlarga ajratadi.

    Har bir so'z alohida qidiriladi va hammasi topilishi shart — mualliflar
    familiya-birinchi saqlanadi ("Sharofiddinov, Kamoliddin"), shuning uchun
    to'liq ism bitta bo'lak sifatida hech qachon topilmasdi.
    """
    return [word for word in normalize(query).split() if len(word) > 1]
