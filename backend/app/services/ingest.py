from __future__ import annotations

import logging
import re
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

from pathlib import Path

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from harvester import oai_harvester
from harvester.oai_harvester import OAIError, OAIRecord, harvest, identify, list_metadata_formats, metadata_from_xml

from . import netguard, seo
from .search_text import article_search_text

# Harvester har so‘rov va redirect'da manzilni tekshirsin (SSRF).
oai_harvester.URL_GUARD = netguard.assert_public_url

from ..db import SessionLocal
from ..models import Article, HarvestRun, HarvestSource, Journal, SourceRecord

logger = logging.getLogger(__name__)

# Harvest qilinadigan manba holatlari. `degraded` — oxirgi urinish(lar)
# yiqilgan, lekin manba hali tashlab yuborilmagan: OJS saytlari vaqti-vaqti
# bilan 500/504 beradi va ertasiga yana ishlaydi. Ilgari bitta xato manbani
# darhol `failed` qilib, `harvest-all` ro‘yxatidan abadiy chiqarib yuborardi.
ACTIVE_SOURCE_STATUSES = ("healthy", "degraded")
# Shuncha ketma-ket xatodan keyin manba `failed` bo‘ladi va faqat qayta
# audit (`--retry-failed` yoki qo‘lda `harvest <slug> <url>`) uni qaytaradi.
FAILED_AFTER = 10
# Inkremental harvest'da `last_success_at` dan shuncha kun orqaga qaytamiz:
# repozitoriy soati bizniki bilan farq qilishi va bir kunlik yozuvlar
# harvest o‘rtasida kelishi mumkin. Takrorlar `metadata_hash` bilan filtrlanadi.
INCREMENTAL_OVERLAP_DAYS = 1
# Yiqilgan manbaga qayta urinish oralig‘i: 2, 4, 8 ... soat, ko‘pi bilan bir hafta.
MAX_BACKOFF_HOURS = 168


def _mark_run_failed(run_id: int, source_id: int, message: str) -> bool:
    """Run'ni `failed`, manbani `degraded` (yoki chegaradan so‘ng `failed`) qiladi.

    Xatoni yozish uchun toza sessiya ochamiz: harvest paytida yiqilgan sessiya
    bilan commit qilishga urinsak, o‘sha commit ham yiqilib run abadiy
    `running` holatida qolib ketardi.
    """
    try:
        with SessionLocal() as db:
            run = db.get(HarvestRun, run_id)
            source = db.get(HarvestSource, source_id)
            now = datetime.now(timezone.utc)
            if run is not None and run.status == "running":
                run.status = "failed"
                run.error_summary = message[:2000]
                run.finished_at = now
            if source is not None:
                source.consecutive_failures += 1
                source.status = "failed" if source.consecutive_failures >= FAILED_AFTER else "degraded"
                source.last_error = message[:2000]
                source.last_attempt_at = now
            db.commit()
        return True
    except Exception:
        logger.exception("Run %s uchun xato holatini yozib bo‘lmadi", run_id)
        return False


def normalize_title(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).casefold()
    value = re.sub(r"[^\w\s]", " ", value, flags=re.UNICODE)
    return " ".join(value.split())


def _first(metadata: dict[str, list[str]], name: str) -> str | None:
    values = metadata.get(name, [])
    return values[0] if values else None


def _doi(metadata: dict[str, list[str]]) -> str | None:
    for value in metadata.get("identifier", []):
        match = re.search(r"10\.\d{4,9}/\S+", value, flags=re.IGNORECASE)
        if match:
            return match.group(0).rstrip(".,;)").lower()
    return None


def _landing_url(metadata: dict[str, list[str]]) -> str | None:
    for value in metadata.get("identifier", []):
        lowered = value.casefold()
        if value.startswith(("http://", "https://")) and "doi.org/" not in lowered and not _looks_like_pdf(lowered):
            return value
    doi = _doi(metadata)
    if doi:
        return f"https://doi.org/{doi}"
    return None


def _looks_like_pdf(value: str) -> bool:
    return value.split("?", 1)[0].endswith(".pdf") or "/download/" in value or "/article/download" in value


def _pdf_url(metadata: dict[str, list[str]]) -> str | None:
    for name in ("identifier", "relation"):
        for value in metadata.get(name, []):
            if value.startswith(("http://", "https://")) and _looks_like_pdf(value.casefold()):
                return value
    return None


