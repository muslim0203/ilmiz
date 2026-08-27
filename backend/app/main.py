from __future__ import annotations

import os
import secrets
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, HttpUrl
from sqlalchemy import String, cast, distinct, func, or_, select
from sqlalchemy.orm import Session, selectinload

from .db import DATABASE_URL, SessionLocal, get_db, init_db
from .models import (
    Article,
    AuditJob,
    HarvestRun,
    HarvestSource,
    Journal,
    OakImportRun,
    OakRegistryEntry,
    OakRegistrySnapshotEntry,
    OakRegistrySnapshotMeta,
    ProfileJob,
)
from .seed import seed_database
from .services.audit_queue import enqueue_audits, process_audit_jobs, queue_stats
from .services.citations import citation_formats
from .services.ingest import audit_source, ingest_source
from .services.profile_collector import collect_profile
from .services.profile_queue import enqueue_profiles, process_profile_jobs, profile_queue_stats, profile_stats
from .services.taxonomy import FIELD_GROUPS, OTHER_GROUP, canonical_city, city_variants, field_group


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    with SessionLocal() as db:
        seed_database(db)
    yield


app = FastAPI(
    title="IlmIz API",
    version="0.2.0",
    description="OAK jurnallari va OAI-PMH maqolalar indeksi",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
    allow_methods=["*"],
    # Frontend sahifalash uchun umumiy sonni shu header'dan o'qiydi.
    allow_headers=["*"],
    expose_headers=["X-Total-Count"],
)


def admin_token() -> str:
    """Har so‘rovda o‘qiladi — tokenni almashtirish uchun restart shart emas."""
    return os.getenv("ILMIZ_ADMIN_TOKEN", "").strip()


def require_admin(
    authorization: str | None = Header(default=None),
    x_admin_token: str | None = Header(default=None),
) -> None:
    """Barcha `/api/admin/*` so‘rovlarini himoyalaydi.

    Token sozlanmagan bo‘lsa hamma narsa rad etiladi — ilgari bu endpointlar
    butunlay ochiq edi, shuning uchun standart holat yopiq bo‘lishi shart.
    """
    expected = admin_token()
    if not expected:
        raise HTTPException(
            status_code=503,
            detail="Admin API o‘chirilgan: ILMIZ_ADMIN_TOKEN muhit o‘zgaruvchisi sozlanmagan.",
        )
    provided = x_admin_token
    if not provided and authorization and authorization.lower().startswith("bearer "):
        provided = authorization[7:]
    if not provided or not secrets.compare_digest(provided.strip(), expected):
        raise HTTPException(status_code=401, detail="Admin tokeni noto‘g‘ri yoki berilmagan.")


@app.middleware("http")
async def admin_guard(request: Request, call_next):
    """Tokenni marshrutlashdan oldin tekshiradi.

    Router dependency’si yetarli, lekin FastAPI so‘rov body’sini
    dependency’lardan oldin parse qiladi — buzuq JSON 401 o‘rniga 422 berardi.
    Bu qatlam javobni bir xil qiladi va `/api/admin` ostidagi har qanday yangi
    yo‘lni ham qamrab oladi.
    """
    if request.url.path.startswith("/api/admin") and request.method != "OPTIONS":
        try:
            require_admin(request.headers.get("authorization"), request.headers.get("x-admin-token"))
        except HTTPException as error:
            return JSONResponse(status_code=error.status_code, content={"detail": error.detail})
    return await call_next(request)


# Router darajasida himoya: yangi admin endpoint qo‘shilganda ham avtomatik yopiq bo‘ladi.
admin = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(require_admin)])


class SourceInput(BaseModel):
    journal_slug: str = Field(min_length=2, max_length=180)
    base_url: HttpUrl


class HarvestInput(SourceInput):
    from_date: str | None = None
    page_limit: int | None = Field(default=None, ge=1, le=10000)


class AuditQueueInput(BaseModel):
    limit: int | None = Field(default=None, ge=1, le=1000)


