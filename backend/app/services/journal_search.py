"""Jurnalni nomidan qidirish: kirill va lotin yozuvlari uchrashsin.

Ilgari so'rov ustunlar bo'yicha `LIKE` bilan qidirilardi va faqat so'rovning
o'zi lotinga o'girilardi. Shuning uchun faqat bir yo'nalish ishlardi:
"Водийнома" deb qidirilganda lotin varianti ham sinalardi, lekin
"Vodiynoma" deb qidirilganda bazadagi "Водийнома" topilmasdi. Apostrof ham
to'sqinlik qilardi: "Ozbekiston" so'rovi "Oʻzbekiston" ga mos kelmasdi.

Endi ikkala tomon ham `search_text.normalize` bilan bitta shaklga keltiriladi
(kichik harf, kirilldan lotinga, apostrofsiz). Bazada 467 jurnal bor, shuning
uchun taqqoslash Python tarafda — alohida ustun ham, indeks ham kerak emas.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Journal
from .search_text import normalize, query_words

# Qidiriladigan maydonlar: nom, qisqa nom, nashriyot va ikkala ISSN.
FIELDS = (Journal.name, Journal.short_name, Journal.publisher, Journal.issn, Journal.eissn)


def matching_ids(db: Session, query: str | None) -> set[int] | None:
    """So'rovga mos jurnal id'lari.

    Har bir so'z topilishi shart (ko'p so'zli so'rovlar uchun). Qidiriladigan
    so'z bo'lmasa (bo'sh yoki bir harfli so'rov) `None` — bu holda chaqiruvchi
    filtr qo'ymaydi, ya'ni eski xatti-harakat saqlanadi.
    """
    words = query_words(query or "")
    if not words:
        return None
    matched: set[int] = set()
    for row in db.execute(select(Journal.id, *FIELDS)):
        haystack = normalize(" ".join(str(value) for value in row[1:] if value))
        if all(word in haystack for word in words):
            matched.add(row[0])
    return matched
