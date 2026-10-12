"""`/iqtibos` vositasi: istalgan maqola uchun GOST, APA, MLA, Chicago.

Formatlash maqola sahifasidagi bilan bir xil (`citations.citation_formats`) —
vosita uchun alohida qoidalar yozilmaydi, aks holda ikki joyda ikki xil
GOST chiqardi. Maqola bazada bo'lmasa, DOI bo'yicha ma'lumot Crossref'ning
ochiq API'sidan olinadi (kalitsiz, bepul).
"""
from __future__ import annotations

import re
import threading
from collections import OrderedDict
from types import SimpleNamespace
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..models import Article
from .article_text import clean_markup, clean_title
from .citations import citation_formats

DOI_RE = re.compile(r"^10\.\d{4,9}/\S{1,200}$")
CROSSREF_URL = "https://api.crossref.org/works/{doi}"
FORMATS = ("gost", "apa", "mla", "chicago")
_CACHE_SIZE = 500
_cache: OrderedDict[str, dict[str, Any] | None] = OrderedDict()
_cache_lock = threading.Lock()


class CitationError(ValueError):
    """Foydalanuvchi kiritgan ma'lumot yaroqsiz."""


def normalize_doi(value: str) -> str:
    """`https://doi.org/10.1/x`, `doi:10.1/x`, `10.1/X` → `10.1/x`."""
    text = (value or "").strip()
    text = re.sub(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", "", text, flags=re.I)
    text = text.strip().rstrip(".").lower()
    if not DOI_RE.match(text):
        raise CitationError("DOI formati noto‘g‘ri. Namuna: 10.5281/zenodo.123456")
    return text


def _record(fields: dict[str, Any]) -> SimpleNamespace:
    """`citation_formats` kutgan maqola ko'rinishi (bazasiz)."""
    title = clean_title(fields.get("title"))
    journal = clean_title(fields.get("journal"))
    if not title:
        raise CitationError("Sarlavha kiritilmagan")
    if not journal:
        raise CitationError("Jurnal nomi kiritilmagan")
    year = fields.get("year")
    try:
        year = int(year) if year not in (None, "") else None
    except (TypeError, ValueError) as error:
        raise CitationError("Yil son bo‘lishi kerak") from error
    authors = [clean_title(name) for name in fields.get("authors") or [] if clean_title(name)]
    text = lambda key: (str(fields.get(key)).strip() or None) if fields.get(key) not in (None, "") else None  # noqa: E731
    return SimpleNamespace(
        title=title,
        authors=authors[:30],
        journal=SimpleNamespace(name=journal),
        publication_year=year,
        volume=text("volume"),
        issue=text("issue"),
        pages=text("pages"),
        doi=text("doi"),
        landing_url=text("url"),
        pdf_url=None,
        language=text("language"),
    )


def format_fields(fields: dict[str, Any]) -> dict[str, str]:
    formats = citation_formats(_record(fields))
    return {key: formats[key] for key in FORMATS}


def _fields_from_article(article: Article) -> dict[str, Any]:
    return {
        "title": article.title,
        "authors": list(article.authors or []),
        "journal": article.journal.name if article.journal else "",
        "year": article.publication_year,
        "volume": article.volume,
        "issue": article.issue,
        "pages": article.pages,
        "doi": article.doi,
        "url": article.landing_url,
        "language": article.language,
    }


def _crossref(doi: str, client: httpx.Client | None = None) -> dict[str, Any] | None:
    with _cache_lock:
        if doi in _cache:
            _cache.move_to_end(doi)
            return _cache[doi]
    own = client is None
    client = client or httpx.Client(timeout=8.0, headers={"User-Agent": "IlmIz/1.0 (https://ilmiz.uz)"})
    try:
        response = client.get(CROSSREF_URL.format(doi=doi))
    except httpx.HTTPError:
        return None  # vaqtincha xato keshlanmaydi
    finally:
        if own:
            client.close()
    if response.status_code == 404:
        result = None
    elif response.status_code != 200:
        return None
    else:
        message = response.json().get("message") or {}
        # "LeCun, Yann" → "LeCun Y." — bazadagi va GOST'dagi "Familiya I." shakli.
        def initials(given: str) -> str:
            return " ".join(f"{part[0]}." for part in re.split(r"[\s.]+", given) if part)

        authors = [
            " ".join(part for part in (item.get("family"), initials(item.get("given") or "")) if part)
            for item in message.get("author") or []
            if item.get("family") or item.get("given")
        ]
        issued = (message.get("issued") or {}).get("date-parts") or [[None]]
        result = {
            "title": clean_title((message.get("title") or [""])[0]),
            "authors": authors,
            "journal": clean_title((message.get("container-title") or [""])[0]),
            "year": issued[0][0] if issued and issued[0] else None,
            "volume": message.get("volume"),
            "issue": message.get("issue"),
            "pages": message.get("page"),
            "doi": doi,
            "url": message.get("URL"),
            "language": message.get("language"),
            "abstract": clean_markup(message.get("abstract")),
        }
    with _cache_lock:
        _cache[doi] = result
        while len(_cache) > _CACHE_SIZE:
            _cache.popitem(last=False)
    return result


def lookup_doi(db: Session, raw: str, *, client: httpx.Client | None = None) -> dict[str, Any] | None:
    """DOI bo'yicha maqola: avval IlmIz bazasi, keyin Crossref."""
    doi = normalize_doi(raw)
    article = db.scalar(
        select(Article).options(selectinload(Article.journal)).where(Article.doi == doi, Article.is_deleted.is_(False))
    )
    if article is not None:
        from .seo import article_path

        fields = _fields_from_article(article)
        return {"source": "ilmiz", "fields": fields, "formats": format_fields(fields),
                "articleUrl": article_path(article.id, article.title)}
    found = _crossref(doi, client)
    if not found or not found.get("title") or not found.get("journal"):
        return None
    fields = {key: value for key, value in found.items() if key != "abstract"}
    return {"source": "crossref", "fields": fields, "formats": format_fields(fields), "articleUrl": None}