class AuditProcessInput(BaseModel):
    limit: int = Field(default=5, ge=1, le=25)


class ProfileCollectInput(BaseModel):
    journal_slug: str = Field(min_length=2, max_length=180)


class ProfileQueueInput(BaseModel):
    limit: int | None = Field(default=None, ge=1, le=1000)
    refresh: bool = False


class ProfileProcessInput(BaseModel):
    limit: int = Field(default=3, ge=1, le=10)
    workers: int = Field(default=3, ge=1, le=5)


def source_status(journal: Journal) -> dict[str, object]:
    if not journal.harvest_sources:
        return {"oaiStatus": "missing", "oaiLastSync": None, "oaiBaseUrl": None}
    source = sorted(journal.harvest_sources, key=lambda item: item.updated_at, reverse=True)[0]
    status = "healthy" if source.status == "healthy" else "warning"
    last_sync = source.last_success_at.isoformat() if source.last_success_at else None
    return {"oaiStatus": status, "oaiLastSync": last_sync, "oaiBaseUrl": source.base_url}


def profile_payload(journal: Journal) -> dict[str, object] | None:
    profile = journal.profile
    if profile is None:
        return None
    return {
        "summary": profile.summary,
        "aimsScope": profile.aims_scope,
        "peerReview": profile.peer_review,
        "publicationFrequency": profile.publication_frequency,
        "submissionLanguages": profile.submission_languages,
        "address": profile.address,
        "latestIssue": profile.latest_issue,
        "completenessScore": profile.completeness_score,
        "sourceUrl": profile.source_url,
        "fetchedAt": profile.fetched_at.isoformat(),
        "verifiedAt": profile.verified_at.isoformat() if profile.verified_at else None,
        "contacts": [{
            "kind": item.kind,
            "label": item.label,
            "value": item.value,
            "sourceUrl": item.source_url,
            "fetchedAt": item.fetched_at.isoformat(),
        } for item in journal.contacts],
        "editorialMembers": [{
            "name": item.name,
            "role": item.role,
            "affiliation": item.affiliation,
            "orcid": item.orcid,
            "email": item.email,
            "sourceUrl": item.source_url,
        } for item in journal.editorial_members],
        "policies": [{
            "type": item.policy_type,
            "title": item.title,
            "content": item.content,
            "url": item.url,
            "sourceUrl": item.source_url,
        } for item in journal.policies],
        "sections": [{"name": item.name, "description": item.description, "sourceUrl": item.source_url} for item in journal.sections],
        "indexingClaims": [{
            "provider": item.provider,
            "status": item.status,
            "claimUrl": item.claim_url,
            "sourceUrl": item.source_url,
            "verifiedAt": item.verified_at.isoformat() if item.verified_at else None,
        } for item in journal.indexing_claims],
        "links": [{"kind": item.kind, "label": item.label, "url": item.url, "sourceUrl": item.source_url} for item in journal.links],
        "provenance": [{
            "fieldName": item.field_name,
            "sourceUrl": item.source_url,
            "confidence": item.confidence,
            "verificationStatus": item.verification_status,
            "fetchedAt": item.fetched_at.isoformat(),
        } for item in journal.profile_fields],
    }


# Jild + son + yil — jurnaldagi bitta nashr sonini aniqlovchi kalit.
_ISSUE_KEY = (
    func.coalesce(Article.volume, "")
    + "|"
    + func.coalesce(Article.issue, "")
    + "|"
    + func.coalesce(cast(Article.publication_year, String), "")
)


