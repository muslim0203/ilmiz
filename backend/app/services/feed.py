"""Maqola ro'yxatlarining "eng yangisi birinchi" tartibi.

Ilgari ro'yxatlar `publication_year DESC, id DESC` bo'yicha saralanardi, ya'ni
bir yil ichida tartib bazaga qo'shilish navbati edi: 11-sentabr 03:08 da
qo'shilgan 2-sentabr sanali maqolalar bir daqiqa oldin qo'shilgan
11-sentabrdagilardan tepada turardi.

Endi so'rov paytigacha (O'zbekiston vaqti) nashr etilganlar nashr sanasi
bo'yicha, yangisidan eskisiga. Sanasi hali kelmagan (jurnal sonni oldindan
e'lon qilgan: 104 ta maqola 2026-09-20 sanali edi) va sanasiz maqolalar
ro'yxatdan chiqarilmaydi — oxirida turadi va sanasi kelgan kuni o'z o'rniga
o'tadi. Aks holda ular ro'yxat tepasini egallab olardi.

Tezlik: `substr(publication_date, 1, 10)` ifodasi bo'yicha indeks
(`ix_articles_published`, `ix_articles_journal_published`). So'rov ikki
bo'lakda: o'tmish bo'lagi indeks bo'yicha tartiblangan skan, qolgani (bir necha
yuz qator) alohida — `CASE` bilan bitta tartib indeksni ishlatolmasdi.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import Select, func, literal_column, or_, select
from sqlalchemy.orm import Session

from ..models import Article

UZBEKISTAN = timezone(timedelta(hours=5), "Asia/Tashkent")

# Argumentlar bog'langan parametr emas, literal bo'lishi shart: SQLite ifoda
# indeksini faqat so'rovdagi ifoda indeksdagi bilan aynan bir xil bo'lsa tanlaydi.
PUBLISHED_ON = func.substr(Article.publication_date, literal_column("1"), literal_column("10"))


def today() -> str:
    """Joriy sana O'zbekiston vaqtida (`YYYY-MM-DD`); O'zbekistonda yozgi vaqt yo'q."""
    return datetime.now(UZBEKISTAN).date().isoformat()


def page(db: Session, statement: Select, *, limit: int, offset: int = 0, day: str | None = None) -> list[Article]:
    """Filtrlangan `select(Article)` ning bir sahifasi, eng yangi nashr birinchi.

    `statement` dagi tartib e'tiborga olinmaydi.
    """
    day = day or today()
    statement = statement.order_by(None)
    published = PUBLISHED_ON <= day
    rows = list(db.scalars(
        statement.where(published)
        .order_by(PUBLISHED_ON.desc(), Article.id.desc())
        .offset(offset)
        .limit(limit)
    ))
    if len(rows) == limit:
        return rows
    if rows:
        # O'tmish bo'lagi shu sahifada tugadi.
        published_total = offset + len(rows)
    else:
        published_total = db.scalar(select(func.count()).select_from(statement.where(published).subquery())) or 0
    later = (
        statement.where(or_(Article.publication_date.is_(None), PUBLISHED_ON > day))
        .order_by(PUBLISHED_ON.asc().nulls_last(), Article.id.desc())
        .offset(max(0, offset - published_total))
        .limit(limit - len(rows))
    )
    rows.extend(db.scalars(later))
    return rows