def _publication_date(metadata: dict[str, list[str]]) -> str | None:
    value = _first(metadata, "date")
    return value.strip()[:80] if value else None


def _year(metadata: dict[str, list[str]]) -> int | None:
    value = _publication_date(metadata)
    if value:
        match = re.search(r"(?:19|20)\d{2}", value)
        if match:
            return int(match.group(0))
    return None


def _language(metadata: dict[str, list[str]]) -> str | None:
    value = _first(metadata, "language")
    if not value:
        return None
    mapping = {"uz": "O‘zbek", "uzb": "O‘zbek", "ru": "Rus", "rus": "Rus", "en": "Ingliz", "eng": "Ingliz"}
    return mapping.get(value.casefold(), value)


# Bu belgilar so‘z ichida ham uchraydi. `\b` bo‘lmasa "ECONOMY" dagi "no"
# issue = "MY" ni, "INNOVATION" dagi "no" issue = "vation" ni, kirilcha
# "автоматики" dagi "том" esa volume = "ки" ni berardi. Qiymat raqamdan
# boshlanishi ham talab qilinadi — haqiqiy jild/son doim shunday.
_VOLUME_RE = re.compile(r"(?:\bvol(?:ume)?\b|\bjild\b|\bтом\b)\.?\s*[:№#-]?\s*(\d[\w./-]*)", re.IGNORECASE | re.UNICODE)
_ISSUE_RE = re.compile(r"(?:\bno\b|\bnr\b|\bissue\b|\bson\b|№|\bвыпуск\b)\.?\s*[:№#-]?\s*(\d[\w./-]*)", re.IGNORECASE | re.UNICODE)
_PAGES_RE = re.compile(r"(?:\bpp?\.|\bpages?\b|\bbet(?:lar)?\b|\bс\.)\s*[:.-]?\s*(\d+\s*[-–—]\s*\d+)", re.IGNORECASE | re.UNICODE)

# O‘zbekcha manbalarda raqam so‘zdan oldin keladi: "4-jild", "2-son", "10-20 bet".
_VOLUME_UZ_RE = re.compile(r"(\d+)\s*[-–]?\s*(?:jild|том)\b", re.IGNORECASE | re.UNICODE)
_ISSUE_UZ_RE = re.compile(r"(\d+)\s*[-–]?\s*son\b", re.IGNORECASE | re.UNICODE)
_PAGES_UZ_RE = re.compile(r"(\d+\s*[-–—]\s*\d+)\s*[-–]?\s*bet(?:lar)?\b", re.IGNORECASE | re.UNICODE)

# OJS `dc:source` standart shakli: "Jurnal; Vol. 4 No. 2 (2025); 37-40".
# Betlar oxirgi segmentda markersiz turadi \u2014 shuning uchun alohida pattern.
_PAGES_OJS_RE = re.compile(r";\s*(\d{1,5}\s*[-–—]\s*\d{1,5})\s*(?=\||$)", re.UNICODE)


def _looks_like_year_range(value: str) -> bool:
    """"2019-2020" bet oralig‘i emas, yil oralig‘i."""
    parts = re.split(r"[-–—]", value.replace(" ", ""), maxsplit=1)
    return len(parts) == 2 and all(part.isdigit() and 1900 <= int(part) <= 2100 for part in parts)


def _first_match(patterns: tuple[re.Pattern[str], ...], text: str) -> str | None:
    for pattern in patterns:
        match = pattern.search(text)
        if match:
            return match.group(1)
    return None


def _bibliographic_parts(metadata: dict[str, list[str]]) -> tuple[str | None, str | None, str | None]:
    text = " | ".join(metadata.get("source", []) + metadata.get("relation", []))
    pages = _first_match((_PAGES_UZ_RE, _PAGES_RE, _PAGES_OJS_RE), text)
    if pages and _looks_like_year_range(pages):
        pages = None
    return (
        _first_match((_VOLUME_UZ_RE, _VOLUME_RE), text),
        _first_match((_ISSUE_UZ_RE, _ISSUE_RE), text),
        pages.replace(" ", "") if pages else None,
    )


def _is_ssl_error(error: Exception) -> bool:
    text = str(error).casefold()
    return "certificate" in text or "ssl" in text