def journal_counts(db: Session, journal_ids: list[int] | None = None) -> dict[int, tuple[int, int]]:
    """Jurnal bo‘yicha maqola va son sonini bitta aggregate so‘rov bilan oladi.

    Ilgari `journal_payload` `journal.articles` ni o‘qir, `selectinload` esa
    barcha maqola obyektlarini xotiraga yuklardi — 493 ta jurnal uchun 100 mingdan
    ortiq ORM obyekti va ~3 soniya.
    """
    statement = (
        select(Article.journal_id, func.count(), func.count(distinct(_ISSUE_KEY)))
        .where(Article.is_deleted.is_(False))
        .group_by(Article.journal_id)
    )
    if journal_ids is not None:
        statement = statement.where(Article.journal_id.in_(journal_ids))
    return {row[0]: (row[1], row[2]) for row in db.execute(statement)}


def journal_payload(
    journal: Journal,
    *,
    include_profile: bool = False,
    counts: tuple[int, int] = (0, 0),
) -> dict[str, object]:
    article_count, issue_count = counts
    payload: dict[str, object] = {
        "id": journal.slug,
        "name": journal.name,
        "shortName": journal.short_name,
        "publisher": journal.publisher,
        "city": canonical_city(journal.city),
        "cityRaw": journal.city,
        "fields": journal.fields,
        "issn": journal.issn or "—",
        "eissn": journal.eissn,
        "languages": journal.languages,
        "oakStatus": journal.oak_status,
        "access": journal.access,
        **source_status(journal),
        "articleCount": article_count,
        "issueCount": issue_count,
        "founded": journal.founded,
        "website": journal.website or "#",
        "description": journal.description or "",
    }
    if include_profile:
        payload["profile"] = profile_payload(journal)
    return payload


def article_payload(article: Article) -> dict[str, object]:
    return {
        "id": str(article.id),
        "title": article.title,
        "authors": article.authors,
        "journalId": article.journal.slug,
        "journalName": article.journal.name,
        "publicationDate": article.publication_date,
        "year": article.publication_year or 0,
        "volume": article.volume or "—",
        "issue": article.issue or "—",
        "pages": article.pages or "—",
        "language": article.language or "Noma’lum",
        "fields": article.fields,
        "abstract": article.abstract or "Annotatsiya taqdim etilmagan.",
        "keywords": article.keywords,
        "doi": article.doi,
        "hasPdf": bool(article.pdf_url),
        "pdfUrl": article.pdf_url,
        "harvestedAt": article.harvested_at.isoformat(),
        "landingUrl": article.landing_url,
        "citations": citation_formats(article),
        "isDemo": bool(article.doi and article.doi.startswith("10.0000/demo")),
    }


@app.get("/api/health")
def health() -> dict[str, object]:
    return {
        "status": "ok",
        "database": "postgresql" if DATABASE_URL.startswith("postgresql") else "sqlite",
        "time": datetime.utcnow().isoformat() + "Z",
    }


@app.get("/api/stats")
def stats(db: Session = Depends(get_db)) -> dict[str, int]:
    journals_count = db.scalar(select(func.count()).select_from(Journal)) or 0
    articles_count = db.scalar(select(func.count()).select_from(Article).where(Article.is_deleted.is_(False))) or 0
    sources_count = db.scalar(select(func.count()).select_from(HarvestSource).where(HarvestSource.status == "healthy")) or 0
    return {"journals": journals_count, "articles": articles_count, "healthySources": sources_count}


def matching_journal_ids(db: Session, fields: list[str], cities: list[str]) -> set[int] | None:
    """Soha/shahar filtriga mos jurnal IDlari, filtr bo‘lmasa None.

    `fields` JSON ustunda saqlangani uchun SQL emas, Python tarafda tekshiramiz —
    jurnallar bor-yo‘g‘i 493 ta, bu arzon va aniq.
    """
    if not fields and not cities:
        return None
    wanted_fields = set(fields)
    wanted_raw_cities = {variant for city in cities for variant in city_variants(city)}
    matched: set[int] = set()
    for journal_id, journal_fields, journal_city in db.execute(select(Journal.id, Journal.fields, Journal.city)):
        if wanted_fields and not wanted_fields.intersection(journal_fields or []):
            continue
        if wanted_raw_cities and journal_city not in wanted_raw_cities:
            continue
        matched.add(journal_id)
    return matched


