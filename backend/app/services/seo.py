"""SEO qatlami: server tomonda meta, JSON-LD va indekslanadigan HTML.

Sayt SPA bo'lgani uchun robotlarga bo'sh `<div id="root">` ketardi.
JavaScript renderiga bog'liqlikni kamaytirish uchun har
bir URL uchun HTML qobiq serverda to'ldiriladi: `<head>` meta'lari va `#root`
ichidagi haqiqiy matn. React yuklangach o'sha joyni o'zi egallaydi — mazmun
bir xil, ya'ni bu cloaking emas, oddiy "static shell + CSR".
"""
from __future__ import annotations

import html
import json
import os
import re
import time
import ipaddress
from datetime import date, datetime, timedelta
from urllib.parse import urlsplit
from dataclasses import dataclass, field as dataclass_field

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from ..models import Article, Journal, OakRegistryEntry
from .search_text import normalize
from .taxonomy import FIELD_GROUPS, canonical_city, city_variants
from .translit import alternate_names
from .citations import citation_formats
from .payloads import article_payload
from . import feed
from . import search_index

SITE_NAME = "IlmIz"
SITE_TAGLINE = "O‘zbekiston OAK jurnallari va ilmiy maqolalar indeksi"
DEFAULT_SITE_URL = "http://127.0.0.1:8000"
DEFAULT_LOCALE = "uz_UZ"
DEFAULT_LANG = "uz"
LOCALES = {"uz": "uz_UZ", "ru": "ru_RU", "en": "en_US", "kaa": "kaa_UZ", "kk": "kk_KZ"}

# OAK importi har jurnalga yozadigan bo'sh tavsif. Yuzlab sahifada bir xil
# meta description bo'lib chiqardi — Google uni tashlab, o'zi snippet yasaydi.
OAK_PLACEHOLDER = "OAK rasmiy elektron reestridan import qilingan jurnal."
# Jurnal sahifasi <title> chegarasi: nom hech qachon kesilmaydi, faqat
# qo'shimcha ("OAK jurnali, ISSN …") sig'masa tushib qoladi.
JOURNAL_TITLE_LIMIT = 70

# Robotlarga to'liq snippet va katta rasm ruxsati: qisqartirilgan snippet
# CTR'ni pasaytiradi, Yandex esa `max-snippet` ni ham hisobga oladi.
INDEXABLE = "index, follow, max-snippet:-1, max-image-preview:large, max-video-preview:-1"
NOINDEX = "noindex, follow"

# Bazadagi til nomlari ko'rsatish uchun yozilgan; meta teglarda BCP-47 kerak.
LANGUAGE_CODES = {
    "o‘zbek": "uz", "o'zbek": "uz", "ozbek": "uz", "uz": "uz", "uz_latn": "uz-Latn",
    "uz_cyrl": "uz-Cyrl", "rus": "ru", "ru": "ru", "ingliz": "en", "en": "en",
    "kaa": "kaa", "qoraqalpoq": "kaa", "kaz": "kk", "qozoq": "kk", "ara": "ar",
    "arab": "ar", "tojik": "tg", "turk": "tr", "nemis": "de", "fransuz": "fr",
}

_WORD = re.compile(r"[^a-z0-9]+")
_TAGS = re.compile(r"<[^>]+>")
_TITLE_TAG = re.compile(r"<title>.*?</title>", re.IGNORECASE | re.DOTALL)
_DESC_TAG = re.compile(r'<meta\s+name="description"[^>]*>', re.IGNORECASE)


# ---------------------------------------------------------------- sozlamalar


def site_url() -> str:
    """Kanonik domen. Prodda `ILMIZ_SITE_URL` bilan beriladi."""
    for key in ("ILMIZ_SITE_URL", "ILMIZ_PUBLIC_URL"):
        value = os.getenv(key, "").strip().rstrip("/")
        # Lokal dev manzili kanonik URL bo'lib qolmasin — aks holda sitemap
        # localhost havolalari bilan to'lib ketadi.
        if valid_origin(value):
            return value
    return DEFAULT_SITE_URL


def absolute(path: str) -> str:
    return f"{site_url()}{path}" if path.startswith("/") else f"{site_url()}/{path}"


def is_production_host() -> bool:
    """Faqat haqiqiy prod domenida indekslashga ruxsat beriladi.

    Staging yoki dasturchi nusxasi indeksga tushsa, asosiy domen bilan
    to'liq dublikat bo'lib, ikkalasining ham reytingini yeb qo'yadi.
    """
    if os.getenv("ILMIZ_NOINDEX", "").strip() == "1":
        return False
    origin = os.getenv("ILMIZ_SITE_URL", "").strip().rstrip("/")
    if not valid_origin(origin) or not origin.startswith("https://"):
        return False
    host = urlsplit(origin).hostname or ""
    if host == "localhost" or host.endswith(".localhost"):
        return False
    try:
        return ipaddress.ip_address(host).is_global
    except ValueError:
        return bool("." in host)


def valid_origin(value: str) -> bool:
    try:
        parsed = urlsplit(value)
        return bool(parsed.scheme in ("http", "https") and parsed.hostname
                    and not parsed.username and not parsed.password
                    and parsed.path in ("", "/") and not parsed.query and not parsed.fragment
                    and not any(char.isspace() for char in value))
    except ValueError:
        return False


# ------------------------------------------------------------------ matn/slug


def slugify(value: str | None, limit: int = 90) -> str:
    """Kirill va apostrofli lotinni ASCII slugga aylantiradi."""
    text = _WORD.sub("-", normalize(value)).strip("-")
    if len(text) <= limit:
        return text
    cut = text[:limit]
    # So'z o'rtasidan kesilgan slug qidiruvda ma'nosiz ko'rinadi.
    return cut.rsplit("-", 1)[0] if "-" in cut else cut


def clip(value: str | None, limit: int) -> str:
    """Snippet uzunligiga sig'diradi, so'zni bo'lmaydi."""
    text = _TAGS.sub(" ", value or "").replace("\xa0", " ")
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0].rstrip(" ,.;:—-") + "…"


def e(value: object) -> str:
    return html.escape(str(value or ""), quote=True)


def web_url(value: str | None) -> str | None:
    """Brauzer ocha oladigan havola bo'lsagina qaytaradi.

    Manbalarda `demo://`, `urn:` va bo'sh qiymatlar uchraydi; ular
    `citation_pdf_url` ga tushsa, Google Scholar yozuvni rad etadi.
    """
    text = (value or "").strip()
    try:
        parsed = urlsplit(text)
        return text if (parsed.scheme in ("http", "https") and parsed.hostname
                        and not parsed.username and not parsed.password
                        and not any(char.isspace() for char in text)) else None
    except ValueError:
        return None


def language_code(value: str | None) -> str:
    return LANGUAGE_CODES.get(normalize(value), DEFAULT_LANG)


def publication_date(raw: str | None, year: int | None) -> str:
    """Emit a genuine ISO date/year; never invent a month/day or use harvest time."""
    value = (raw or "").strip()
    if re.fullmatch(r"\d{4}[-/]\d{2}[-/]\d{2}(?:T.*)?", value):
        try:
            return date.fromisoformat(value[:10].replace("/", "-")).isoformat()
        except ValueError:
            pass
    if re.fullmatch(r"\d{4}", value) and 1000 <= int(value) <= 2999:
        return value
    return str(year) if year and 1000 <= year <= 2999 else ""


# ------------------------------------------------------------------- URL'lar


def journal_path(slug: str) -> str:
    return f"/jurnal/{slug}"


def journal_year_path(slug: str, year: int) -> str:
    return f"/jurnal/{slug}/{year}"


def article_path(article_id: int | str, title: str | None = None) -> str:
    tail = slugify(title, 80)
    return f"/maqola/{article_id}-{tail}" if tail else f"/maqola/{article_id}"


def field_path(name: str) -> str:
    return f"/soha/{slugify(name)}"


def city_path(name: str) -> str:
    return f"/shahar/{slugify(name)}"


def all_fields() -> list[str]:
    return [name for _, names in FIELD_GROUPS for name in names]


def field_by_slug(db: Session, slug: str) -> str | None:
    for name in all_fields():
        if slugify(name) == slug:
            return name
    # Taksonomiyada yo'q, lekin bazada bor sohalar ham ochilishi kerak.
    for (raw,) in db.execute(select(Journal.fields).distinct()):
        for name in raw or []:
            if slugify(name) == slug:
                return name
    return None


def cities(db: Session) -> list[str]:
    def collect() -> list[str]:
        seen: dict[str, None] = {}
        for (raw,) in db.execute(select(Journal.city).distinct()):
            name = canonical_city(raw)
            if name:
                seen[name] = None
        return sorted(seen)

    return _cached("cities", collect)


def city_by_slug(db: Session, slug: str) -> str | None:
    return next((name for name in cities(db) if slugify(name) == slug), None)


# ----------------------------------------------------------------- sahifa modeli


@dataclass
class PageMeta:
    """Bitta URL uchun serverda tayyorlangan hamma SEO ma'lumoti."""

    title: str
    description: str
    path: str
    body: str = ""
    robots: str = INDEXABLE
    og_type: str = "website"
    head: list[str] = dataclass_field(default_factory=list)
    jsonld: list[dict] = dataclass_field(default_factory=list)
    status: int = 200
    redirect: str | None = None
    published_time: str | None = None
    modified_time: str | None = None
    # Sahifaning asosiy tili: <html lang>, hreflang va og:locale shundan.
    lang: str = DEFAULT_LANG
    # React birinchi yuklashda API'ga qayta murojaat qilmasligi uchun sahifaga
    # JSON sifatida joylanadigan ma'lumot (`<script id="ilmiz-data">`).
    data: dict | None = None

    @property
    def canonical(self) -> str:
        return absolute(self.path)


def _breadcrumbs(items: list[tuple[str, str]]) -> dict:
    return {
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": index, "name": name, "item": absolute(path)}
            for index, (name, path) in enumerate(items, start=1)
        ],
    }


def _item_list(name: str, entries: list[tuple[str, str]]) -> dict:
    return {
        "@type": "ItemList",
        "name": name,
        "numberOfItems": len(entries),
        "itemListElement": [
            {"@type": "ListItem", "position": index, "name": label, "url": absolute(path)}
            for index, (label, path) in enumerate(entries, start=1)
        ],
    }


# ------------------------------------------------------- indekslanadigan HTML

def _chips(items: list[tuple[str, str]]) -> str:
    if not items:
        return ""
    links = "".join(f'<a class="seo-chip" href="{e(path)}">{e(label)}</a>' for label, path in items)
    return f'<div class="seo-chips">{links}</div>'


def _crumbs(items: list[tuple[str, str]]) -> str:
    parts = []
    for index, (label, path) in enumerate(items):
        last = index == len(items) - 1
        parts.append(
            f'<span aria-current="page">{e(label)}</span>' if last
            else f'<a href="{e(path)}">{e(label)}</a><span class="seo-sep">/</span>'
        )
    return f'<nav class="seo-crumbs" aria-label="Yo‘nalish">{"".join(parts)}</nav>'


def _journal_item(journal: Journal, articles: int = 0) -> str:
    meta = " · ".join(
        part for part in [
            e(journal.publisher),
            e(canonical_city(journal.city)),
            f"ISSN {e(journal.issn)}" if journal.issn else "",
            f"{articles} maqola" if articles else "",
        ] if part
    )
    fields = ", ".join(e(name) for name in (journal.fields or [])[:4])
    return (
        '<li class="seo-item">'
        f'<a class="seo-item-title" href="{e(journal_path(journal.slug))}">{e(journal.name)}</a>'
        f'<p class="seo-item-meta">{meta}</p>'
        + (f'<p class="seo-item-meta">{fields}</p>' if fields else "")
        + "</li>"
    )