def audit_source(
    db: Session,
    journal: Journal,
    base_url: str,
    *,
    timeout: int = 30,
    allow_insecure_ssl: bool = False,
) -> HarvestSource:
    if urlparse(base_url).scheme not in {"http", "https"}:
        raise ValueError("OAI base URL http yoki https bo‘lishi kerak")
    # Bitta OAI endpoint bitta jurnalga tegishli. OJS'ning sayt darajasidagi
    # `/index.php/index/oai` manzili esa o‘sha o‘rnatmadagi HAMMA jurnalni
    # qaytaradi: u to‘rtta jurnalga biriktirilib, aynan bir xil 22 ta maqola
    # to‘rt marta yozilgan edi.
    taken = db.scalar(
        select(HarvestSource).where(
            HarvestSource.base_url == base_url,
            HarvestSource.journal_id != journal.id,
            HarvestSource.status.in_(ACTIVE_SOURCE_STATUSES),
        )
    )
    if taken is not None:
        raise OAIError(
            f"Bu OAI endpoint allaqachon boshqa jurnalga biriktirilgan: {taken.journal.name}"
        )
    # Ichki manzil (127.0.0.1, 10.x, metadata) bo‘lsa manba yaratilmasin ham.
    netguard.assert_public_url(base_url)
    source = db.scalar(
        select(HarvestSource).where(
            HarvestSource.journal_id == journal.id,
            HarvestSource.base_url == base_url,
            HarvestSource.metadata_prefix == "oai_dc",
        )
    )
    if source is None:
        source = HarvestSource(journal=journal, base_url=base_url, metadata_prefix="oai_dc")
        db.add(source)
    source.last_attempt_at = datetime.now(timezone.utc)
    try:
        verify_ssl = not source.insecure_ssl
        try:
            identity = identify(base_url, timeout=timeout, verify_ssl=verify_ssl)
        except OAIError as error:
            # Sertifikat buzuq bo‘lsa, faqat shu host uchun tekshiruvni
            # o‘chirib bir marta qayta urinamiz — universitet saytlarining
            # bir qismida sertifikat muddati o‘tgan, OAI esa to‘g‘ri ishlaydi.
            if not (allow_insecure_ssl and verify_ssl and _is_ssl_error(error)):
                raise
            logger.warning("Sertifikat tekshiruvisiz qayta urinilmoqda: %s", base_url)
            source.insecure_ssl = True
            verify_ssl = False
            identity = identify(base_url, timeout=timeout, verify_ssl=False)
        formats = list_metadata_formats(base_url, timeout=timeout, verify_ssl=verify_ssl)
        prefixes = {item["prefix"] for item in formats}
        if "oai_dc" not in prefixes:
            raise OAIError("Repository oai_dc formatini taqdim qilmaydi")
        source.repository_name = identity.get("repository_name") or journal.name
        source.protocol_version = identity.get("protocol_version")
        source.datestamp_granularity = identity.get("granularity")
        source.deleted_record_policy = identity.get("deleted_record")
        source.available_formats = formats
        source.status = "healthy"
        source.consecutive_failures = 0
        source.last_error = None
        source.last_success_at = datetime.now(timezone.utc)
    except Exception as error:
        source.status = "failed"
        source.consecutive_failures += 1
        source.last_error = str(error)[:2000]
        db.commit()
        raise
    db.commit()
    db.refresh(source)
    return source


class _BatchCache:
    """Bitta commit oralig‘ida yaratilgan, hali flush qilinmagan obyektlar.

    Sessiya `autoflush=False` bilan ochilgani uchun `select` hali bazaga
    yozilmagan yozuvni ko‘rmaydi. Bir OAI oqimida ayni `oai_identifier` yoki
    DOI ikki marta kelsa (deleted headerlar va bir nechta setSpec bunday
    keladi), ikkinchi INSERT commit paytida UNIQUE constraintni buzardi va
    butun harvest yiqilardi.
    """

    __slots__ = ("records", "articles_by_doi", "articles_by_key")

    def __init__(self) -> None:
        self.records: dict[str, SourceRecord] = {}
        self.articles_by_doi: dict[str, Article] = {}
        self.articles_by_key: dict[tuple[int, str, int | None], Article] = {}

    def clear(self) -> None:
        self.records.clear()
        self.articles_by_doi.clear()
        self.articles_by_key.clear()