@app.get("/api/facets")
def facets(db: Session = Depends(get_db)) -> dict[str, object]:
    """Filtr uchun haqiqiy soha/shahar ro‘yxati va sanoqlari.

    Ilgari frontend 7 ta sohani demo ma’lumotdan qattiq yozib olgan edi, shu
    sabab bazadagi 24 tadan 17 tasi umuman tanlanmasdi.
    """
    article_counts: dict[int, int] = dict(
        db.execute(
            select(Article.journal_id, func.count())
            .where(Article.is_deleted.is_(False))
            .group_by(Article.journal_id)
        ).all()
    )
    # Jurnal bir nechta sohaga tegishli bo‘lishi mumkin, shuning uchun guruh
    # sanog‘i qo‘shish emas, birlashma bo‘lishi kerak — aks holda bitta jurnal
    # (va uning maqolalari) guruh ichida ikki marta sanalardi.
    field_members: dict[str, set[int]] = {}
    city_journals: dict[str, int] = {}
    city_articles: dict[str, int] = {}
    for journal_id, journal_fields, journal_city in db.execute(select(Journal.id, Journal.fields, Journal.city)):
        articles = article_counts.get(journal_id, 0)
        for name in journal_fields or []:
            field_members.setdefault(name, set()).add(journal_id)
        city = canonical_city(journal_city)
        city_journals[city] = city_journals.get(city, 0) + 1
        city_articles[city] = city_articles.get(city, 0) + articles

    def totals(journal_ids: set[int]) -> tuple[int, int]:
        return len(journal_ids), sum(article_counts.get(item, 0) for item in journal_ids)

    def facet(name: str) -> dict[str, object]:
        journals, articles = totals(field_members[name])
        return {"name": name, "journals": journals, "articles": articles}

    grouped: list[dict[str, object]] = []
    for group, names in FIELD_GROUPS:
        present = [name for name in names if name in field_members]
        if not present:
            continue
        members = set().union(*(field_members[name] for name in present))
        journals, articles = totals(members)
        grouped.append({
            "group": group,
            "journals": journals,
            "articles": articles,
            "fields": sorted((facet(name) for name in present), key=lambda item: -int(item["articles"])),
        })
    ungrouped = [name for name in field_members if field_group(name) == OTHER_GROUP]
    if ungrouped:
        members = set().union(*(field_members[name] for name in ungrouped))
        journals, articles = totals(members)
        grouped.append({
            "group": OTHER_GROUP,
            "journals": journals,
            "articles": articles,
            "fields": [facet(name) for name in sorted(ungrouped)],
        })
    field_journals = {name: len(members) for name, members in field_members.items()}
    return {
        "fieldGroups": grouped,
        "fieldCount": len(field_journals),
        "cities": [
            {"name": name, "journals": city_journals[name], "articles": city_articles[name]}
            for name in sorted(city_journals, key=lambda name: -city_journals[name])
        ],
    }


def _total_of(db: Session, statement) -> int:
    """Sahifalashdan oldingi umumiy son."""
    return db.scalar(select(func.count()).select_from(statement.order_by(None).subquery())) or 0


@app.get("/api/journals")
def list_journals(
    response: Response,
    q: str | None = None,
    city: list[str] = Query(default=[]),
    field: list[str] = Query(default=[]),
    oai_only: bool = False,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
) -> list[dict[str, object]]:
    statement = select(Journal).options(selectinload(Journal.harvest_sources)).order_by(Journal.name)
    if q:
        needle = f"%{q.strip()}%"
        statement = statement.where(or_(Journal.name.ilike(needle), Journal.publisher.ilike(needle), Journal.issn.ilike(needle)))
    if oai_only:
        statement = statement.join(Journal.harvest_sources).distinct()
    allowed = matching_journal_ids(db, field, city)
    if allowed is not None:
        statement = statement.where(Journal.id.in_(allowed))
    # Limit filtrlardan keyin qo‘llanadi — ilgari SQL limiti oldin ishlab,
    # soha filtri faqat birinchi N jurnal ichidan qidirardi.
    response.headers["X-Total-Count"] = str(_total_of(db, statement))
    journals = list(db.scalars(statement.offset(offset).limit(limit)).unique())
    counts = journal_counts(db, [journal.id for journal in journals])
    return [journal_payload(journal, counts=counts.get(journal.id, (0, 0))) for journal in journals]