def _article_item(article: Article) -> str:
    when = article.publication_date or (str(article.publication_year) if article.publication_year else "")
    meta = " · ".join(
        part for part in [
            e(", ".join(article.authors or [])[:180]),
            e(article.journal.name if article.journal else ""),
            e(when),
        ] if part
    )
    return (
        '<li class="seo-item">'
        f'<a class="seo-item-title" href="{e(article_path(article.id, article.title))}">{e(article.title)}</a>'
        f'<p class="seo-item-meta">{meta}</p>'
        + (f'<p class="seo-item-abstract">{e(clip(article.abstract, 220))}</p>' if article.abstract else "")
        + "</li>"
    )


def _pagination(path: str, page: int, total: int, per_page: int) -> str:
    """Chuqur ro'yxatlarni robot uchun bosib o'tiladigan qiladi."""
    pages = max(1, -(-total // per_page))
    if pages < 2:
        return ""
    def href(number: int) -> str:
        return path if number == 1 else f"{path}?sahifa={number}"
    window = sorted({1, pages, *range(max(1, page - 2), min(pages, page + 2) + 1)})
    # Exponential jump links keep even large yearly archives shallow for crawlers.
    jumps = {page + 2**power for power in range(2, pages.bit_length()) if page + 2**power <= pages}
    window = sorted(set(window) | jumps)
    links = []
    previous = 0
    for number in window:
        if previous and number - previous > 1:
            links.append('<span class="seo-sep">…</span>')
        links.append(
            f'<span aria-current="page">{number}</span>' if number == page
            else f'<a href="{e(href(number))}">{number}</a>'
        )
        previous = number
    return f'<nav class="seo-pager" aria-label="Sahifalar">{"".join(links)}</nav>'


# ------------------------------------------------------------------ so'rovlar

JOURNALS_PER_PAGE = 50
ARTICLES_PER_PAGE = 50


# Sanoq so'rovlari 104 000 qator ustidan ishlaydi va har sahifada takrorlanardi:
# bosh sahifa TTFB'si 400 ms edi. Bu qiymatlar faqat harvest'dan keyin
# o'zgaradi, shuning uchun qisqa muddatli kesh ularni tekinga aylantiradi.
CACHE_TTL = 300.0
_cache: dict[str, tuple[float, object]] = {}


def _cached(key: str, produce):
    hit = _cache.get(key)
    now = time.monotonic()
    if hit is not None and now - hit[0] < CACHE_TTL:
        return hit[1]
    value = produce()
    _cache[key] = (now, value)
    return value


def cached(key: str, produce):
    """Kesh boshqa modullar uchun ham ochiq — API sanoqlari ham shu yerda."""
    return _cached(key, produce)


def invalidate(key: str | None = None) -> None:
    """Keshni bo'shatadi.

    Ma'lumot to'g'ridan-to'g'ri o'zgartirilganda (masalan OpenAlex importi)
    chaqiriladi: aks holda jurnal sahifasi TTL tugaguncha eski sanoqni
    ko'rsatib turadi.
    """
    if key is None:
        _cache.clear()
    else:
        _cache.pop(key, None)


def reset_cache() -> None:
    """Harvest yoki import tugagach chaqiriladi."""
    _cache.clear()


def _counts(db: Session, journal_ids: list[int] | None = None) -> dict[int, int]:
    everything = _cached(
        "counts",
        lambda: {
            row[0]: row[1]
            for row in db.execute(
                select(Article.journal_id, func.count())
                .where(Article.is_deleted.is_(False))
                .group_by(Article.journal_id)
            )
        },
    )
    if journal_ids is None:
        return everything
    wanted = set(journal_ids)
    return {key: value for key, value in everything.items() if key in wanted}


def _journal_ids_for(db: Session, *, field: str | None = None, city: str | None = None) -> set[int] | None:
    """`fields` JSON ustun bo'lgani uchun filtr Python tarafda — jurnal 500 ga yaqin."""
    if not field and not city:
        return None
    rows = _cached(
        "journal_meta",
        lambda: [
            (journal_id, tuple(fields or []), journal_city)
            for journal_id, fields, journal_city in db.execute(
                select(Journal.id, Journal.fields, Journal.city)
            )
        ],
    )
    raw_cities = set(city_variants(city)) if city else set()
    matched: set[int] = set()
    for journal_id, fields, journal_city in rows:
        if field and field not in fields:
            continue
        if raw_cities and journal_city not in raw_cities:
            continue
        matched.add(journal_id)
    return matched


def _stats(db: Session) -> tuple[int, int]:
    return _cached(
        "stats",
        lambda: (
            db.scalar(select(func.count()).select_from(Journal)) or 0,
            db.scalar(select(func.count()).select_from(Article).where(Article.is_deleted.is_(False))) or 0,
        ),
    )


def _site_jsonld() -> list[dict]:
    """Har sahifada takrorlanadigan sayt darajasidagi grafik."""
    return [
        {
            "@type": "WebSite",
            "@id": absolute("/#website"),
            "url": absolute("/"),
            "name": SITE_NAME,
            "alternateName": "IlmIz — OAK jurnallari indeksi",
            "description": SITE_TAGLINE,
            "inLanguage": DEFAULT_LANG,
            "publisher": {"@id": absolute("/#organization")},
            "potentialAction": {
                "@type": "SearchAction",
                "target": {
                    "@type": "EntryPoint",
                    "urlTemplate": absolute("/qidiruv?q={search_term_string}"),
                },
                "query-input": "required name=search_term_string",
            },
        },
        {
            "@type": "Organization",
            "@id": absolute("/#organization"),
            "name": SITE_NAME,
            "url": absolute("/"),
            "description": SITE_TAGLINE,
            "logo": {"@type": "ImageObject", "url": absolute("/icon-512.png"), "width": 512, "height": 512},
            "areaServed": {"@type": "Country", "name": "O‘zbekiston"},
        },
    ]


# ---------------------------------------------------------------- sahifalar

CITATION_LABELS = {
    "apa": "APA", "gost": "GOST (OAK)", "mla": "MLA", "chicago": "Chicago", "harvard": "Harvard", "bibtex": "BibTeX",
}


def _recently_added(db: Session, limit: int = 12) -> tuple[str | None, list[Journal]]:
    """OAK ro'yxatiga eng so'nggi yilda qo'shilgan milliy jurnallar.

    «OAK ro'yxatiga qo'shilgan jurnallar 2025» — tez-tez so'raladigan so'rov;
    reestr yozuvlari (`status = Қўшилди`) shuni to'g'ridan-to'g'ri beradi.
    """
    def produce() -> tuple[str | None, list[int]]:
        latest = db.scalar(
            select(func.max(OakRegistryEntry.year)).where(
                OakRegistryEntry.status == "Қўшилди", OakRegistryEntry.journal_id.is_not(None)
            )
        )
        if not latest:
            return None, []
        ids = [
            row[0] for row in db.execute(
                select(OakRegistryEntry.journal_id)
                .where(OakRegistryEntry.status == "Қўшилди", OakRegistryEntry.year == latest,
                       OakRegistryEntry.journal_id.is_not(None))
                .group_by(OakRegistryEntry.journal_id)
                .order_by(func.max(OakRegistryEntry.id).desc())
                .limit(limit)
            )
        ]
        return str(latest), ids

    year, ids = _cached("recently_added", produce)
    if not ids:
        return year, []
    journals = db.scalars(select(Journal).where(Journal.id.in_(ids))).all()
    order = {journal_id: index for index, journal_id in enumerate(ids)}
    journals.sort(key=lambda item: order.get(item.id, 999))
    return year, journals


def _latest_harvest(db: Session) -> datetime | None:
    return _cached("latest_harvest", lambda: db.scalar(select(func.max(Article.harvested_at))))


def _faq_jsonld(items: list[tuple[str, str]]) -> dict:
    return {
        "@type": "FAQPage",
        "mainEntity": [
            {"@type": "Question", "name": question,
             "acceptedAnswer": {"@type": "Answer", "text": answer}}
            for question, answer in items
        ],
    }


def _faq_html(items: list[tuple[str, str]]) -> str:
    return "".join(f"<h3>{e(q)}</h3><p>{e(a)}</p>" for q, a in items)


def _home(db: Session) -> PageMeta:
    journals, articles = _stats(db)
    counts = _counts(db)
    top = db.scalars(
        select(Journal).where(Journal.id.in_([id for id, _ in sorted(counts.items(), key=lambda row: -row[1])[:24]]))
    ).all()
    top.sort(key=lambda journal: -counts.get(journal.id, 0))
    latest = feed.page(
        db,
        select(Article).options(selectinload(Article.journal)).where(Article.is_deleted.is_(False)),
        limit=12,
    )
    added_year, added = _recently_added(db)
    harvested = _latest_harvest(db)
    # 24 soha + ~40 shahar uchun jurnal sanoqlari — har so'rovda 250 ms olardi.
    def produce_field_counts() -> list[tuple[str, int]]:
        rows = [(name, len(_journal_ids_for(db, field=name) or set())) for name in all_fields()]
        return sorted(rows, key=lambda item: -item[1])

    def produce_city_counts() -> list[tuple[str, int]]:
        rows = [(name, len(_journal_ids_for(db, city=name) or set())) for name in cities(db)]
        return sorted(rows, key=lambda item: -item[1])

    field_counts = _cached("home_field_counts", produce_field_counts)
    cities_ranked = _cached("home_city_counts", produce_city_counts)

    faq = [
        ("OAK jurnallari ro‘yxati nima?",
         "Bu O‘zbekiston Respublikasi Vazirlar Mahkamasi huzuridagi Oliy attestatsiya komissiyasi (OAK) "
         "tasdiqlagan ilmiy nashrlar ro‘yxati. PhD va DSc dissertatsiyalarining asosiy natijalari aynan shu "
         "ro‘yxatdagi jurnallarda chop etilishi talab qilinadi. IlmIz rasmiy reestrdagi barcha "
         f"{journals} ta jurnalni ixtisoslik kodi, qaror raqami va sanasi bilan ko‘rsatadi."),
        ("Jurnal OAK ro‘yxatida ekanini qanday tekshiraman?",
         "Jurnal nomi yoki ISSN raqamini qidiruvga yozing. Jurnal sahifasida OAK holati, ixtisoslik kodi, "
         "qaror raqami, qo‘shilgan sanasi va rasmiy sayt havolasi ko‘rsatiladi; ro‘yxatdan chiqarilgan "
         "jurnallar alohida belgilanadi."),
        ("Maqolalar qayerdan olinadi?",
         "Jurnallarning o‘z saytlaridagi OAI-PMH repozitoriylaridan (asosan OJS) va OpenAlex bazasidan "
         "avtomatik yig‘iladi, har kuni yangilanadi. Har bir maqolada asl manba, DOI va PDF havolasi qoladi; "
         "IlmIz maqola matnini o‘zida saqlamaydi."),
        ("Maqolaga iqtibosni qanday olaman?",
         "Har bir maqola sahifasida APA, GOST (OAK talabi), MLA, Chicago, Harvard va BibTeX formatlaridagi "
         "tayyor iqtibos bor — nusxalab dissertatsiya yoki maqolaga qo‘yish mumkin."),
        ("Ilmiy soha yoki shahar bo‘yicha jurnallarni qanday topaman?",
         "«Ilmiy sohalar» bo‘limida 24 ta OAK sohasi, «Shaharlar» bo‘limida esa nashriyot joylashgan "
         "shaharlar bo‘yicha jurnallar ro‘yxati bor. Har bir soha va shahar sahifasi alohida manzilga ega."),
    ]

    body = (
        f'<h1>{e(SITE_TAGLINE)}</h1>'
        f'<p class="seo-lead">O‘zbekiston Oliy attestatsiya komissiyasi ro‘yxatidagi '
        f'<strong>{journals}</strong> ta ilmiy jurnal va ular chop etgan '
        f'<strong>{articles}</strong> ta maqolaning ochiq, bepul indeksi. Sarlavha, muallif, '
        f'kalit so‘z, ISSN, ilmiy soha va shahar bo‘yicha qidiring; APA, GOST, MLA, Chicago, '
        f'Harvard va BibTeX iqtiboslarini bir bosishda oling.</p>'
        f'<p><a href="/jurnallar">Barcha OAK jurnallari</a> · '
        f'<a href="/maqolalar">Barcha maqolalar</a> · '
        f'<a href="/yangi-maqolalar">Yangi maqolalar</a> · '
        f'<a href="/sohalar">Ilmiy sohalar</a> · '
        f'<a href="/shaharlar">Shaharlar</a> · '
        f'<a href="/loyiha">Loyiha haqida</a></p>'
        f'<table class="seo-facts"><caption>Indeks holati</caption><tbody>'
        f'<tr><th>OAK jurnallari</th><td>{journals}</td></tr>'
        f'<tr><th>Maqolalar</th><td>{articles}</td></tr>'
        f'<tr><th>Ilmiy sohalar</th><td>{len(all_fields())}</td></tr>'
        f'<tr><th>Shaharlar</th><td>{len(cities_ranked)}</td></tr>'
        + (f'<tr><th>So‘nggi yangilanish</th><td>{e(harvested.date().isoformat())}</td></tr>' if harvested else "")
        + '</tbody></table>'
        f'<h2>Eng ko‘p maqolali OAK jurnallari</h2>'
        f'<ul class="seo-list">{"".join(_journal_item(item, counts.get(item.id, 0)) for item in top[:24])}</ul>'
    )
    if added:
        body += (
            f'<h2>OAK ro‘yxatiga {e(added_year)}-yilda qo‘shilgan jurnallar</h2>'
            f'<p>Rasmiy reestrda «qo‘shildi» belgisi bilan turgan eng so‘nggi milliy jurnallar. '
            f'To‘liq ro‘yxat va qaror raqamlari har bir jurnal sahifasida.</p>'
            f'<ul class="seo-list">{"".join(_journal_item(item, counts.get(item.id, 0)) for item in added)}</ul>'
        )
    body += (
        f'<h2>So‘nggi qo‘shilgan maqolalar</h2>'
        f'<ul class="seo-list">{"".join(_article_item(item) for item in latest)}</ul>'
        f'<h2>Ilmiy sohalar bo‘yicha</h2>'
        + _chips([(f"{name} ({count})" if count else name, field_path(name)) for name, count in field_counts])
        + '<h2>Shaharlar bo‘yicha</h2>'
        + _chips([(f"{name} ({count})" if count else name, city_path(name)) for name, count in cities_ranked])
        + '<h2>IlmIz qanday ishlaydi</h2>'
        '<p>IlmIz — O‘zbekiston ilmiy jurnallari uchun ochiq bibliografik indeks. Jurnallar ro‘yxati OAK '
        'rasmiy elektron reestridan olinadi va har bir jurnal uchun ixtisoslik kodi, qaror raqami va sanasi '
        'saqlanadi. Maqolalar jurnal saytlarining OAI-PMH repozitoriylaridan va OpenAlex bazasidan avtomatik '
        'yig‘iladi: sarlavha, mualliflar, annotatsiya, kalit so‘zlar, jild, son, betlar va DOI. Matn '
        'saqlanmaydi — har maqola asl sahifasi va PDF’iga yo‘naltiradi. Qidiruv kirill va lotin yozuvini '
        'farqlamaydi: «Сулайманова» ham, «Sulaymanova» ham bir xil natija beradi.</p>'
        '<h2>Ko‘p so‘raladigan savollar</h2>'
        + _faq_html(faq)
    )
    return PageMeta(
        title=f"{SITE_NAME} — {SITE_TAGLINE}",
        description=(
            f"O‘zbekiston OAK ro‘yxatidagi {journals} ta ilmiy jurnal va {articles} ta "
            "maqolaning ochiq indeksi. Jurnalning OAK holati, ixtisoslik kodi va ISSN; muallif, kalit so‘z "
            "va soha bo‘yicha qidiruv; APA va GOST iqtibos."
        ),
        path="/",
        body=body,
        modified_time=harvested.isoformat() if harvested else None,
        jsonld=_site_jsonld() + [
            {
                "@type": "CollectionPage",
                "@id": absolute("/#page"),
                "url": absolute("/"),
                "name": f"{SITE_NAME} — {SITE_TAGLINE}",
                "isPartOf": {"@id": absolute("/#website")},
                "inLanguage": DEFAULT_LANG,
                "mainEntity": _item_list("Eng ko‘p maqolali OAK jurnallari", [(item.name, journal_path(item.slug)) for item in top[:24]]),
            },
            _faq_jsonld(faq),
        ],
    )


def _journal_list(db: Session, page: int, *, field: str | None = None, city: str | None = None) -> PageMeta:
    allowed = _journal_ids_for(db, field=field, city=city)
    statement = select(Journal)
    if allowed is not None:
        statement = statement.where(Journal.id.in_(allowed))
    total = len(allowed) if allowed is not None else _stats(db)[0]
    if page > max(1, -(-total // JOURNALS_PER_PAGE)):
        base = field_path(field) if field else city_path(city) if city else "/jurnallar"
        return _not_found(f"{base}?sahifa={page}")
    counts = _counts(db, list(allowed) if allowed is not None else None)
    journals = db.scalars(
        statement.outerjoin(
            recent := select(Article.journal_id, func.count().label("recent"))
            .where(Article.is_deleted.is_(False), Article.publication_year >= datetime.now().year - 1)
            .group_by(Article.journal_id).subquery(), recent.c.journal_id == Journal.id
        ).order_by(func.coalesce(recent.c.recent, 0).desc(), Journal.name, Journal.id)
        .offset((page - 1) * JOURNALS_PER_PAGE).limit(JOURNALS_PER_PAGE)
    ).all()
    article_total = sum(counts.get(item, 0) for item in (allowed if allowed is not None else counts))

    if field:
        base = field_path(field)
        heading = f"{field} sohasidagi OAK jurnallari"
        title = f"{field} — OAK jurnallari va ilmiy maqolalar"
        description = (
            f"{field} sohasi bo‘yicha OAK ro‘yxatidagi {total} ta ilmiy jurnal va "
            f"{article_total} ta maqola. ISSN, nashriyot va shahar ma’lumotlari bilan."
        )
        crumbs = [("Bosh sahifa", "/"), ("Sohalar", "/sohalar"), (field, base)]
    elif city:
        base = city_path(city)
        heading = f"{city} shahridagi OAK jurnallari"
        title = f"{city} — OAK jurnallari va ilmiy nashrlari"
        description = (
            f"{city} shahrida nashr etiladigan OAK ro‘yxatidagi {total} ta ilmiy jurnal "
            f"va {article_total} ta maqola."
        )
        crumbs = [("Bosh sahifa", "/"), ("Shaharlar", "/shaharlar"), (city, base)]
    else:
        base = "/jurnallar"
        heading = "O‘zbekiston OAK jurnallari ro‘yxati"
        title = f"OAK jurnallari ro‘yxati — {total} ta ilmiy nashr"
        description = (
            f"O‘zbekiston Oliy attestatsiya komissiyasi tasdiqlagan {total} ta ilmiy jurnalning "
            "to‘liq ro‘yxati: ISSN, nashriyot, shahar, ilmiy soha va maqolalar soni."
        )
        crumbs = [("Bosh sahifa", "/"), ("Jurnallar", "/jurnallar")]

    path = base if page == 1 else f"{base}?sahifa={page}"
    suffix = f" — {page}-sahifa" if page > 1 else ""
    body = (
        _crumbs(crumbs)
        + f"<h1>{e(heading)}{e(suffix)}</h1>"
        + f'<p class="seo-lead">{e(description)}</p>'
        + f'<ul class="seo-list">{"".join(_journal_item(item, counts.get(item.id, 0)) for item in journals)}</ul>'
        + _pagination(base, page, total, JOURNALS_PER_PAGE)
    )
    return PageMeta(
        title=clip(title + suffix, 65),
        description=clip(description, 158),
        path=path,
        body=body,
        jsonld=[
            {
                "@type": "CollectionPage",
                "url": absolute(path),
                "name": heading,
                "description": description,
                "inLanguage": DEFAULT_LANG,
                "isPartOf": {"@id": absolute("/#website")},
                "mainEntity": _item_list(heading, [(item.name, journal_path(item.slug)) for item in journals]),
            },
            _breadcrumbs(crumbs),
        ],
    )


def journal_description(journal: Journal) -> str | None:
    """Haqiqiy tavsif: profil xulosasi yoki tahrirlangan tavsif; OAK placeholder emas."""
    profile = journal.profile
    for candidate in ((profile.summary if profile else None), journal.description):
        text = (candidate or "").strip()
        if text and text != OAK_PLACEHOLDER:
            return text
    return None


def journal_title(name: str, issn: str | None, *, suffix: str = "") -> str:
    """Jurnal nomi to'liq qoladi — u aynan foydalanuvchi qidiradigan so'rov.

    Ilgari nom 46 belgida kesilardi ("Scientific Journal of Science, Research
    and…"), ya'ni sahifa o'z nomi bo'yicha so'rovga to'liq mos kelmasdi.
    """
    base = f"{name} — OAK jurnali"
    with_issn = f"{base}, ISSN {issn}" if issn else base
    if len(with_issn) + len(suffix) <= JOURNAL_TITLE_LIMIT:
        return with_issn + suffix
    if len(base) + len(suffix) <= JOURNAL_TITLE_LIMIT:
        return base + suffix
    return name + suffix


def _journal_lang(journal: Journal) -> str:
    """Jurnalning birinchi tili; ruscha nomli tilsiz jurnal — `ru`."""
    for item in journal.languages or []:
        return language_code(item)
    from .translit import has_cyrillic, looks_russian

    if has_cyrillic(journal.name) and looks_russian(journal.name):
        return "ru"
    return DEFAULT_LANG


def _registry_rows(db: Session, journal: Journal) -> list[OakRegistryEntry]:
    """Jurnalning OAK reestri yozuvlari (ixtisoslik/qaror bo'yicha takrorsiz)."""
    rows = db.scalars(
        select(OakRegistryEntry)
        .where(OakRegistryEntry.journal_id == journal.id)
        .order_by(OakRegistryEntry.year.desc(), OakRegistryEntry.id.desc())
    ).all()
    seen: set[tuple[str | None, str | None, str | None]] = set()
    unique: list[OakRegistryEntry] = []
    for row in rows:
        key = (row.specialty_code, row.decision, row.status)
        if key in seen:
            continue
        seen.add(key)
        unique.append(row)
    return unique[:12]


def _similar_journals(db: Session, journal: Journal, limit: int = 6) -> list[tuple[Journal, int]]:
    """Shu sohadagi (bo'lmasa shu shahardagi) eng faol jurnallar — ichki bog'lanish."""
    counts = _counts(db)
    candidates = db.scalars(
        select(Journal).where(Journal.id != journal.id, Journal.oak_status == "active")
    ).all()
    wanted = set(journal.fields or [])
    city = canonical_city(journal.city)
    ranked = sorted(
        candidates,
        key=lambda item: (
            -len(wanted & set(item.fields or [])),
            0 if canonical_city(item.city) == city else 1,
            -counts.get(item.id, 0),
            item.name,
        ),
    )
    chosen = [item for item in ranked if (wanted & set(item.fields or [])) or canonical_city(item.city) == city]
    return [(item, counts.get(item.id, 0)) for item in chosen[:limit]]


def _dedupe(values: list[str]) -> list[str]:
    seen: dict[str, None] = {}
    for value in values:
        text = (value or "").strip()
        if text:
            seen.setdefault(text, None)
    return list(seen)


# Maqola qabul qilish uchun yagona Telegram aloqa nuqtasi.
SUBMIT_TELEGRAM_URL = "https://t.me/zarifjon0203"


def _journal_page(db: Session, slug: str, year: int | None = None, page: int = 1) -> PageMeta:
    journal = db.scalar(
        select(Journal).where(Journal.slug == slug).options(
            selectinload(Journal.profile),
            selectinload(Journal.contacts),
            selectinload(Journal.editorial_members),
            selectinload(Journal.policies),
            selectinload(Journal.sections),
            selectinload(Journal.indexing_claims),
            selectinload(Journal.links),
        )
    )
    if journal is None:
        return _not_found(f"/jurnal/{slug}")

    total = db.scalar(
        select(func.count()).select_from(Article).where(
            Article.journal_id == journal.id, Article.is_deleted.is_(False)
        )
    ) or 0
    year_counts = [
        (row[0], row[1]) for row in db.execute(
            select(Article.publication_year, func.count())
            .where(Article.journal_id == journal.id, Article.is_deleted.is_(False),
                   Article.publication_year.is_not(None))
            .group_by(Article.publication_year)
            .order_by(Article.publication_year.desc())
        )
    ]
    years = [item for item, _ in year_counts]
    article_query = (
        select(Article)
        .options(selectinload(Article.journal))
        .where(Article.journal_id == journal.id, Article.is_deleted.is_(False))
    )
    if year:
        article_query = article_query.where(Article.publication_year == year)
    selected_total = db.scalar(select(func.count()).select_from(article_query.subquery())) or 0
    base = journal_year_path(slug, year) if year else journal_path(slug)
    if (year and not selected_total) or page > max(1, -(-selected_total // ARTICLES_PER_PAGE)):
        return _not_found(base if page == 1 else f"{base}?sahifa={page}")
    articles = feed.page(db, article_query, offset=(page - 1) * ARTICLES_PER_PAGE, limit=ARTICLES_PER_PAGE)

    city = canonical_city(journal.city)
    issn = journal.issn or journal.eissn or ""
    profile = journal.profile
    summary_full = journal_description(journal)
    summary = clip(summary_full, 400)
    aliases = alternate_names(journal.name, journal.languages)
    fields = list(journal.fields or [])
    registry = _registry_rows(db, journal)
    active = journal.oak_status == "active"
    # Eng so'nggi "qo'shildi/aktiv" yozuvi — qaror raqami va sanasi uchun.
    decision = next((row for row in registry if row.decision), None)
    span = f"{years[-1]}–{years[0]}" if len(years) > 1 else (str(years[0]) if years else "")

    page_suffix = f" — {page}-sahifa" if page > 1 else ""
    if year:
        path = journal_year_path(slug, year)
        heading = f"{journal.name} — {year}-yil maqolalari"
        title = f"{journal.name} — {year}-yil maqolalari{page_suffix}"
        description = (
            f"{journal.name} jurnalining {year}-yilda chop etilgan {selected_total} ta ilmiy maqolasi: "
            "muallif, annotatsiya, DOI va tayyor iqtibos."
        )
    else:
        path = journal_path(slug)
        heading = journal.name
        title = journal_title(journal.name, issn, suffix=page_suffix)
        fallback_bits = [
            f"{journal.name}" + (f" ({aliases[0]})" if aliases else ""),
            f"{journal.publisher} nashr etadigan" if journal.publisher else "",
            "OAK ro‘yxatidagi ilmiy jurnal" if active else "OAK ro‘yxatidan chiqarilgan ilmiy jurnal",
        ]
        fallback = " ".join(bit for bit in fallback_bits if bit) + "."
        extras = []
        if issn:
            extras.append(f"ISSN {issn}")
        if fields:
            extras.append("Sohalar: " + ", ".join(fields[:4]))
        if total:
            extras.append(f"{total} ta maqola" + (f" ({span})" if span else ""))
        if extras:
            fallback += " " + ". ".join(extras) + "."
        description = summary or fallback

    crumbs = [("Bosh sahifa", "/"), ("Jurnallar", "/jurnallar"), (clip(journal.name, 60), journal_path(slug))]
    if year:
        crumbs.append((str(year), path))
    if page > 1:
        path += f"?sahifa={page}"
        heading += page_suffix

    emails = _dedupe([item.value for item in journal.contacts if item.kind == "email"])[:4]
    phones = _dedupe([item.value for item in journal.contacts if item.kind == "phone"])[:3]
    addresses = _dedupe(
        [item.value for item in journal.contacts if item.kind == "address"]
        + ([profile.address] if profile and profile.address else [])
    )[:1]
    kinds = _dedupe([row.kind for row in registry])
    facts = [
        ("Nashriyot", journal.publisher),
        ("Shahar", city),
        ("ISSN", journal.issn),
        ("e-ISSN", journal.eissn),
        ("Boshqa yozuvda", ", ".join(aliases)),
        ("Tashkil etilgan", journal.founded),
        ("Nashr tillari", ", ".join(journal.languages or [])),
        ("Nashr davriyligi", profile.publication_frequency if profile else None),
        ("Ilmiy sohalari", ", ".join(fields)),
        ("OAK ixtisoslik kodi", ", ".join(_dedupe([f"{row.specialty_code} ({row.area})" if row.area else (row.specialty_code or "") for row in registry]))),
        ("OAK qarori", f"№{decision.decision}" + (f", {decision.added}" if decision.added else "") if decision else None),
        ("Jurnal turi", ", ".join(kinds)),
        ("OAK holati", "Ro‘yxatda" if active else "Ro‘yxatdan chiqarilgan"),
        ("Maqolalar indeksda", f"{total}" + (f" ({span})" if span else "") if total else None),
        ("Ochiq kirish", {"open": "Ha", "mixed": "Qisman"}.get(journal.access)),
        ("Indekslash", ", ".join(_dedupe([item.provider for item in journal.indexing_claims]))),
    ]
    facts_html = "".join(
        f"<tr><th>{e(label)}</th><td>{e(value)}</td></tr>" for label, value in facts if value
    )
    website = web_url(journal.website)
    # Rasmiy sayt — tekshirilgan manba, `nofollow` entity bog'lanishini kuchsizlantiradi.
    site_link = (
        f'<p><a href="{e(website)}" rel="noopener" target="_blank">'
        f"{e(journal.name)} — rasmiy sayti</a></p>" if website else ""
    )

    parts = [
        _crumbs(crumbs),
        f"<h1>{e(heading)}</h1>",
    ]
    if not year:
        if summary:
            parts.append(f'<p class="seo-lead">{e(summary)}</p>')
        else:
            parts.append(f'<p class="seo-lead">{e(description)}</p>')
        if aliases:
            parts.append(f'<p class="seo-alias">Boshqa yozuvda: {e(", ".join(aliases))}</p>')
    parts.append(
        f'<table class="seo-facts"><caption>Jurnal ma’lumotlari</caption><tbody>{facts_html}</tbody></table>'
    )
    # Ilgari drawer (`JournalSheet`) pastida turardi; `/jurnal/{slug}` to'liq
    # sahifaga o'tganda tushib qolgan edi.
    parts.append(
        f'<p class="seo-cta"><a class="seo-button" href="{e(SUBMIT_TELEGRAM_URL)}" '
        'rel="noopener nofollow" target="_blank">Telegram orqali maqola yuborish</a></p>'
    )
    parts.append(site_link)

    if not year:
        aims = (profile.aims_scope if profile else None) or ""
        if aims and aims.strip() != summary_full:
            parts.append("<h2>Maqsad va yo‘nalish</h2>")
            parts.append(f"<p>{e(clip(aims, 1200))}</p>")
        review = (profile.peer_review if profile else None) or ""
        if review:
            parts.append("<h2>Taqriz tartibi</h2>")
            parts.append(f"<p>{e(clip(review, 800))}</p>")
        if journal.sections:
            parts.append("<h2>Jurnal bo‘limlari</h2>")
            parts.append(
                "<ul>" + "".join(f"<li>{e(item.name)}</li>" for item in journal.sections[:20]) + "</ul>"
            )
        if journal.editorial_members:
            parts.append("<h2>Tahririyat</h2>")
            members = []
            for member in journal.editorial_members[:20]:
                detail = " — ".join(bit for bit in [member.role, member.affiliation] if bit)
                members.append(f"<li>{e(member.name)}" + (f" <span class=\"seo-item-meta\">{e(detail)}</span>" if detail else "") + "</li>")
            parts.append("<ul>" + "".join(members) + "</ul>")
        if registry:
            parts.append("<h2>OAK reestri yozuvlari</h2>")
            rows_html = "".join(
                "<tr>"
                f"<td>{e(row.specialty_code)}</td><td>{e(row.area)}</td>"
                f"<td>{e(('№' + row.decision) if row.decision else '')}</td>"
                f"<td>{e(row.added)}</td><td>{e(row.status)}</td><td>{e(row.kind)}</td>"
                "</tr>"
                for row in registry
            )
            parts.append(
                '<table class="seo-facts seo-registry"><thead><tr><th>Ixtisoslik</th><th>Soha</th>'
                "<th>Qaror</th><th>Sana</th><th>Holati</th><th>Turi</th></tr></thead>"
                f"<tbody>{rows_html}</tbody></table>"
            )
        if journal.policies:
            parts.append("<h2>Nashr siyosati</h2>")
            items = []
            for policy in journal.policies[:8]:
                url = web_url(policy.url)
                label = e(policy.title)
                items.append(
                    f'<li><a href="{e(url)}" rel="noopener" target="_blank">{label}</a></li>' if url else f"<li>{label}</li>"
                )
            parts.append("<ul>" + "".join(items) + "</ul>")
        if emails or phones or addresses:
            parts.append("<h2>Aloqa</h2>")
            contact_rows = []
            for value in emails:
                contact_rows.append(f'<tr><th>E-pochta</th><td><a href="mailto:{e(value)}">{e(value)}</a></td></tr>')
            for value in phones:
                contact_rows.append(f"<tr><th>Telefon</th><td>{e(value)}</td></tr>")
            for value in addresses:
                contact_rows.append(f"<tr><th>Manzil</th><td>{e(value)}</td></tr>")
            parts.append(f'<table class="seo-facts"><tbody>{"".join(contact_rows)}</tbody></table>')
        useful = [
            (label, web_url(item.url))
            for item in journal.links
            for label in [{"submission": "Maqola topshirish", "archive": "Arxiv", "editorial": "Tahririyat",
                           "contact": "Aloqa", "website": "Rasmiy sayt"}.get(item.kind)]
            if label and web_url(item.url)
        ]
        seen_labels: dict[str, str] = {}
        for label, url in useful:
            seen_labels.setdefault(label, url)
        if seen_labels:
            parts.append("<h2>Foydali havolalar</h2>")
            parts.append(
                "<ul>" + "".join(
                    f'<li><a href="{e(url)}" rel="noopener" target="_blank">{e(label)}</a></li>'
                    for label, url in seen_labels.items()
                ) + "</ul>"
            )

    if years and not year:
        parts.append("<h2>Yillar bo‘yicha arxiv</h2>")
        parts.append(_chips([(f"{item}-yil ({count})", journal_year_path(slug, item)) for item, count in year_counts]))
    parts.append(f"<h2>{'Maqolalar' if year else 'So‘nggi maqolalar'}</h2>")
    parts.append(
        f'<ul class="seo-list">{"".join(_article_item(item) for item in articles)}</ul>'
        if articles else "<p>Bu jurnal uchun maqolalar hali indekslanmagan.</p>"
    )
    parts.append(_pagination(base, page, selected_total, ARTICLES_PER_PAGE))
    if fields:
        parts.append("<h2>Ilmiy sohalari</h2>")
        parts.append(_chips([(name, field_path(name)) for name in fields]))

    if not year:
        similar = _similar_journals(db, journal)
        if similar:
            parts.append("<h2>Shu sohadagi boshqa OAK jurnallari</h2>")
            parts.append(f'<ul class="seo-list">{"".join(_journal_item(item, count) for item, count in similar)}</ul>')
        faq: list[tuple[str, str]] = []
        if active:
            answer = f"Ha. {journal.name} O‘zbekiston Oliy attestatsiya komissiyasi (OAK) ro‘yxatidagi ilmiy jurnal"
            if decision and decision.decision:
                answer += f" — {decision.decision}-sonli qaror" + (f" ({decision.added})" if decision.added else "")
            if registry and registry[0].area:
                answer += f", ixtisoslik: {registry[0].specialty_code} {registry[0].area}"
            faq.append((f"{journal.name} OAK ro‘yxatida bormi?", answer + "."))
        else:
            faq.append((f"{journal.name} OAK ro‘yxatida bormi?", f"Yo‘q. {journal.name} hozirda OAK ro‘yxatidan chiqarilgan."))
        if issn:
            faq.append((f"{journal.name} ISSN raqami qanday?", f"ISSN {journal.issn or '—'}" + (f", e-ISSN {journal.eissn}" if journal.eissn else "") + "."))
        if journal.publisher:
            faq.append((f"{journal.name} jurnalini kim nashr etadi?", f"{journal.publisher}" + (f" ({city})" if city else "") + "."))
        if fields:
            faq.append((f"{journal.name} qaysi sohalar bo‘yicha maqola qabul qiladi?", "Sohalar: " + ", ".join(fields) + "."))
        if website or emails:
            how = f"Maqola jurnalning rasmiy sayti orqali topshiriladi: {website}" if website else "Tahririyat bilan bog‘laning"
            if emails:
                how += f". E-pochta: {', '.join(emails[:2])}"
            faq.append((f"{journal.name} jurnaliga maqola qanday topshiriladi?", how + "."))
        if faq:
            parts.append("<h2>Ko‘p so‘raladigan savollar</h2>")
            parts.append("".join(f"<h3>{e(q)}</h3><p>{e(a)}</p>" for q, a in faq))
    if city:
        parts.append(f'<p><a href="{e(city_path(city))}">{e(city)} shahridagi boshqa jurnallar</a></p>')

    periodical: dict[str, object] = {
        "@type": "Periodical",
        "@id": absolute(journal_path(slug)) + "#periodical",
        "name": journal.name,
        "url": absolute(journal_path(slug)),
        "inLanguage": [language_code(item) for item in (journal.languages or ["O‘zbek"])],
        "publisher": {"@type": "Organization", "name": journal.publisher, **({"url": website} if website else {})},
    }
    if aliases:
        periodical["alternateName"] = aliases
    identifiers = [item for item in (journal.issn, journal.eissn) if item]
    if identifiers:
        periodical["issn"] = identifiers
        periodical["identifier"] = [
            {"@type": "PropertyValue", "propertyID": "ISSN", "value": item} for item in identifiers
        ]
    same_as = _dedupe(
        ([website] if website else [])
        + [f"https://portal.issn.org/resource/ISSN/{item}" for item in identifiers]
        + [row.link for row in registry if web_url(row.link)]
        + [item.url for item in journal.links if item.kind == "website" and web_url(item.url)]
    )
    if same_as:
        periodical["sameAs"] = same_as if len(same_as) > 1 else same_as[0]
    if summary:
        periodical["description"] = summary
    if journal.founded:
        periodical["foundingDate"] = str(journal.founded)
    if fields:
        periodical["about"] = [{"@type": "Thing", "name": name} for name in fields]
    if journal.editorial_members:
        periodical["editor"] = [
            {"@type": "Person", "name": member.name, **({"jobTitle": member.role} if member.role else {})}
            for member in journal.editorial_members[:10]
        ]
    if emails:
        periodical["contactPoint"] = {"@type": "ContactPoint", "email": emails[0], "contactType": "editorial office"}
    if addresses:
        periodical["address"] = addresses[0]

    jsonld: list[dict] = [periodical, _breadcrumbs(crumbs)]
    if articles:
        jsonld.append(
            _item_list(heading, [(item.title, article_path(item.id, item.title)) for item in articles[:30]])
        )

    head = [f'<meta name="citation_journal_title" content="{e(journal.name)}">']
    if issn:
        head.append(f'<meta name="citation_issn" content="{e(issn)}">')
    head.append(f'<meta name="citation_publisher" content="{e(journal.publisher)}">')

    return PageMeta(
        title=title if not year else clip(title, 90),
        description=clip(description, 158),
        path=path,
        body="".join(parts),
        modified_time=journal.updated_at.isoformat() if journal.updated_at else None,
        jsonld=jsonld,
        head=head,
        lang=_journal_lang(journal),
    )


def _article_list(db: Session, page: int, *, recent: bool = False) -> PageMeta:
    base = "/yangi-maqolalar" if recent else "/maqolalar"
    statement = select(Article).where(Article.is_deleted.is_(False))
    if recent:
        statement = statement.where(Article.harvested_at >= datetime.utcnow() - timedelta(days=14))
    total = (db.scalar(select(func.count()).select_from(statement.subquery())) or 0) if recent else _stats(db)[1]
    if page > max(1, -(-total // ARTICLES_PER_PAGE)):
        return _not_found(f"{base}?sahifa={page}")
    articles = feed.page(
        db,
        statement.options(selectinload(Article.journal)),
        offset=(page - 1) * ARTICLES_PER_PAGE,
        limit=ARTICLES_PER_PAGE,
    )
    heading = "So‘nggi 14 kunda indeksga qo‘shilgan maqolalar" if recent else "O‘zbekiston ilmiy maqolalari bazasi"
    description = (
        f"OAK jurnallaridan yig‘ilgan {total} ta ilmiy maqola: sarlavha, mualliflar, "
        "annotatsiya, kalit so‘zlar, DOI va tayyor iqtibos formatlari."
    )
    crumbs = [("Bosh sahifa", "/"), ("Yangi maqolalar" if recent else "Maqolalar", base)]
    path = base if page == 1 else f"{base}?sahifa={page}"
    suffix = f" — {page}-sahifa" if page > 1 else ""
    body = (
        _crumbs(crumbs)
        + f"<h1>{e(heading)}{e(suffix)}</h1>"
        + f'<p class="seo-lead">{e(description)}</p>'
        + f'<ul class="seo-list">{"".join(_article_item(item) for item in articles)}</ul>'
        + _pagination(base, page, total, ARTICLES_PER_PAGE)
    )
    return PageMeta(
        title=clip(f"{'Yangi maqolalar' if recent else 'Ilmiy maqolalar bazasi'} — {total} ta maqola{suffix}", 65),
        description=clip(description, 158),
        path=path,
        body=body,
        jsonld=[
            {
                "@type": "CollectionPage",
                "url": absolute(path),
                "name": heading,
                "description": description,
                "inLanguage": DEFAULT_LANG,
                "isPartOf": {"@id": absolute("/#website")},
                "mainEntity": _item_list(
                    heading, [(item.title, article_path(item.id, item.title)) for item in articles]
                ),
            },
            _breadcrumbs(crumbs),
        ],
    )


def _article_page(db: Session, article_id: int, requested_path: str) -> PageMeta:
    article = db.scalar(
        select(Article).where(Article.id == article_id).options(selectinload(Article.journal))
    )
    if article is None or article.is_deleted:
        return _not_found(requested_path)

    journal = article.journal
    canonical_path = article_path(article.id, article.title)
    # Sarlavha o'zgarsa eski slug ham ishlashi kerak, lekin indeksda bitta
    # kanonik URL qolsin — shuning uchun 301.
    if requested_path != canonical_path:
        return PageMeta(title="", description="", path=canonical_path, status=301, redirect=canonical_path)

    authors = article.authors or []
    when = publication_date(article.publication_date, article.publication_year)
    year = article.publication_year
    lang = language_code(article.language)
    abstract = (article.abstract or "").strip()
    keywords = article.keywords or []

    # Sarlavha to'liq (so'rov aynan shu), keyin jurnal va yil — sayt nomi emas:
    # brend `og:site_name` da, <title> dagi har belgi esa relevantlik.
    journal_tail = f" — {journal.name}" + (f", {year}" if year else "") if journal else ""
    title = (article.title if len(article.title) <= 120 else clip(article.title, 120)) + journal_tail
    if not abstract:
        bits = [", ".join(authors[:4]) + (" va b." if len(authors) > 4 else "")] if authors else []
        if journal:
            bits.append(f"{journal.name}" + (f" ({year})" if year else "") + " jurnalida chop etilgan ilmiy maqola")
        location = ", ".join(part for part in [f"jild {article.volume}" if article.volume else "", f"{article.issue}-son" if article.issue else "", f"{article.pages}-betlar" if article.pages else ""] if part)
        if location:
            bits.append(location)
        if keywords:
            bits.append("Kalit so‘zlar: " + ", ".join(keywords[:6]))
        description = clip(". ".join(bit for bit in bits if bit) + ".", 158)
    else:
        description = clip(abstract, 158)

    crumbs = [("Bosh sahifa", "/"), ("Maqolalar", "/maqolalar")]
    if journal:
        crumbs.append((clip(journal.name, 50), journal_path(journal.slug)))
        if year:
            crumbs.append((f"{year}", journal_year_path(journal.slug, year)))
    crumbs.append((clip(article.title, 60), canonical_path))

    facts = [
        ("Mualliflar", ", ".join(authors)),
        ("Jurnal", journal.name if journal else None),
        ("Nashriyot", journal.publisher if journal else None),
        ("ISSN", ", ".join(item for item in ((journal.issn, journal.eissn) if journal else ()) if item)),
        ("Nashr sanasi", when or (str(year) if year else None)),
        ("Jild", article.volume),
        ("Son", article.issue),
        ("Betlar", article.pages),
        ("Til", article.language),
        ("Ilmiy soha", ", ".join(article.fields or [])),
        ("DOI", article.doi),
        ("Indeksga qo‘shilgan", article.harvested_at.date().isoformat() if article.harvested_at else None),
    ]
    facts_html = "".join(
        f"<tr><th>{e(label)}</th><td>{e(value)}</td></tr>" for label, value in facts if value
    )

    landing, pdf = web_url(article.landing_url), web_url(article.pdf_url)
    links = []
    if article.doi:
        links.append(f'<a href="https://doi.org/{e(article.doi)}" rel="nofollow noopener">DOI: {e(article.doi)}</a>')
    if landing:
        links.append(f'<a href="{e(landing)}" rel="nofollow noopener">Maqolaning asl sahifasi</a>')
    if pdf:
        links.append(f'<a href="{e(pdf)}" rel="nofollow noopener">PDF</a>')

    parts = [
        _crumbs(crumbs),
        f"<h1>{e(article.title)}</h1>",
    ]
    if authors:
        parts.append(f'<p class="seo-authors">{e(", ".join(authors))}</p>')
    if journal:
        journal_line = f'<a href="{e(journal_path(journal.slug))}">{e(journal.name)}</a>'
        if year:
            journal_line += f' · <a href="{e(journal_year_path(journal.slug, year))}">{year}-yil</a>'
        parts.append(f'<p class="seo-item-meta">{journal_line}</p>')
    if abstract:
        parts.append("<h2>Annotatsiya</h2>")
        parts.append(f"<p>{e(abstract)}</p>")
    parts.append(f'<table class="seo-facts"><caption>Maqola ma’lumotlari</caption><tbody>{facts_html}</tbody></table>')
    if links:
        parts.append(f'<p class="seo-links">{" · ".join(links)}</p>')
    if keywords:
        parts.append("<h2>Kalit so‘zlar</h2>")
        parts.append(f'<p>{e(", ".join(keywords))}</p>')
    if article.fields:
        parts.append("<h2>Ilmiy soha</h2>")
        parts.append(_chips([(name, field_path(name)) for name in article.fields]))

    # Iqtibos formatlari — matn sifatida: dissertatsiya yozuvchilar aynan
    # «maqola iqtibos GOST» deb qidiradi; frontend ham shu formatlarni beradi.
    if journal:
        formats = citation_formats(article)
        parts.append("<h2>Iqtibos keltirish</h2>")
        rows_html = "".join(
            f"<tr><th>{e(CITATION_LABELS.get(key, key.upper()))}</th><td>"
            + (f"<pre>{e(value)}</pre>" if key == "bibtex" else e(value))
            + "</td></tr>"
            for key, value in formats.items()
        )
        parts.append(f'<table class="seo-facts seo-cite"><tbody>{rows_html}</tbody></table>')

    # Qo'shni maqolalarga havola — 104 809 ta yozuvning aksari sitemap'dan
    # tashqari hech qayerdan bog'lanmagan bo'lardi, ya'ni orfan sahifa.
    # Ikki tomonlama 5 tadan: `abs(id - x)` bo'yicha saralash katta jurnalda
    # (15 ming maqola) butun ro'yxatni saralardi.
    if journal:
        base_query = (
            select(Article)
            .options(selectinload(Article.journal))
            .where(Article.journal_id == journal.id, Article.is_deleted.is_(False))
        )
        before = db.scalars(base_query.where(Article.id < article.id).order_by(Article.id.desc()).limit(5)).all()
        after = db.scalars(base_query.where(Article.id > article.id).order_by(Article.id.asc()).limit(5)).all()
        siblings = list(reversed(before)) + after
        if siblings:
            parts.append(f"<h2>{e(journal.name)} jurnalidan boshqa maqolalar</h2>")
            parts.append(f'<ul class="seo-list">{"".join(_article_item(item) for item in siblings)}</ul>')
        parts.append(
            f'<p><a href="{e(journal_path(journal.slug))}">{e(journal.name)} — barcha maqolalar</a>'
            + (f' · <a href="{e(journal_year_path(journal.slug, year))}">{year}-yil arxivi</a>' if year else "")
            + "</p>"
        )

    # Muallifning boshqa maqolalari — FTS indeksi bo'lsa (prodda bor).
    # Muallif nomi kirill/lotin farqisiz normallashtirilgan `search_text`da.
    if authors and search_index.available(db):
        expression = search_index.match_expression(authors[0])
        if expression:
            by_author = db.scalars(
                search_index.apply(
                    select(Article).options(selectinload(Article.journal))
                    .where(Article.is_deleted.is_(False), Article.id != article.id),
                    expression,
                ).limit(6)
            ).all()
            if by_author:
                parts.append(f"<h2>{e(authors[0])} — boshqa maqolalari</h2>")
                parts.append(f'<ul class="seo-list">{"".join(_article_item(item) for item in by_author)}</ul>')

    # Shu sohadagi boshqa jurnallarning so'nggi maqolalari — soha bo'yicha
    # bog'lanish, orfanlikni kamaytiradi.
    if article.fields:
        field_ids = _journal_ids_for(db, field=article.fields[0]) or set()
        field_ids.discard(journal.id if journal else -1)
        if field_ids:
            related = feed.page(
                db,
                select(Article).options(selectinload(Article.journal))
                .where(Article.journal_id.in_(field_ids), Article.is_deleted.is_(False)),
                limit=6,
            )
            if related:
                parts.append(f"<h2>{e(article.fields[0])} sohasidagi boshqa maqolalar</h2>")
                parts.append(f'<ul class="seo-list">{"".join(_article_item(item) for item in related)}</ul>')
                parts.append(f'<p><a href="{e(field_path(article.fields[0]))}">{e(article.fields[0])} sohasidagi OAK jurnallari</a></p>')

    scholarly: dict[str, object] = {
        "@type": "ScholarlyArticle",
        "@id": absolute(canonical_path) + "#article",
        "url": absolute(canonical_path),
        "headline": clip(article.title, 110),
        "name": article.title,
        "inLanguage": lang,
        "isAccessibleForFree": True,
        "mainEntityOfPage": absolute(canonical_path),
        "author": [{"@type": "Person", "name": name} for name in authors] or None,
    }
    if article.updated_at:
        scholarly["dateModified"] = article.updated_at.date().isoformat()
    if abstract:
        scholarly["abstract"] = clip(abstract, 5000)
        scholarly["description"] = clip(abstract, 300)
    if when:
        scholarly["datePublished"] = when
    elif year:
        scholarly["datePublished"] = str(year)
    if keywords:
        scholarly["keywords"] = keywords
    if article.fields:
        scholarly["about"] = [{"@type": "Thing", "name": name} for name in article.fields]
    if article.pages:
        scholarly["pagination"] = article.pages
    if article.doi:
        scholarly["sameAs"] = f"https://doi.org/{article.doi}"
        scholarly["identifier"] = {
            "@type": "PropertyValue", "propertyID": "DOI", "value": article.doi,
        }
    if journal:
        periodical = {
            "@type": "Periodical",
            "@id": absolute(journal_path(journal.slug)) + "#periodical",
            "name": journal.name,
            "url": absolute(journal_path(journal.slug)),
        }
        issns = [item for item in (journal.issn, journal.eissn) if item]
        if issns:
            periodical["issn"] = issns
        container: dict[str, object] = periodical
        if article.volume and article.volume != "—":
            container = {"@type": "PublicationVolume", "volumeNumber": article.volume, "isPartOf": container}
        if article.issue and article.issue != "—":
            container = {"@type": "PublicationIssue", "issueNumber": article.issue, "isPartOf": container}
        scholarly["isPartOf"] = container
        publisher_site = web_url(journal.website)
        scholarly["publisher"] = {"@type": "Organization", "name": journal.publisher, **({"url": publisher_site} if publisher_site else {})}
    scholarly = {key: value for key, value in scholarly.items() if value is not None}

    # Google Scholar va akademik indekslar aynan shu prefiksni o'qiydi.
    head = [f'<meta name="citation_title" content="{e(article.title)}">']
    head += [f'<meta name="citation_author" content="{e(name)}">' for name in authors]
    if when:
        head.append(f'<meta name="citation_publication_date" content="{e(when.replace("-", "/"))}">')
    elif year:
        head.append(f'<meta name="citation_publication_date" content="{year}">')
    if journal:
        head.append(f'<meta name="citation_journal_title" content="{e(journal.name)}">')
        head.append(f'<meta name="citation_publisher" content="{e(journal.publisher)}">')
        if journal.issn:
            head.append(f'<meta name="citation_issn" content="{e(journal.issn)}">')
    for name, value in (
        ("citation_volume", article.volume), ("citation_issue", article.issue),
        ("citation_doi", article.doi), ("citation_language", lang),
    ):
        if value and value != "—":
            head.append(f'<meta name="{name}" content="{e(value)}">')
    if article.pages and article.pages != "—":
        bounds = re.split(r"[-–—]", article.pages)
        head.append(f'<meta name="citation_firstpage" content="{e(bounds[0].strip())}">')
        if len(bounds) > 1 and bounds[-1].strip():
            head.append(f'<meta name="citation_lastpage" content="{e(bounds[-1].strip())}">')
    head.append(f'<meta name="citation_abstract_html_url" content="{e(absolute(canonical_path))}">')
    # Scholar only accepts a PDF in the same origin/subdirectory as its abstract.
    # External publisher PDFs remain visible links, not misleading Scholar tags.
    if pdf and urlsplit(pdf).netloc == urlsplit(absolute(canonical_path)).netloc and urlsplit(pdf).path.startswith(urlsplit(canonical_path).path.rsplit("/", 1)[0] + "/"):
        head.append(f'<meta name="citation_pdf_url" content="{e(pdf)}">')
    if abstract:
        head.append(f'<meta name="citation_abstract" content="{e(abstract)}">')
    if keywords:
        head.append(f'<meta name="citation_keywords" content="{e("; ".join(keywords))}">')
    # Dublin Core — Yandex va repozitoriy agregatorlari uchun.
    head.append(f'<meta name="DC.title" content="{e(article.title)}">')
    head += [f'<meta name="DC.creator" content="{e(name)}">' for name in authors]
    head.append(f'<meta name="DC.type" content="Text.Article">')
    head.append(f'<meta name="DC.language" content="{e(lang)}">')
    if when or year:
        head.append(f'<meta name="DC.date" content="{e(when or year)}">')
    if journal:
        head.append(f'<meta name="DC.source" content="{e(journal.name)}">')
    if article.doi:
        head.append(f'<meta name="DC.identifier" content="https://doi.org/{e(article.doi)}">')

    return PageMeta(
        title=title,
        description=description,
        path=canonical_path,
        body="".join(parts),
        og_type="article",
        published_time=when or (str(year) if year else None),
        modified_time=article.updated_at.isoformat() if article.updated_at else None,
        jsonld=[scholarly, _breadcrumbs(crumbs)],
        head=head,
        lang=lang,
        data={
            "kind": "article",
            "article": article_payload(article),
            # React'dagi "Shu jurnaldan" bloki — `/api/articles?journal_slug=`
            # so'rovisiz; qo'shnilar allaqachon shu sahifada.
            "related": [article_payload(item) for item in siblings[:5]] if journal else [],
        },
    )


def _fields_index(db: Session) -> PageMeta:
    counts = _counts(db)
    rows = []
    for group, names in FIELD_GROUPS:
        entries = []
        for name in names:
            ids = _journal_ids_for(db, field=name) or set()
            entries.append((name, len(ids), sum(counts.get(item, 0) for item in ids)))
        rows.append((group, entries))

    parts = [
        _crumbs([("Bosh sahifa", "/"), ("Sohalar", "/sohalar")]),
        "<h1>Ilmiy sohalar bo‘yicha OAK jurnallari</h1>",
        '<p class="seo-lead">OAK ro‘yxatidagi jurnallar 24 ta fan yo‘nalishi bo‘yicha '
        "guruhlangan. Har bir sohaning jurnallari va maqolalarini alohida ko‘ring.</p>",
    ]
    for group, entries in rows:
        parts.append(f"<h2>{e(group)}</h2><ul class='seo-list'>")
        for name, journals, articles in entries:
            parts.append(
                f'<li class="seo-item"><a class="seo-item-title" href="{e(field_path(name))}">{e(name)}</a>'
                f'<p class="seo-item-meta">{journals} ta jurnal · {articles} ta maqola</p></li>'
            )
        parts.append("</ul>")

    return PageMeta(
        title="Ilmiy sohalar — OAK jurnallari yo‘nalishlari bo‘yicha",
        description=(
            "OAK ro‘yxatidagi ilmiy jurnallarni fan yo‘nalishi bo‘yicha ko‘ring: tibbiyot, "
            "pedagogika, iqtisodiyot, filologiya, texnika, yuridik va boshqa 24 ta soha."
        ),
        path="/sohalar",
        body="".join(parts),
        jsonld=[
            _breadcrumbs([("Bosh sahifa", "/"), ("Sohalar", "/sohalar")]),
            _item_list("Ilmiy sohalar", [(name, field_path(name)) for name in all_fields()]),
        ],
    )


def _cities_index(db: Session) -> PageMeta:
    counts = _counts(db)
    entries = []
    for name in cities(db):
        ids = _journal_ids_for(db, city=name) or set()
        entries.append((name, len(ids), sum(counts.get(item, 0) for item in ids)))
    entries.sort(key=lambda row: -row[1])

    items = "".join(
        f'<li class="seo-item"><a class="seo-item-title" href="{e(city_path(name))}">{e(name)}</a>'
        f'<p class="seo-item-meta">{journals} ta jurnal · {articles} ta maqola</p></li>'
        for name, journals, articles in entries
    )
    return PageMeta(
        title="Shaharlar bo‘yicha OAK jurnallari — O‘zbekiston",
        description=(
            "O‘zbekiston shaharlari bo‘yicha OAK ro‘yxatidagi ilmiy jurnallar: Toshkent, "
            "Samarqand, Buxoro, Namangan, Farg‘ona, Nukus va boshqalar."
        ),
        path="/shaharlar",
        body=(
            _crumbs([("Bosh sahifa", "/"), ("Shaharlar", "/shaharlar")])
            + "<h1>Shaharlar bo‘yicha OAK jurnallari</h1>"
            + '<p class="seo-lead">Jurnal qaysi shaharda nashr etilishiga qarab tanlang.</p>'
            + f'<ul class="seo-list">{items}</ul>'
        ),
        jsonld=[
            _breadcrumbs([("Bosh sahifa", "/"), ("Shaharlar", "/shaharlar")]),
            _item_list("Shaharlar", [(name, city_path(name)) for name, _, _ in entries]),
        ],
    )


def _search_page(db: Session, query: str) -> PageMeta:
    """Qidiruv natijalari indekslanmaydi — cheksiz ko‘p va sifatsiz URL beradi."""
    articles = []
    if query.strip():
        from .search_text import LIKE_ESCAPE, escape_like, query_words

        statement = (
            select(Article)
            .options(selectinload(Article.journal))
            .where(Article.is_deleted.is_(False))
        )
        for word in query_words(query):
            statement = statement.where(
                Article.search_text.like(f"%{escape_like(word)}%", escape=LIKE_ESCAPE)
            )
        articles = feed.page(db, statement, limit=20)

    heading = f"{e(query)} — qidiruv natijalari" if query else "Qidiruv"
    body = _crumbs([("Bosh sahifa", "/"), ("Qidiruv", "/qidiruv")]) + f"<h1>{heading}</h1>"
    if articles:
        body += f'<ul class="seo-list">{"".join(_article_item(item) for item in articles)}</ul>'
    elif query:
        body += "<p>Bu so‘rov bo‘yicha maqola topilmadi.</p>"
    return PageMeta(
        title=clip(f"{query} — qidiruv | {SITE_NAME}" if query else f"Qidiruv | {SITE_NAME}", 65),
        description=clip(f"“{query}” bo‘yicha OAK jurnallari va maqolalari qidiruvi.", 158),
        path="/qidiruv",
        body=body,
        robots=NOINDEX,
    )


def _about_page(db: Session) -> PageMeta:
    journals, articles = _stats(db)
    body = (
        _crumbs([("Bosh sahifa", "/"), ("Loyiha haqida", "/loyiha")])
        + "<h1>IlmIz loyihasi haqida</h1>"
        + '<p class="seo-lead">IlmIz — O‘zbekiston Oliy attestatsiya komissiyasi (OAK) '
        "ro‘yxatidagi ilmiy jurnallar va ularda chop etilgan maqolalarning ochiq indeksi.</p>"
        + "<h2>Indeks nimadan iborat</h2>"
        + f"<ul><li>{journals} ta OAK jurnali profili: ISSN, nashriyot, tahririyat, "
        "nashr siyosatlari va OAK qarorlari</li>"
        + f"<li>{articles} ta maqola metama’lumoti: mualliflar, annotatsiya, kalit so‘zlar, "
        "DOI va to‘liq matn havolasi</li>"
        + "<li>Har bir maydonning manbasi va olingan vaqti saqlanadi</li></ul>"
        + "<h2>Ma’lumot qayerdan olinadi</h2>"
        + "<p>Jurnal metama’lumotlari OAK rasmiy elektron reestridan, maqolalar esa "
        "jurnal repozitoriylaridan OAI-PMH 2.0 protokoli orqali muntazam yig‘iladi. "
        "Faqat o‘zgargan yozuvlar olinadi, shuning uchun indeks eskirmaydi.</p>"
        + "<h2>Foydalanish</h2>"
        + '<p>Qidiruv va metama’lumotlar barcha uchun bepul. <a href="/jurnallar">Jurnallar</a>, '
        '<a href="/maqolalar">maqolalar</a>, <a href="/sohalar">sohalar</a> va '
        '<a href="/shaharlar">shaharlar</a> bo‘limlaridan boshlang.</p>'
    )
    return PageMeta(
        title="Loyiha haqida — IlmIz OAK jurnallari indeksi",
        description=(
            "IlmIz qanday ishlaydi: OAK reestri va OAI-PMH orqali yig‘iladigan ochiq ilmiy "
            "indeks, manba provenance’i va bepul foydalanish shartlari."
        ),
        path="/loyiha",
        body=body,
        jsonld=[
            _breadcrumbs([("Bosh sahifa", "/"), ("Loyiha haqida", "/loyiha")]),
            {
                "@type": "AboutPage",
                "url": absolute("/loyiha"),
                "name": "IlmIz loyihasi haqida",
                "inLanguage": DEFAULT_LANG,
                "isPartOf": {"@id": absolute("/#website")},
            },
        ],
    )


def _privacy_page() -> PageMeta:
    """`/maxfiylik` — maxfiylik siyosati.

    Google OAuth ilovasi "Production" holatida shu manzilning ochiq
    bo'lishini talab qiladi, shuning uchun sahifa crawler'ga ham
    JavaScript'siz ko'rinishi kerak.
    """
    body = (
        _crumbs([("Bosh sahifa", "/"), ("Maxfiylik siyosati", "/maxfiylik")])
        + "<h1>Maxfiylik siyosati</h1>"
        + '<p class="seo-lead">Saytdan foydalanish uchun ro‘yxatdan o‘tish shart emas. '
        "Quyida qaysi ma’lumot, nima uchun va qancha muddat saqlanishi yozilgan.</p>"
        + "<h2>Kirmasdan foydalanganda</h2>"
        + "<p>Qidiruv, jurnal va maqola sahifalari hisobsiz ochiladi; shaxsiy ma’lumot "
        "saqlanmaydi. Veb-server odatiy texnik jurnal yuritadi — u faqat nosozliklarni "
        "aniqlash va suiiste’molning oldini olish uchun kerak.</p>"
        + "<h2>ORCID yoki Google orqali kirganda</h2>"
        + "<p>Parol so‘ralmaydi va saqlanmaydi. Provayder qaytargan maydonlar saqlanadi: "
        "provayder nomi va identifikator, ORCID iD, elektron pochta, ko‘rsatiladigan ism, "
        "ish joyi (ROR identifikatori bilan) hamda hisob yaratilgan va oxirgi kirilgan vaqt. "
        "Ish joyi qidiruvidagi matn server orqali ror.org registriga yuboriladi. ORCID orqali "
        "kirganda, ish joyi qo‘lda kiritilmagan bo‘lsa, ORCID yozuvidagi ochiq joriy ish joyidan olinadi.</p>"
        + "<h2>Sessiya va cookie</h2>"
        + "<p>Bitta <code>ilmiz_session</code> cookie qo‘yiladi: HttpOnly, SameSite=Lax, "
        "HTTPS’da Secure, muddati 30 kun. Serverda tokenning o‘zi emas, SHA-256 hash’i "
        "saqlanadi.</p>"
        + "<h2>Nima qilmaymiz</h2>"
        + "<ul><li>Reklama ko‘rsatmaymiz</li>"
        "<li>Kuzatuv va analitika skriptlari ishlatmaymiz</li>"
        "<li>Ma’lumotlaringizni sotmaymiz</li>"
        "<li>Parolingizni ko‘rmaymiz va saqlamaymiz</li></ul>"
        + "<h2>Sizning huquqlaringiz</h2>"
        + "<p>Chiqish tugmasi sessiyani serverda bekor qiladi; tasdiqlagan maqolalaringizni "
        "istalgan vaqt olib tashlashingiz mumkin; hisobni butunlay o‘chirishni so‘rasangiz, "
        "unga bog‘langan barcha yozuvlar bilan o‘chiramiz.</p>"
        + "<h2>Aloqa</h2>"
        + '<p><a href="mailto:info@ilmiz.uz">info@ilmiz.uz</a></p>'
    )
    return PageMeta(
        title="Maxfiylik siyosati — IlmIz",
        description=(
            "IlmIz qanday ma’lumot saqlaydi: ORCID va Google orqali kirish, sessiya, "
            "o‘zlashtirilgan maqolalar. Reklama va kuzatuv skriptlari yo‘q."
        ),
        path="/maxfiylik",
        body=body,
        jsonld=[_breadcrumbs([("Bosh sahifa", "/"), ("Maxfiylik siyosati", "/maxfiylik")])],
    )


def _terms_page() -> PageMeta:
    """`/shartlar` — foydalanish shartlari."""
    body = (
        _crumbs([("Bosh sahifa", "/"), ("Foydalanish shartlari", "/shartlar")])
        + "<h1>Foydalanish shartlari</h1>"
        + '<p class="seo-lead">Saytdan foydalanish shu shartlarni qabul qilishni bildiradi.</p>'
        + "<h2>Xizmat nima</h2>"
        + "<p>IlmIz — OAK ro‘yxatidagi ilmiy jurnallar va maqolalarning qidiruv indeksi. "
        "Qidiruv va metama’lumotlar barcha uchun bepul.</p>"
        + "<h2>Metama’lumot va mualliflik huquqi</h2>"
        + "<p>To‘liq matnlar saqlanmaydi va tarqatilmaydi — faqat metama’lumot va "
        "nashriyot sahifasiga havola ko‘rsatiladi. Huquqlar mualliflar va nashriyotlarda "
        "qoladi. Rasmiy OAK holati uchun birlamchi manba — OAK reestrining o‘zi.</p>"
        + "<h2>Hisob va maqolalarni o‘zlashtirish</h2>"
        + "<p>Profilingizga faqat o‘zingiz muallif bo‘lgan maqolalarni qo‘shing. "
        "Soxta o‘zlashtirish aniqlansa, yozuvlar olib tashlanadi va hisob to‘xtatilishi "
        "mumkin.</p>"
        + "<h2>Kafolatlar</h2>"
        + "<p>Xizmat “borligicha” taqdim etiladi. Rasmiy qarorlar uchun birlamchi "
        "manbalarga tayaning.</p>"
        + "<h2>Aloqa</h2>"
        + '<p><a href="mailto:info@ilmiz.uz">info@ilmiz.uz</a> · '
        '<a href="/maxfiylik">Maxfiylik siyosati</a></p>'
    )
    return PageMeta(
        title="Foydalanish shartlari — IlmIz",
        description=(
            "IlmIz’dan foydalanish shartlari: bepul kirish, metama’lumot manbalari, "
            "hisob va maqolalarni o‘zlashtirish qoidalari."
        ),
        path="/shartlar",
        body=body,
        jsonld=[_breadcrumbs([("Bosh sahifa", "/"), ("Foydalanish shartlari", "/shartlar")])],
    )


def _not_found(path: str) -> PageMeta:
    return PageMeta(
        title="Sahifa topilmadi — IlmIz",
        description="So‘ralgan sahifa mavjud emas.",
        path=path,
        robots=NOINDEX,
        status=404,
        body=(
            "<h1>Sahifa topilmadi</h1>"
            "<p>Bunday manzil indeksda yo‘q. "
            '<a href="/jurnallar">Jurnallar</a>, <a href="/maqolalar">maqolalar</a> yoki '
            '<a href="/">bosh sahifa</a>ga o‘ting.</p>'
        ),
    )


# ------------------------------------------------------------------ marshrutlash

_ARTICLE_PATH = re.compile(r"^/maqola/(\d+)(?:-[^/]*)?$")
_JOURNAL_PATH = re.compile(r"^/jurnal/([^/]+)(?:/(\d{4}))?$")
_FIELD_PATH = re.compile(r"^/soha/([^/]+)$")
_CITY_PATH = re.compile(r"^/shahar/([^/]+)$")


def _page_number(params: dict[str, str]) -> int:
    raw = params.get("sahifa") or params.get("page") or "1"
    try:
        return max(1, min(int(raw), 5000))
    except ValueError:
        return 1


def build_page(db: Session, path: str, params: dict[str, str] | None = None) -> PageMeta:
    """URL ni serverda tayyorlangan SEO sahifasiga aylantiradi."""
    params = params or {}
    path = "/" + path.strip("/") if path.strip("/") else "/"
    page = _page_number(params)

    if path == "/":
        return _home(db)
    if path == "/jurnallar":
        return _journal_list(db, page)
    if path == "/maqolalar":
        return _article_list(db, page)
    if path == "/yangi-maqolalar":
        return _article_list(db, page, recent=True)
    if path == "/sohalar":
        return _fields_index(db)
    if path == "/shaharlar":
        return _cities_index(db)
    if path == "/loyiha":
        return _about_page(db)
    if path == "/maxfiylik":
        return _privacy_page()
    if path == "/shartlar":
        return _terms_page()
    if path == "/qidiruv":
        return _search_page(db, params.get("q", ""))

    match = _ARTICLE_PATH.match(path)
    if match:
        return _article_page(db, int(match.group(1)), path)

    match = _JOURNAL_PATH.match(path)
    if match:
        year = int(match.group(2)) if match.group(2) else None
        return _journal_page(db, match.group(1), year, page)

    match = _FIELD_PATH.match(path)
    if match:
        name = field_by_slug(db, match.group(1))
        return _journal_list(db, page, field=name) if name else _not_found(path)

    match = _CITY_PATH.match(path)
    if match:
        name = city_by_slug(db, match.group(1))
        return _journal_list(db, page, city=name) if name else _not_found(path)

    return _not_found(path)


# --------------------------------------------------------------- HTML qobiq

CRITICAL_CSS = """
#root .seo-shell{max-width:52rem;margin:0 auto;padding:2.5rem 1.25rem 4rem;
font:400 16px/1.65 ui-sans-serif,system-ui,'Segoe UI',sans-serif;color:#18181b}
@media(prefers-color-scheme:dark){#root .seo-shell{color:#e4e4e7}}
#root .seo-shell h1{font-size:1.85rem;line-height:1.25;margin:0 0 .75rem;letter-spacing:-.02em}
#root .seo-shell h2{font-size:1.2rem;margin:2rem 0 .6rem;letter-spacing:-.01em}
#root .seo-shell a{color:#2563eb;text-decoration:none}
#root .seo-shell a:hover{text-decoration:underline}
#root .seo-lead{font-size:1.05rem;opacity:.85;margin:0 0 1.25rem}
#root .seo-alias{font-size:.9rem;opacity:.7;margin:-.75rem 0 1rem}
#root .seo-registry th{width:auto;white-space:normal}
#root .seo-registry td{padding-right:.6rem;font-size:.85rem}
#root .seo-shell h3{font-size:1rem;margin:1.1rem 0 .3rem}
#root .seo-cite th{width:7rem}
#root .seo-cite pre{white-space:pre-wrap;font-size:.8rem;margin:0}
#root .seo-crumbs{font-size:.8rem;opacity:.7;margin-bottom:1rem}
#root .seo-sep{margin:0 .4rem;opacity:.5}
#root .seo-list{list-style:none;margin:0;padding:0}
#root .seo-item{padding:.85rem 0;border-bottom:1px solid rgba(128,128,128,.22)}
#root .seo-item-title{font-weight:600;font-size:1rem}
#root .seo-item-meta{margin:.25rem 0 0;font-size:.82rem;opacity:.7}
#root .seo-item-abstract{margin:.4rem 0 0;font-size:.88rem;opacity:.8}
#root .seo-authors{font-size:.95rem;opacity:.85;margin:0 0 .5rem}
#root .seo-facts{width:100%;border-collapse:collapse;margin:1.25rem 0;font-size:.9rem}
#root .seo-facts caption{text-align:left;font-weight:600;padding-bottom:.5rem}
#root .seo-facts th{text-align:left;font-weight:500;opacity:.7;padding:.4rem .75rem .4rem 0;
white-space:nowrap;vertical-align:top;width:11rem}
#root .seo-facts td{padding:.4rem 0;border-bottom:1px solid rgba(128,128,128,.18)}
#root .seo-chips{display:flex;flex-wrap:wrap;gap:.4rem;margin:.5rem 0 1rem}
#root .seo-chip{border:1px solid rgba(128,128,128,.35);border-radius:999px;
padding:.2rem .7rem;font-size:.82rem}
#root .seo-pager{display:flex;gap:.6rem;flex-wrap:wrap;margin:1.5rem 0;font-size:.9rem}
#root .seo-cta{margin:1.25rem 0 .5rem}
#root .seo-shell a.seo-button{display:inline-flex;align-items:center;gap:.5rem;
padding:.6rem 1.1rem;border-radius:.5rem;font-weight:600;font-size:.95rem;
background:var(--primary,#1f5f4a);color:var(--primary-foreground,#fff)}
#root .seo-shell a.seo-button:hover{text-decoration:none;opacity:.92}
""".strip()


def effective_robots(meta: PageMeta) -> str:
    """Prod bo'lmagan hostda hech narsa indekslanmaydi."""
    return meta.robots if is_production_host() else NOINDEX


def render_head(meta: PageMeta) -> str:
    """`<head>` ichiga qo'yiladigan hamma narsa."""
    lines = [
        f'<meta name="ilmiz-route" content="{e(meta.path)}">',
        f"<title>{e(meta.title)}</title>",
        f'<meta name="description" content="{e(meta.description)}">',
        f'<link rel="canonical" href="{e(meta.canonical)}">',
        f'<meta name="robots" content="{e(effective_robots(meta))}">',
        f'<link rel="alternate" hreflang="{e(meta.lang)}" href="{e(meta.canonical)}">',
        f'<link rel="alternate" hreflang="x-default" href="{e(meta.canonical)}">',
        f'<meta property="og:type" content="{e(meta.og_type)}">',
        f'<meta property="og:site_name" content="{SITE_NAME}">',
        f'<meta property="og:locale" content="{e(LOCALES.get(meta.lang, DEFAULT_LOCALE))}">',
        f'<meta property="og:title" content="{e(meta.title)}">',
        f'<meta property="og:description" content="{e(meta.description)}">',
        f'<meta property="og:url" content="{e(meta.canonical)}">',
        f'<meta property="og:image" content="{e(absolute("/og-image.png"))}">',
        f'<meta property="og:image:alt" content="{e(meta.title)}">',
        '<meta property="og:image:width" content="1200">',
        '<meta property="og:image:height" content="630">',
        '<meta name="twitter:card" content="summary_large_image">',
        f'<meta name="twitter:title" content="{e(meta.title)}">',
        f'<meta name="twitter:description" content="{e(meta.description)}">',
        f'<meta name="twitter:image" content="{e(absolute("/og-image.png"))}">',
    ]
    if meta.published_time:
        lines.append(f'<meta property="article:published_time" content="{e(meta.published_time)}">')
    if meta.modified_time:
        lines.append(f'<meta property="article:modified_time" content="{e(meta.modified_time)}">')
    for key, env in (("google-site-verification", "GOOGLE_SITE_VERIFICATION"),
                     ("yandex-verification", "YANDEX_VERIFICATION"),
                     ("msvalidate.01", "BING_SITE_VERIFICATION")):
        value = os.getenv(env, "").strip()
        if value:
            lines.append(f'<meta name="{key}" content="{e(value)}">')
    lines += meta.head
    graph = [{"@context": "https://schema.org", **item} for item in meta.jsonld]
    for item in graph:
        payload = json.dumps(item, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
        lines.append(f'<script type="application/ld+json">{payload}</script>')
    lines.append(f'<style data-ilmiz-critical>{CRITICAL_CSS}</style>')
    return "\n    ".join(lines)


def render_shell(template: str, meta: PageMeta) -> str:
    """Vite qobig'iga meta va indekslanadigan matnni joylaydi.

    Matn `#root` ichiga qo'yiladi: React yuklangach o'sha joyni almashtiradi,
    ya'ni robot va foydalanuvchi bir xil mazmunni ko'radi.
    """
    document = _TITLE_TAG.sub("", _DESC_TAG.sub("", template))
    # Ruscha jurnal/maqola sahifasi Google'ga o'zbekcha deb e'lon qilinmasin.
    document = document.replace('<html lang="uz">', f'<html lang="{e(meta.lang)}">', 1)
    extra = ""
    if meta.data is not None:
        # `</script>` va `<` matn ichida kelsa HTML buzilmasin — JSON-LD dagi kabi.
        payload = json.dumps(meta.data, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
        extra = f'\n    <script id="ilmiz-data" type="application/json">{payload}</script>'
    document = document.replace("</head>", f"    {render_head(meta)}{extra}\n  </head>", 1)
    navigation = '<nav aria-label="Asosiy navigatsiya"><a href="/">IlmIz</a> · <a href="/jurnallar">Jurnallar</a> · <a href="/maqolalar">Maqolalar</a> · <a href="/yangi-maqolalar">Yangi maqolalar</a></nav>'
    body = f'<div class="seo-shell">{navigation}{meta.body}</div>' if meta.body else ""
    return document.replace('<div id="root"></div>', f'<div id="root">{body}</div>', 1)