def _upsert_record(db: Session, source: HarvestSource, record: OAIRecord, cache: _BatchCache | None = None) -> str:
    now = datetime.now(timezone.utc)
    if cache is None:
        cache = _BatchCache()
    source_record = cache.records.get(record.identifier)
    if source_record is None:
        source_record = db.scalar(
            select(SourceRecord).where(
                SourceRecord.source_id == source.id,
                SourceRecord.oai_identifier == record.identifier,
            )
        )
    if source_record is not None:
        cache.records[record.identifier] = source_record
    if source_record and source_record.metadata_hash == record.metadata_hash and source_record.is_deleted == record.deleted:
        source_record.last_seen_at = now
        return "unchanged"
    if source_record is None:
        source_record = SourceRecord(source=source, oai_identifier=record.identifier)
        db.add(source_record)
        cache.records[record.identifier] = source_record
        state = "created"
    else:
        state = "updated"
    source_record.oai_datestamp = record.datestamp
    source_record.set_specs = record.set_specs
    source_record.is_deleted = record.deleted
    source_record.metadata_hash = record.metadata_hash
    source_record.raw_xml = record.raw_xml
    source_record.last_seen_at = now

    if record.deleted:
        if source_record.article:
            source_record.article.is_deleted = True
            source_record.article.updated_at = now
        return "deleted"

    title = _first(record.metadata, "title")
    if not title:
        return "skipped"
    doi = _doi(record.metadata)
    publication_year = _year(record.metadata)
    article = source_record.article
    doi_article = None
    if doi:
        doi_article = cache.articles_by_doi.get(doi)
        if doi_article is None:
            doi_article = db.scalar(select(Article).where(Article.doi == doi))
            if doi_article is not None:
                cache.articles_by_doi[doi] = doi_article
    if article is None and doi_article is not None:
        article = doi_article
    elif article is not None and doi_article is not None and article.id != doi_article.id:
        if article.normalized_title == doi_article.normalized_title:
            source_record.article = doi_article
            article = doi_article
        else:
            # Ayrim OAI manbalar bir DOI qiymatini bir nechta maqolaga xato
            # qo‘yadi. Bunday holda maqolani yo‘qotmaymiz, kollizion DOIni olmaymiz.
            doi = None
    article_key = (source.journal_id, normalize_title(title), publication_year)
    if article is None:
        article = cache.articles_by_key.get(article_key)
    if article is None:
        article = db.scalar(
            select(Article).where(
                Article.journal_id == source.journal_id,
                Article.normalized_title == normalize_title(title),
                Article.publication_year == publication_year,
            )
        )
    if article is None:
        article = Article(journal=source.journal, title=title, normalized_title=normalize_title(title))
        db.add(article)
    cache.articles_by_key[article_key] = article
    if article.doi and doi and article.doi != doi:
        doi = None
    volume, issue, pages = _bibliographic_parts(record.metadata)
    article.title = title
    article.normalized_title = normalize_title(title)
    article.authors = record.metadata.get("creator", [])
    article.abstract = _first(record.metadata, "description")
    article.keywords = record.metadata.get("subject", [])
    article.language = _language(record.metadata)
    article.fields = source.journal.fields
    article.publication_date = _publication_date(record.metadata)
    article.publication_year = publication_year
    article.volume = volume or article.volume
    article.issue = issue or article.issue
    article.pages = pages or article.pages
    article.doi = doi
    article.landing_url = _landing_url(record.metadata)
    article.pdf_url = _pdf_url(record.metadata)
    article.search_text = article_search_text(article.title, article.abstract, article.authors)
    article.is_deleted = False
    article.harvested_at = now
    article.updated_at = now
    if doi:
        cache.articles_by_doi[doi] = article
    source_record.article = article
    return state