@app.get("/api/journals/{slug}")
def get_journal(slug: str, db: Session = Depends(get_db)) -> dict[str, object]:
    journal = db.scalar(
        select(Journal).where(Journal.slug == slug).options(
            selectinload(Journal.harvest_sources),
            selectinload(Journal.profile),
            selectinload(Journal.contacts),
            selectinload(Journal.editorial_members),
            selectinload(Journal.policies),
            selectinload(Journal.sections),
            selectinload(Journal.indexing_claims),
            selectinload(Journal.links),
            selectinload(Journal.profile_fields),
        )
    )
    if journal is None:
        raise HTTPException(status_code=404, detail="Jurnal topilmadi")
    counts = journal_counts(db, [journal.id])
    payload = journal_payload(journal, include_profile=True, counts=counts.get(journal.id, (0, 0)))
    latest_import = db.scalar(select(OakImportRun).where(OakImportRun.status == "succeeded").order_by(OakImportRun.started_at.desc()).limit(1))
    registry_statement = select(OakRegistryEntry).where(OakRegistryEntry.journal_id == journal.id).order_by(OakRegistryEntry.id)
    if latest_import is not None:
        has_snapshot = db.scalar(
            select(func.count()).select_from(OakRegistrySnapshotEntry).where(OakRegistrySnapshotEntry.import_run_id == latest_import.id)
        )
        if has_snapshot:
            registry_statement = registry_statement.join(OakRegistrySnapshotEntry).where(
                OakRegistrySnapshotEntry.import_run_id == latest_import.id
            )
    registry_entries = db.scalars(registry_statement)
    payload["oakRecords"] = [{
        "area": item.area,
        "specialtyCode": item.specialty_code,
        "status": item.status,
        "decision": item.decision,
        "added": item.added,
        "removed": item.removed,
        "sourceReference": item.source_reference,
        "sourceUrl": item.link,
    } for item in registry_entries]
    return payload


@app.get("/api/articles")
def list_articles(
    response: Response,
    q: str | None = None,
    journal_slug: str | None = None,
    year: int | None = None,
    city: list[str] = Query(default=[]),
    field: list[str] = Query(default=[]),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
) -> list[dict[str, object]]:
    statement = select(Article).options(selectinload(Article.journal)).where(Article.is_deleted.is_(False)).order_by(Article.publication_year.desc(), Article.id.desc())
    if q:
        needle = f"%{q.strip()}%"
        statement = statement.where(or_(Article.title.ilike(needle), Article.abstract.ilike(needle), cast(Article.authors, String).ilike(needle)))
    if journal_slug:
        statement = statement.join(Article.journal).where(Journal.slug == journal_slug)
    if year:
        statement = statement.where(Article.publication_year == year)
    # Soha/shahar filtri endi serverda — ilgari frontend faqat yuklangan 500 ta
    # maqola ichidan filtrlardi, ya’ni 106 mingdan qolgani ko‘rinmasdi.
    allowed = matching_journal_ids(db, field, city)
    if allowed is not None:
        statement = statement.where(Article.journal_id.in_(allowed))
    response.headers["X-Total-Count"] = str(_total_of(db, statement))
    return [article_payload(article) for article in db.scalars(statement.offset(offset).limit(limit))]


