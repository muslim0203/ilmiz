"""Foydalanuvchi ismi bo'yicha uning maqolalarini topish.

Mualliflik nomlar orqali taxmin qilinadi, shuning uchun bu yerdagi hech narsa
avtomatik bog'lanmaydi — natija faqat *nomzodlar* ro'yxati. Qaysi biri
o'ziniki ekanini foydalanuvchi tasdiqlaydi.

Uchta qiyinchilik bor:

1. Mualliflar familiya-birinchi saqlanadi ("Sharofiddinov, Kamoliddin"),
   foydalanuvchi esa ism-birinchi yozadi. Shuning uchun tartibga bog'lanmay,
   so'zlar to'plami sifatida solishtiramiz.
2. Bir maqolada kirill, boshqasida lotin. `search_text.normalize` ikkalasini
   bitta shaklga keltiradi.
3. Ko'p jurnal faqat bosh harfni yozadi ("Sharofiddinov K."). Bunday yozuv
   to'liq ismni tasdiqlamaydi — Kamoliddin ham, Kamola ham bo'lishi mumkin.
   Shuning uchun ularni alohida, pastroq ishonch bilan belgilaymiz.
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..models import Article, User, UserArticle
from .search_text import normalize

# Bitta so'zli ism juda ko'p narsaga mos keladi ("Ali"), shuning uchun kamida
# ikkita so'z talab qilinadi.
MIN_NAME_WORDS = 2
# Nomzodlar ro'yxati foydalanuvchi ko'zdan kechiradigan uzunlikda qolsin.
MAX_SUGGESTIONS = 60
# Prefiltr uchun eng noyob so'zni tanlaymiz; kalta so'zlar buning uchun yaroqsiz.
MIN_PREFILTER_LENGTH = 4

EXACT = "exact"
PARTIAL = "partial"


@dataclass(frozen=True)
class Suggestion:
    article: Article
    confidence: str
    matched_author: str


def name_words(value: str | None) -> list[str]:
    """Ismni normallashtirilgan so'zlarga ajratadi.

    Tinish belgilari ("Sharofiddinov, K.") ajratuvchi sifatida qaraladi,
    shunda "k." dan "k" chiqadi.
    """
    if not value:
        return []
    cleaned = "".join(char if char.isalnum() else " " for char in normalize(value))
    return [word for word in cleaned.split() if word]


def _matches(user_words: list[str], author_words: list[str]) -> str | None:
    """Muallif yozuvi foydalanuvchi ismiga mos kelsa, ishonch darajasi.

    Har bir so'z uchun mos juft qidiriladi. To'liq mos kelsa — `EXACT`.
    Faqat bosh harf bilan mos kelsa (`k` <-> `kamoliddin`) — `PARTIAL`.
    """
    remaining = list(author_words)
    initial_only = False
    for word in user_words:
        exact = next((other for other in remaining if other == word), None)
        if exact is not None:
            remaining.remove(exact)
            continue
        # Bosh harf: tomonlardan biri bitta harf va ikkinchisining boshi.
        initial = next(
            (
                other
                for other in remaining
                if (len(other) == 1 and word.startswith(other))
                or (len(word) == 1 and other.startswith(word))
            ),
            None,
        )
        if initial is None:
            return None
        remaining.remove(initial)
        initial_only = True
    return PARTIAL if initial_only else EXACT


def claimed_article_ids(db: Session, user: User) -> set[int]:
    return set(db.scalars(select(UserArticle.article_id).where(UserArticle.user_id == user.id)))


def suggest(db: Session, user: User, *, limit: int = MAX_SUGGESTIONS) -> list[Suggestion]:
    """Foydalanuvchi ismiga mos maqolalar, aniqlari birinchi."""
    words = name_words(user.display_name)
    if len(words) < MIN_NAME_WORDS:
        return []

    # `search_text` bo'yicha oldindan siqib olamiz: 104 000 maqolaning
    # `authors` JSON ustunini Python tarafda ochish qimmat. Eng uzun so'z
    # (odatda familiya) eng kam natija qaytaradi.
    prefilter = max(words, key=len)
    if len(prefilter) < MIN_PREFILTER_LENGTH:
        return []

    already = claimed_article_ids(db, user)
    statement = (
        select(Article)
        .options(selectinload(Article.journal))
        .where(
            Article.is_deleted.is_(False),
            Article.search_text.contains(prefilter),
        )
        .order_by(Article.publication_year.desc().nulls_last(), Article.id.desc())
    )

    found: list[Suggestion] = []
    for article in db.scalars(statement).yield_per(200):
        if article.id in already:
            continue
        for author in article.authors or []:
            confidence = _matches(words, name_words(author))
            if confidence is not None:
                found.append(Suggestion(article, confidence, author))
                break
        if len(found) >= limit * 3:
            break

    found.sort(key=lambda item: (item.confidence != EXACT, -(item.article.publication_year or 0)))
    return found[:limit]


def claim(db: Session, user: User, article_id: int) -> UserArticle:
    article = db.get(Article, article_id)
    if article is None or article.is_deleted:
        raise LookupError("Maqola topilmadi")
    existing = db.scalar(
        select(UserArticle).where(
            UserArticle.user_id == user.id, UserArticle.article_id == article_id
        )
    )
    if existing is not None:
        return existing
    link = UserArticle(user_id=user.id, article_id=article_id)
    db.add(link)
    db.commit()
    db.refresh(link)
    return link


def unclaim(db: Session, user: User, article_id: int) -> bool:
    link = db.scalar(
        select(UserArticle).where(
            UserArticle.user_id == user.id, UserArticle.article_id == article_id
        )
    )
    if link is None:
        return False
    db.delete(link)
    db.commit()
    return True


def claimed(db: Session, user: User) -> list[Article]:
    """Tasdiqlangan maqolalar, yangisidan eskisiga."""
    statement = (
        select(Article)
        .join(UserArticle, UserArticle.article_id == Article.id)
        .options(selectinload(Article.journal))
        .where(UserArticle.user_id == user.id, Article.is_deleted.is_(False))
        .order_by(Article.publication_year.desc().nulls_last(), Article.id.desc())
    )
    return list(db.scalars(statement))


def stats(db: Session, user: User) -> dict[str, object]:
    """Profil uchun qisqa ko'rsatkichlar."""
    articles = claimed(db, user)
    years = [article.publication_year for article in articles if article.publication_year]
    journals = {article.journal_id for article in articles}
    return {
        "articles": len(articles),
        "journals": len(journals),
        "firstYear": min(years) if years else None,
        "lastYear": max(years) if years else None,
    }


__all__ = [
    "EXACT",
    "PARTIAL",
    "Suggestion",
    "claim",
    "claimed",
    "claimed_article_ids",
    "name_words",
    "stats",
    "suggest",
    "unclaim",
]