def ingest_source(db: Session, source: HarvestSource, *, from_date: str | None, page_limit: int | None) -> HarvestRun:
    stale_runs = list(db.scalars(select(HarvestRun).where(HarvestRun.source_id == source.id, HarvestRun.status == "running")))
    for stale in stale_runs:
        stale.status = "failed"
        stale.finished_at = datetime.now(timezone.utc)
        stale.error_summary = stale.error_summary or "Oldingi worker yakunlanmasdan to‘xtagan; qayta harvest boshlandi."
    run = HarvestRun(source=source, mode="incremental" if from_date else "full")
    db.add(run)
    db.commit()
    cache = _BatchCache()
    try:
        for record in harvest(
            source.base_url,
            metadata_prefix=source.metadata_prefix,
            from_date=from_date,
            page_limit=page_limit,
            timeout=60,
            verify_ssl=not source.insecure_ssl,
        ):
            run.records_seen += 1
            state = _upsert_record(db, source, record, cache)
            if state == "created":
                run.records_created += 1
            elif state == "updated":
                run.records_updated += 1
            elif state == "deleted":
                run.records_deleted += 1
            if run.records_seen % 100 == 0:
                db.commit()
                # Commitdan keyin hamma narsa bazada; keshni tozalab xotirani
                # to‘liq harvest davomida barqaror ushlab turamiz.
                cache.clear()
        run.status = "succeeded"
        source.status = "healthy"
        source.last_success_at = datetime.now(timezone.utc)
        source.last_error = None
        source.consecutive_failures = 0
    except Exception as error:
        run_id = run.id
        source_id = source.id
        message = f"{type(error).__name__}: {error}"
        logger.exception("Harvest yiqildi: source=%s run=%s url=%s", source_id, run_id, source.base_url)
        try:
            db.rollback()
        except Exception:
            logger.exception("Rollback yiqildi: source=%s run=%s", source_id, run_id)
        if not _mark_run_failed(run_id, source_id, message):
            logger.error("Run %s `running` holatida qoldi; keyingi harvest uni stale deb yopadi", run_id)
        db.expire_all()
        raise
    run.finished_at = datetime.now(timezone.utc)
    source.last_attempt_at = run.finished_at
    db.commit()
    db.refresh(run)
    # Maqola sanoqlari SEO sahifalari va katalog uchun keshlanadi; harvest
    # ularni o‘zgartirgan bo‘lishi mumkin.
    seo.reset_cache()
    return run


def _as_utc(value: datetime | None) -> datetime | None:
    """SQLite `DateTime(timezone=True)` qiymatni tzinfo'siz qaytaradi."""
    if value is None:
        return None
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def incremental_from_date(source: HarvestSource, *, overlap_days: int = INCREMENTAL_OVERLAP_DAYS) -> str | None:
    """Manba uchun inkremental `from` sanasi (`YYYY-MM-DD`).

    Hech qachon muvaffaqiyatli harvest bo‘lmagan bo‘lsa `None` — to‘liq
    harvest kerak. Kun aniqligi ataylab: OAI-PMH bo‘yicha har ikki
    granularity'dagi repozitoriy ham uni qabul qiladi.
    """
    last = _as_utc(source.last_success_at)
    if last is None:
        return None
    return (last - timedelta(days=overlap_days)).date().isoformat()


def backoff_until(source: HarvestSource) -> datetime | None:
    """`degraded` manbaga qachongacha tegmaslik kerak.

    Ketma-ket xatolar soniga qarab 2, 4, 8 ... soat, ko‘pi bilan bir hafta.
    Sog‘ manba yoki hech qachon urinilmagan manba uchun `None`.
    """
    if source.status != "degraded" or source.consecutive_failures <= 0:
        return None
    attempted = _as_utc(source.last_attempt_at)
    if attempted is None:
        return None
    hours = min(2 ** source.consecutive_failures, MAX_BACKOFF_HOURS)
    return attempted + timedelta(hours=hours)


def _ingest_source_by_id(
    source_id: int,
    from_date: str | None,
    page_limit: int | None,
    *,
    since_last_success: bool = False,
) -> dict[str, int | str]:
    empty = {"seen": 0, "created": 0, "updated": 0, "deleted": 0}
    with SessionLocal() as worker_db:
        source = worker_db.get(HarvestSource, source_id)
        if source is None:
            logger.error("Source %s topilmadi", source_id)
            return {"status": "failed", **empty, "error": "source topilmadi"}
        base_url = source.base_url
        if source.status == "failed":
            # `--retry-failed`: avval endpoint tirikligini tekshiramiz; audit
            # o‘zi holatni `healthy` ga qaytaradi yoki xatoni yozadi.
            try:
                audit_source(worker_db, source.journal, base_url, allow_insecure_ssl=True)
            except Exception as error:
                logger.warning("Source %s (%s) qayta auditdan o‘tmadi: %s", source_id, base_url, error)
                return {"status": "failed", **empty, "error": f"audit: {type(error).__name__}: {error}"[:500]}
        effective_from = from_date
        if effective_from is None and since_last_success:
            effective_from = incremental_from_date(source)
        try:
            run = ingest_source(worker_db, source, from_date=effective_from, page_limit=page_limit)
            logger.info(
                "Harvest tugadi: source=%s url=%s from=%s seen=%s created=%s updated=%s deleted=%s",
                source_id, base_url, effective_from or "-",
                run.records_seen, run.records_created, run.records_updated, run.records_deleted,
            )
            return {
                "status": run.status,
                "seen": run.records_seen,
                "created": run.records_created,
                "updated": run.records_updated,
                "deleted": run.records_deleted,
                "error": "",
            }
        except Exception as error:
            # Traceback ingest_source ichida allaqachon yozilgan; bu yerda faqat
            # xulosani natijaga qo‘shamiz, chunki avval xato butunlay yo‘qolardi.
            logger.warning("Source %s (%s) harvest qilinmadi: %s", source_id, base_url, error)
            return {"status": "failed", **empty, "error": f"{type(error).__name__}: {error}"[:500]}


