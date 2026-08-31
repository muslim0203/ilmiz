"""Maqola qidiruvi uchun FTS5 indeksidan foydalanish.

Qidiruv `search_text LIKE '%so'z%'` bilan ishlardi. Boshida joker belgi
bo'lgani uchun indeks yordam bermasdi: har so'rov 104 000 qatorni to'liq
skanerlardi (~0.25-0.34s) va natijalar faqat sanaga qarab tartiblanardi.

FTS5 ikkalasini hal qiladi — 60-90 baravar tez va BM25 reytingi bor.

Indeks `trigram` tokenizatori bilan qurilgan, ya'ni qism-so'z bo'yicha
topadi va hozirgi `LIKE` bilan aynan bir xil natija beradi. Shuning uchun
bu almashtirish qidiruv qamrovini o'zgartirmaydi.
"""
from __future__ import annotations

from sqlalchemy import Select, column, inspect, table, text
from sqlalchemy.orm import Session

from .search_text import query_words

TABLE = "articles_fts"
# `trigram` uch belgidan qisqa bo'lakni indekslay olmaydi.
MIN_TERM_LENGTH = 3

articles_fts = table(TABLE, column("rowid"), column("search_text"))


def available(db: Session) -> bool:
    """Indeks shu bazada bormi.

    FTS5 faqat SQLite'da. PostgreSQL'da yoki migratsiya hali qo'llanmagan
    bazada eski `LIKE` yo'li ishlatiladi.
    """
    bind = db.get_bind()
    if bind.dialect.name != "sqlite":
        return False
    return TABLE in inspect(bind).get_table_names()


def match_expression(query: str) -> str | None:
    """Foydalanuvchi so'rovini FTS5 ifodasiga aylantiradi.

    Har bir so'z qo'shtirnoq ichida — shunda FTS5 uni maxsus belgi emas,
    oddiy matn deb qaraydi (`AND`, `OR`, `*`, `-` va qavslar shu tarzda
    zararsizlanadi).

    Uch belgidan qisqa so'z bo'lsa `None` qaytadi: trigram uni topa
    olmaydi, ya'ni chaqiruvchi eski yo'lga qaytishi kerak.
    """
    words = query_words(query)
    if not words or any(len(word) < MIN_TERM_LENGTH for word in words):
        return None
    return " ".join('"{}"'.format(word.replace('"', '""')) for word in words)


def apply(statement: Select, expression: str) -> Select:
    """So'rovga FTS bog'lanishini va BM25 tartibini qo'shadi.

    `bm25()` manfiy qiymat qaytaradi va kichigi mosroq degani, shuning
    uchun o'sish tartibida saralanadi.
    """
    return (
        statement.join(articles_fts, text("articles_fts.rowid = articles.id"))
        .where(text("articles_fts MATCH :fts_query"))
        .params(fts_query=expression)
        .order_by(None)
        .order_by(text("bm25(articles_fts)"))
    )


def rebuild(db: Session) -> int:
    """Indeksni asosiy jadvaldan qayta quradi.

    Ommaviy yangilashlardan keyin kerak bo'lishi mumkin; odatda triggerlar
    sinxronlikni o'zi ushlab turadi.
    """
    db.execute(text(f"INSERT INTO {TABLE}({TABLE}) VALUES('rebuild')"))
    db.commit()
    return db.execute(text(f"SELECT count(*) FROM {TABLE}")).scalar() or 0


def check_integrity(db: Session) -> bool:
    """FTS5 indeksining asosiy jadvalga mosligini tekshiradi."""
    try:
        db.execute(text(f"INSERT INTO {TABLE}({TABLE}) VALUES('integrity-check')"))
        return True
    except Exception:
        return False


__all__ = ["apply", "available", "check_integrity", "match_expression", "rebuild"]
