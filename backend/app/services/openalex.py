"""OpenAlex'dan maqola yozuvlarini olish.

Nega kerak: 346 jurnalda umuman maqola yo'q — OAI ishlamaydi yoki sayt
yo'q. Ularning 171 tasining ISSN'i bor va namunaviy tekshiruvda yarmi
OpenAlex'da topildi (`docs/openalex-pilot.md`).

Bu OAI o'rnini bosmaydi. Jurnalning o'z endpointi ishlayotgan bo'lsa,
o'sha ustun: u nashriyotning birlamchi ma'lumoti. OpenAlex esa uchinchi
tomon indeksi, shuning uchun yozuvlari alohida manba sifatida belgilanadi
va mavjud maydonlar ustiga yozilmaydi.
"""
from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import httpx

API = "https://api.openalex.org"
# OpenAlex «polite pool» — aloqa manzili ko'rsatilgan so'rovlar alohida,
# barqarorroq navbatda ishlanadi.
CONTACT = "mailto:journalmaturidi@gmail.com"
USER_AGENT = f"IlmIz/0.4 (https://github.com/muslim0203/ilmiz; {CONTACT})"
PAGE_SIZE = 100
# Bitta so'rovda olinadigan maydonlar — keraksizini so'ramaymiz.
FIELDS = (
    "id,doi,title,publication_date,publication_year,language,type,biblio,"
    "authorships,abstract_inverted_index,primary_location,best_oa_location"
)
# Konferensiya tezislari, tahririyat xatlari va shu kabilar indeksga kirmaydi.
ARTICLE_TYPES = {"article", "review", "book-chapter", "preprint"}


def _client() -> httpx.Client:
    return httpx.Client(timeout=40, headers={"User-Agent": USER_AGENT})


def find_source(issn: str, *, client: httpx.Client | None = None) -> dict[str, Any] | None:
    """ISSN bo'yicha OpenAlex manbasini topadi."""
    owned = client is None
    client = client or _client()
    try:
        response = client.get(f"{API}/sources/issn:{issn}", params={"mailto": CONTACT})
        if response.status_code != 200:
            return None
        data = response.json()
        return {
            "id": data["id"].rsplit("/", 1)[-1],
            "name": data.get("display_name"),
            "works_count": data.get("works_count", 0),
            "issn": data.get("issn") or [],
        }
    finally:
        if owned:
            client.close()


def reconstruct_abstract(inverted: dict[str, list[int]] | None) -> str | None:
    """`abstract_inverted_index` dan matnni tiklaydi.

    OpenAlex annotatsiyani so'z -> pozitsiyalar ko'rinishida saqlaydi
    (litsenziya sabab); tartibga solib qaytaramiz.
    """
    if not inverted:
        return None
    positions = sorted(
        (position, word) for word, places in inverted.items() for position in places
    )
    text = " ".join(word for _, word in positions).strip()
    return text or None


def normalise(work: dict[str, Any]) -> dict[str, Any] | None:
    """OpenAlex yozuvini loyihaning maydonlariga moslashtiradi.

    Faqat OpenAlex bergan qiymatlar olinadi — hech narsa to'ldirilmaydi
    yoki taxmin qilinmaydi.
    """
    title = (work.get("title") or "").strip()
    if not title:
        return None
    if work.get("type") and work["type"] not in ARTICLE_TYPES:
        return None

    doi = work.get("doi") or ""
    # Bizda DOI prefikssiz saqlanadi: `10.xxxx/yyy`.
    doi = doi.replace("https://doi.org/", "").strip().lower() or None

    biblio = work.get("biblio") or {}
    first, last = biblio.get("first_page"), biblio.get("last_page")
    pages = f"{first}-{last}" if first and last else (first or None)

    location = work.get("primary_location") or {}
    best = work.get("best_oa_location") or {}

    return {
        "openalex_id": work["id"].rsplit("/", 1)[-1],
        "title": title,
        "authors": [
            a["author"]["display_name"]
            for a in work.get("authorships") or []
            if a.get("author", {}).get("display_name")
        ],
        "abstract": reconstruct_abstract(work.get("abstract_inverted_index")),
        "publication_date": work.get("publication_date"),
        "publication_year": work.get("publication_year"),
        "volume": biblio.get("volume"),
        "issue": biblio.get("issue"),
        "pages": pages,
        "doi": doi,
        "language": work.get("language"),
        "landing_url": location.get("landing_page_url"),
        "pdf_url": best.get("pdf_url"),
    }


def iter_works(source_id: str, *, limit: int | None = None) -> Iterator[dict[str, Any]]:
    """Manbaning ishlarini kursor bo'yicha sahifalab qaytaradi."""
    cursor = "*"
    seen = 0
    with _client() as client:
        while cursor:
            response = client.get(
                f"{API}/works",
                params={
                    "filter": f"primary_location.source.id:{source_id}",
                    "per-page": PAGE_SIZE,
                    "cursor": cursor,
                    "select": FIELDS,
                    "mailto": CONTACT,
                },
            )
            response.raise_for_status()
            payload = response.json()
            for work in payload.get("results", []):
                record = normalise(work)
                if record is None:
                    continue
                yield record
                seen += 1
                if limit is not None and seen >= limit:
                    return
            cursor = (payload.get("meta") or {}).get("next_cursor")


__all__ = ["find_source", "iter_works", "normalise", "reconstruct_abstract"]


# --- Bazaga import ---------------------------------------------------------

SOURCE_PREFIX = "openalex"
# `ingest_all_sources` faqat `oai_dc` manbalarini yig'adi, shuning uchun bu
# manba OAI harvesteriga tushmaydi.
METADATA_PREFIX = "openalex"