def select_harvest_sources(
    db: Session,
    *,
    retry_failed: bool = False,
    respect_backoff: bool = True,
    now: datetime | None = None,
) -> tuple[list[int], list[int]]:
    """Harvest qilinadigan va backoff tufayli o‘tkazib yuborilgan manba id'lari.

    Faqat OAI manbalari (`oai_dc`). OpenAlex import qilgan manbalar
    `metadata_prefix` bilan ajratiladi — ularni OAI harvesteriga bersak,
    so‘rov xato bo‘lib manba `failed` deb belgilanardi.
    `retry_failed` bilan ilgari kamida bir marta ishlagan `failed` manbalar ham
    olinadi (ular harvestdan oldin qayta audit qilinadi).
    """
    now = now or datetime.now(timezone.utc)
    statement = select(HarvestSource).where(HarvestSource.metadata_prefix == "oai_dc")
    if retry_failed:
        statement = statement.where(
            HarvestSource.status.in_(ACTIVE_SOURCE_STATUSES)
            | ((HarvestSource.status == "failed") & HarvestSource.last_success_at.is_not(None))
        )
    else:
        statement = statement.where(HarvestSource.status.in_(ACTIVE_SOURCE_STATUSES))
    chosen: list[int] = []
    skipped: list[int] = []
    for source in db.scalars(statement.order_by(HarvestSource.id)):
        until = backoff_until(source) if respect_backoff else None
        if until is not None and until > now:
            skipped.append(source.id)
            continue
        chosen.append(source.id)
    return chosen, skipped


def ingest_all_sources(
    db: Session,
    *,
    from_date: str | None = None,
    page_limit: int | None = None,
    workers: int = 3,
    selected_source_ids: list[int] | None = None,
    since_last_success: bool = False,
    retry_failed: bool = False,
    respect_backoff: bool = True,
) -> dict[str, object]:
    skipped: list[int] = []
    if selected_source_ids:
        source_ids = list(selected_source_ids)
    else:
        source_ids, skipped = select_harvest_sources(db, retry_failed=retry_failed, respect_backoff=respect_backoff)
    totals: dict[str, object] = {
        "sources": len(source_ids), "skipped": len(skipped),
        "mode": "incremental" if (from_date or since_last_success) else "full",
        "succeeded": 0, "failed": 0, "seen": 0, "created": 0, "updated": 0, "deleted": 0,
    }
    errors: list[dict[str, str]] = []
    with ThreadPoolExecutor(max_workers=min(max(1, workers), len(source_ids) or 1)) as executor:
        futures = {
            executor.submit(
                _ingest_source_by_id, source_id, from_date, page_limit, since_last_success=since_last_success
            ): source_id
            for source_id in source_ids
        }
        for future in as_completed(futures):
            source_id = futures[future]
            result = future.result()
            status = str(result["status"])
            totals["succeeded" if status == "succeeded" else "failed"] += 1
            for key in ("seen", "created", "updated", "deleted"):
                totals[key] += int(result[key])
            if status != "succeeded":
                errors.append({"sourceId": str(source_id), "error": str(result.get("error", ""))})
    totals["errors"] = errors
    db.expire_all()
    return totals