@admin.get("/sources")
def list_sources(db: Session = Depends(get_db)) -> list[dict[str, object]]:
    sources = db.scalars(select(HarvestSource).options(selectinload(HarvestSource.journal)).order_by(HarvestSource.updated_at.desc()))
    return [
        {
            "id": source.id,
            "journal": source.journal.name,
            "journalSlug": source.journal.slug,
            "baseUrl": source.base_url,
            "status": source.status,
            "repositoryName": source.repository_name,
            "formats": source.available_formats,
            "lastSuccessAt": source.last_success_at,
            "lastError": source.last_error,
        }
        for source in sources
    ]


@admin.get("/dashboard")
def admin_dashboard(db: Session = Depends(get_db)) -> dict[str, object]:
    latest_import = db.scalar(select(OakImportRun).order_by(OakImportRun.started_at.desc()).limit(1))
    source_rows = db.execute(select(HarvestSource.status, func.count()).group_by(HarvestSource.status)).all()
    source_counts = {str(status): count for status, count in source_rows}
    current_registry_entries = 0
    registry_publications = 0
    if latest_import is not None:
        current_registry_entries = db.scalar(
            select(func.count()).select_from(OakRegistrySnapshotEntry).where(OakRegistrySnapshotEntry.import_run_id == latest_import.id)
        ) or 0
        registry_publications = db.scalar(
            select(OakRegistrySnapshotMeta.publication_count).where(OakRegistrySnapshotMeta.import_run_id == latest_import.id)
        ) or 0
    profiles = profile_stats(db)
    return {
        "journals": db.scalar(select(func.count()).select_from(Journal)) or 0,
        "activeJournals": db.scalar(select(func.count()).select_from(Journal).where(Journal.oak_status == "active")) or 0,
        "removedJournals": db.scalar(select(func.count()).select_from(Journal).where(Journal.oak_status == "removed")) or 0,
        "articles": db.scalar(select(func.count()).select_from(Article).where(Article.is_deleted.is_(False))) or 0,
        "registryEntries": current_registry_entries or db.scalar(select(func.count()).select_from(OakRegistryEntry)) or 0,
        "registryPublications": registry_publications,
        "profiles": profiles,
        "sources": source_counts,
        "auditQueue": queue_stats(db),
        "profileQueue": profile_queue_stats(db),
        "latestImport": None if latest_import is None else {
            "id": latest_import.id,
            "status": latest_import.status,
            "sourceUrl": latest_import.source_url,
            "startedAt": latest_import.started_at,
            "finishedAt": latest_import.finished_at,
            "recordsSeen": latest_import.records_seen,
            "registryCreated": latest_import.registry_created,
            "journalsCreated": latest_import.journals_created,
            "journalsUpdated": latest_import.journals_updated,
        },
    }


@admin.get("/oak/runs")
def oak_runs(limit: int = Query(default=10, ge=1, le=100), db: Session = Depends(get_db)) -> list[dict[str, object]]:
    runs = db.scalars(select(OakImportRun).order_by(OakImportRun.started_at.desc()).limit(limit))
    return [{
        "id": run.id,
        "status": run.status,
        "sourceUrl": run.source_url,
        "startedAt": run.started_at,
        "finishedAt": run.finished_at,
        "recordsSeen": run.records_seen,
        "registryCreated": run.registry_created,
        "journalsCreated": run.journals_created,
        "journalsUpdated": run.journals_updated,
        "error": run.error_summary,
    } for run in runs]


@admin.get("/audit/jobs")
def audit_jobs(
    status: str | None = None,
    limit: int = Query(default=50, ge=1, le=500),
    db: Session = Depends(get_db),
) -> list[dict[str, object]]:
    statement = select(AuditJob).options(selectinload(AuditJob.journal)).order_by(AuditJob.created_at.desc()).limit(limit)
    if status:
        statement = statement.where(AuditJob.status == status)
    jobs = db.scalars(statement)
    return [{
        "id": job.id,
        "journal": job.journal.name,
        "journalSlug": job.journal.slug,
        "website": job.candidate_url,
        "status": job.status,
        "attempts": job.attempts,
        "discoveredBaseUrl": job.discovered_base_url,
        "lastError": job.last_error,
        "createdAt": job.created_at,
        "finishedAt": job.finished_at,
    } for job in jobs]