def source_url(source_id: str) -> str:
    return f"{API}/works?filter=primary_location.source.id:{source_id}"


def _harvest_source(db, journal, source_id: str):
    """Provenance uchun manba yozuvi — mavjud bo'lsa qayta ishlatiladi."""
    from sqlalchemy import select

    from ..models import HarvestSource

    url = source_url(source_id)
    source = db.scalar(
        select(HarvestSource).where(
            HarvestSource.journal_id == journal.id, HarvestSource.base_url == url
        )
    )
    if source is None:
        source = HarvestSource(
            journal_id=journal.id,
            base_url=url,
            metadata_prefix=METADATA_PREFIX,
            repository_name="OpenAlex",
            status="healthy",
        )
        db.add(source)
        db.flush()
    return source


def import_journal(db, journal, *, limit: int | None = None, dry_run: bool = True) -> dict:
    """Jurnalning OpenAlex yozuvlarini bazaga qo'shadi.

    Mavjud maqolaga tegilmaydi: DOI yoki OpenAlex ID bo'yicha topilgan
    yozuv o'tkazib yuboriladi. Ya'ni OAI orqali yig'ilgan birlamchi
    ma'lumot ustiga yozilmaydi.
    """
    from datetime import datetime, timezone

    from sqlalchemy import select

    from ..models import Article, SourceRecord
    from .search_text import article_search_text, normalize

    # Ikkala ISSN ham sinaladi. Bosma ISSN ko'pincha OpenAlex'da yo'q:
    # «Adabiy meros» faqat e-ISSN bo'yicha topiladi.
    candidates = [value for value in (journal.issn, journal.eissn) if value]
    if not candidates:
        return {"status": "issn yo‘q"}
    found = next((result for result in map(find_source, candidates) if result), None)
    if found is None:
        return {"status": "OpenAlex'da topilmadi", "issn": candidates}

    source = None if dry_run else _harvest_source(db, journal, found["id"])
    now = datetime.now(timezone.utc)

    known_dois = {
        value.lower()
        for (value,) in db.execute(select(Article.doi).where(Article.doi.is_not(None)))
        if value
    }
    known_ids = {
        value
        for (value,) in db.execute(
            select(SourceRecord.oai_identifier).where(
                SourceRecord.oai_identifier.like(f"{SOURCE_PREFIX}:%")
            )
        )
    }

    stats = {"status": "ok", "manba": found["name"], "jami": found["works_count"],
             "yangi": 0, "mavjud": 0, "sarlavhasiz": 0}
    for record in iter_works(found["id"], limit=limit):
        identifier = f"{SOURCE_PREFIX}:{record['openalex_id']}"
        if identifier in known_ids or (record["doi"] and record["doi"] in known_dois):
            stats["mavjud"] += 1
            continue
        stats["yangi"] += 1
        if dry_run:
            continue
        article = Article(
            journal_id=journal.id,
            title=record["title"],
            normalized_title=normalize(record["title"]),
            authors=record["authors"],
            abstract=record["abstract"],
            keywords=[],
            fields=[],
            language=record["language"],
            publication_date=record["publication_date"],
            publication_year=record["publication_year"],
            volume=record["volume"],
            issue=record["issue"],
            pages=record["pages"],
            doi=record["doi"],
            landing_url=record["landing_url"],
            pdf_url=record["pdf_url"],
            search_text=article_search_text(
                record["title"], record["abstract"], record["authors"]
            ),
            harvested_at=now,
        )
        db.add(article)
        db.flush()
        db.add(SourceRecord(
            source_id=source.id,
            article_id=article.id,
            oai_identifier=identifier,
            oai_datestamp=record["publication_date"],
            first_seen_at=now,
            last_seen_at=now,
        ))
        if record["doi"]:
            known_dois.add(record["doi"])
        known_ids.add(identifier)

    if not dry_run:
        db.commit()
        # Jurnal sanoqlari keshlanadi (TTL 300s). Tozalamasak, import
        # qilgan odam natijani besh daqiqa kutib turardi.
        from . import seo

        seo.invalidate("journal_counts")
    stats["rejim"] = "dry-run" if dry_run else "apply"
    return stats


def scan_candidates(db, *, only_empty: bool = True, workers: int = 4) -> list[dict]:
    """Jurnallarni OpenAlex'da qidirib, natijani ro'yxat qilib qaytaradi.

    Bazaga hech narsa yozmaydi — bu faqat qaysi jurnalni import qilish
    mumkinligini ko'rsatuvchi tekshiruv.

    Ikkala ISSN ham sinaladi: bosma ISSN OpenAlex'da ko'pincha ro'yxatga
    olinmagan («Adabiy meros» aynan shu sababli topilmay qolgan edi).
    """
    from concurrent.futures import ThreadPoolExecutor

    from sqlalchemy import select

    from ..models import Article, Journal

    statement = select(Journal).order_by(Journal.name)
    if only_empty:
        statement = statement.where(
            ~select(Article.id)
            .where(Article.journal_id == Journal.id, Article.is_deleted.is_(False))
            .exists()
        )
    journals = [
        {"id": j.id, "slug": j.slug, "name": j.name,
         "issns": [v for v in (j.issn, j.eissn) if v]}
        for j in db.scalars(statement)
    ]
    todo = [entry for entry in journals if entry["issns"]]

    def probe(entry: dict) -> dict:
        with _client() as client:
            for issn in entry["issns"]:
                found = find_source(issn, client=client)
                if found:
                    return {**entry, "found": True, "issn_used": issn,
                            "source": found["name"], "works": found["works_count"]}
        return {**entry, "found": False, "issn_used": None, "source": None, "works": 0}

    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        results = list(pool.map(probe, todo))

    results.sort(key=lambda row: -row["works"])
    return results