def reparse_bibliographic(db: Session, *, dry_run: bool = True, batch_size: int = 2000) -> dict[str, int]:
    """Saqlangan `raw_xml` dan jild/son/betlarni qayta hisoblaydi.

    Qayta harvest qilish shart emas — provenance `source_records` da turibdi.
    Faqat parser xatosi tuzatiladi, hech qanday qiymat uydirilmaydi.
    """
    totals = {"tekshirildi": 0, "yangilandi": 0, "volume": 0, "issue": 0, "pages": 0, "xatolar": 0}
    statement = (
        select(Article.id, Article.volume, Article.issue, Article.pages, SourceRecord.raw_xml)
        .join(SourceRecord, SourceRecord.article_id == Article.id)
        .where(Article.is_deleted.is_(False), SourceRecord.raw_xml.is_not(None))
    )
    # Avval faqat o‘qiymiz. `yield_per` oqimi o‘rtasida commit qilish kursorni
    # buzib, qatorlarni o‘tkazib yuborardi — natijada bir yurish yetmasdi.
    planned: list[tuple[int, str | None, str | None, str | None]] = []
    seen: set[int] = set()
    for article_id, volume, issue, pages, raw_xml in db.execute(statement).yield_per(batch_size):
        current = (volume, issue, pages)
        if article_id in seen:
            continue
        seen.add(article_id)
        totals["tekshirildi"] += 1
        try:
            metadata = metadata_from_xml(raw_xml)
        except Exception:
            logger.warning("Maqola %s uchun raw_xml o‘qilmadi", article_id)
            totals["xatolar"] += 1
            continue
        parsed = _bibliographic_parts(metadata)
        changed = False
        for index, field in enumerate(("volume", "issue", "pages")):
            if current[index] != parsed[index]:
                totals[field] += 1
                changed = True
        if changed:
            totals["yangilandi"] += 1
            planned.append((article_id, *parsed))

    if dry_run:
        return totals

    for start in range(0, len(planned), batch_size):
        for article_id, volume, issue, pages in planned[start : start + batch_size]:
            article = db.get(Article, article_id)
            if article is None:
                continue
            article.volume = volume
            article.issue = issue
            article.pages = pages
        db.commit()
    logger.info("Bibliografik qayta tahlil: %s", totals)
    return totals

def drop_raw_metadata_column(*, vacuum: bool = True) -> dict[str, object]:
    """`source_records.raw_metadata` ustunini o‘chiradi va joyni bo‘shatadi.

    Ustun `raw_xml` dan to‘liq tiklanadi, shuning uchun ortiqcha. VACUUM
    bo‘lmasa SQLite bo‘shagan sahifalarni faylga qaytarmaydi.
    """
    from sqlalchemy import inspect as sa_inspect

    from ..db import engine

    result: dict[str, object] = {"ustun_bor_edi": False, "vacuum": False}
    columns = {column["name"] for column in sa_inspect(engine).get_columns("source_records")}
    if "raw_metadata" not in columns:
        logger.info("raw_metadata ustuni allaqachon yo‘q")
        return result

    result["ustun_bor_edi"] = True
    before = engine.url.database
    if before and Path(before).exists():
        result["hajm_avval_bayt"] = Path(before).stat().st_size

    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE source_records DROP COLUMN raw_metadata"))
    logger.info("raw_metadata ustuni o‘chirildi")

    if vacuum:
        # VACUUM tranzaksiya ichida ishlamaydi.
        with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
            connection.execute(text("VACUUM"))
        result["vacuum"] = True
        logger.info("VACUUM tugadi")

    if before and Path(before).exists():
        result["hajm_hozir_bayt"] = Path(before).stat().st_size
    return result

def rebuild_search_index(db: Session, *, batch_size: int = 2000) -> dict[str, int]:
    """Barcha maqolalar uchun `search_text` ni qayta hisoblaydi.

    Normalizatsiya qoidasi o‘zgarganda yoki ustun yangi qo‘shilganda kerak.
    """
    rows = db.execute(
        select(Article.id, Article.title, Article.abstract, Article.authors)
    ).all()
    updates = [
        {"id": row[0], "search_text": article_search_text(row[1], row[2], row[3])}
        for row in rows
    ]
    for start in range(0, len(updates), batch_size):
        db.bulk_update_mappings(Article, updates[start : start + batch_size])
        db.commit()
    logger.info("Qidiruv indeksi qayta qurildi: %s maqola", len(updates))
    return {"maqolalar": len(updates)}