@admin.get("/profile/jobs")
def profile_jobs(
    status: str | None = None,
    limit: int = Query(default=50, ge=1, le=500),
    db: Session = Depends(get_db),
) -> list[dict[str, object]]:
    statement = select(ProfileJob).options(selectinload(ProfileJob.journal)).order_by(
        ProfileJob.attempts.desc(), ProfileJob.finished_at.desc(), ProfileJob.created_at.desc()
    ).limit(limit)
    if status:
        statement = statement.where(ProfileJob.status == status)
    jobs = db.scalars(statement)
    return [{
        "id": job.id,
        "journal": job.journal.name,
        "journalSlug": job.journal.slug,
        "website": job.source_url,
        "status": job.status,
        "attempts": job.attempts,
        "completenessScore": job.completeness_score,
        "lastError": job.last_error,
        "createdAt": job.created_at,
        "finishedAt": job.finished_at,
    } for job in jobs]


@admin.post("/audit/queue")
def queue_audit_jobs(input: AuditQueueInput, db: Session = Depends(get_db)) -> dict[str, int]:
    return {"queued": enqueue_audits(db, limit=input.limit)}


@admin.post("/audit/process")
def process_queued_audits(input: AuditProcessInput, db: Session = Depends(get_db)) -> dict[str, int]:
    return process_audit_jobs(db, limit=input.limit)


@admin.post("/profiles/queue")
def queue_profile_jobs(input: ProfileQueueInput, db: Session = Depends(get_db)) -> dict[str, int]:
    return {"queued": enqueue_profiles(db, limit=input.limit, refresh=input.refresh)}


@admin.post("/profiles/process")
def process_queued_profiles(input: ProfileProcessInput, db: Session = Depends(get_db)) -> dict[str, int]:
    return process_profile_jobs(db, limit=input.limit, workers=input.workers)


@admin.post("/sources/audit")
def audit(input: SourceInput, db: Session = Depends(get_db)) -> dict[str, object]:
    journal = db.scalar(select(Journal).where(Journal.slug == input.journal_slug))
    if journal is None:
        raise HTTPException(status_code=404, detail="Jurnal topilmadi")
    try:
        source = audit_source(db, journal, str(input.base_url))
    except Exception as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return {"id": source.id, "status": source.status, "repositoryName": source.repository_name, "formats": source.available_formats}


@admin.post("/sources/harvest")
def run_harvest(input: HarvestInput, db: Session = Depends(get_db)) -> dict[str, object]:
    journal = db.scalar(select(Journal).where(Journal.slug == input.journal_slug))
    if journal is None:
        raise HTTPException(status_code=404, detail="Jurnal topilmadi")
    source = db.scalar(
        select(HarvestSource).where(
            HarvestSource.journal_id == journal.id,
            HarvestSource.base_url == str(input.base_url),
        )
    )
    if source is None or source.status != "healthy":
        try:
            source = audit_source(db, journal, str(input.base_url))
        except Exception as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
    try:
        run = ingest_source(db, source, from_date=input.from_date, page_limit=input.page_limit)
    except Exception as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return {
        "runId": run.id,
        "status": run.status,
        "seen": run.records_seen,
        "created": run.records_created,
        "updated": run.records_updated,
        "deleted": run.records_deleted,
    }


@admin.post("/profiles/collect")
def collect_journal_profile(input: ProfileCollectInput, db: Session = Depends(get_db)) -> dict[str, object]:
    journal = db.scalar(select(Journal).where(Journal.slug == input.journal_slug))
    if journal is None:
        raise HTTPException(status_code=404, detail="Jurnal topilmadi")
    try:
        profile = collect_profile(db, journal)
    except Exception as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return {
        "journalSlug": journal.slug,
        "status": "collected",
        "completenessScore": profile.completeness_score,
        "fetchedAt": profile.fetched_at,
    }


app.include_router(admin)
