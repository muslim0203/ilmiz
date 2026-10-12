"""Maqola sahifasi indeksga loyiqmi — "sifat birinchi" mezoni.

Google'ning 2026-yil sentyabr–oktyabr spam-yangilanishidan keyin saytning
ko'rsatishlari deyarli nolga tushdi: 140 ming avtomatik yig'ilgan sahifaning
ko'pi qo'shimcha qiymatsiz deb baholandi. Endi faqat mazmunli sahifalar
indeksga taklif qilinadi; qolganlari `noindex, follow` (havolalari baribir
kuzatiladi) va sitemap'dan chiqariladi.

Mezon ikki ko'rinishda yoziladi va ular bir-biriga mos bo'lishi shart:
`issues()` — sahifadagi `robots` uchun, `indexable_clause()` — sitemap
so'rovi uchun. Aks holda sitemap `noindex` sahifani taklif qilib qo'yardi.
"""
from __future__ import annotations

from sqlalchemy import and_, func, or_
from sqlalchemy.sql.elements import ColumnElement

from ..models import Article
from .article_text import has_html_artifacts

MIN_ABSTRACT = 400


def issues(article: Article) -> list[str]:
    """Mezondan o'tmagan shartlar ro'yxati (bo'sh — indeksga loyiq)."""
    problems = []
    if article.is_deleted or article.duplicate_of is not None:
        problems.append("takror_yoki_ochirilgan")
    abstract = article.abstract or ""
    if len(abstract) < MIN_ABSTRACT:
        problems.append("annotatsiya_qisqa")
    elif has_html_artifacts(abstract):
        # SQL tomonida tekshirilmaydi: annotatsiyalar import va
        # `clean-articles` bilan tozalanadi, bu faqat ehtiyot chorasi.
        problems.append("annotatsiyada_html")
    if not article.authors:
        problems.append("muallifsiz")
    if article.journal_id is None:
        problems.append("jurnalsiz")
    if not article.publication_year:
        problems.append("yilsiz")
    if not article.doi and not article.keywords:
        problems.append("kalit_soz_va_doi_yoq")
    return problems


def is_indexable(article: Article) -> bool:
    return not issues(article)


def indexable_clause() -> ColumnElement[bool]:
    """`issues()` ning SQL ko'rinishi (HTML tekshiruvisiz)."""
    return and_(
        Article.is_deleted.is_(False),
        Article.duplicate_of.is_(None),
        func.length(func.coalesce(Article.abstract, "")) >= MIN_ABSTRACT,
        func.json_array_length(Article.authors) > 0,
        Article.journal_id.is_not(None),
        Article.publication_year.is_not(None),
        Article.publication_year != 0,
        or_(and_(Article.doi.is_not(None), Article.doi != ""), func.json_array_length(Article.keywords) > 0),
    )
