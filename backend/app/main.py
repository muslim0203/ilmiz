from __future__ import annotations

import logging
import os
import secrets
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel, Field, HttpUrl
from sqlalchemy import String, case, cast, distinct, func, or_, select
from sqlalchemy.orm import Session, selectinload

from .db import DATABASE_URL, SessionLocal, get_db, init_db
from .models import (
    Article,
    User,
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
from .services import auth as auth_service
from .services import authorship
from .services import journal_edit
from .services import search_index
from .services.search_text import LIKE_ESCAPE, escape_like, query_words
from .services.payloads import article_payload
from .services.ingest import audit_source, ingest_source
from harvester.oai_harvester import OAIError
from .services.profile_collector import collect_profile
from .services.profile_queue import enqueue_profiles, process_profile_jobs, profile_queue_stats, profile_stats
logger = logging.getLogger(__name__)

from .services import seo
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
# Sitemap 25 000 URL, SEO qobig'i esa to'liq annotatsiya bilan ketadi —
# siqilmasa TTFB va Core Web Vitals'ga urib ketadi.
app.add_middleware(GZipMiddleware, minimum_size=800)

DEV_CORS_ORIGINS = ["http://127.0.0.1:5173", "http://localhost:5173"]


def cors_origins() -> list[str]:
    """Ruxsat etilgan CORS originlari.

    `ILMIZ_CORS_ORIGINS` (vergul bilan) berilsa faqat o‘sha. Aks holda
    prod'da (`ILMIZ_PUBLIC_URL` https) ro‘yxat bo‘sh — sayt bir originda;
    dev'da Vite portlari. Ilgari dev originlari prod'da ham ochiq edi.
    """
    raw = os.getenv("ILMIZ_CORS_ORIGINS")
    if raw is not None:
        return [item.strip() for item in raw.split(",") if item.strip()]
    if auth_service.public_base_url().startswith("https://"):
        return []
    return DEV_CORS_ORIGINS


app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins(),
    allow_methods=["*"],
    # Frontend sahifalash uchun umumiy sonni shu header'dan o'qiydi.
    allow_headers=["*"],
    expose_headers=["X-Total-Count"],
)


def admin_token() -> str:
    """Har so‘rovda o‘qiladi — tokenni almashtirish uchun restart shart emas."""
    return os.getenv("ILMIZ_ADMIN_TOKEN", "").strip()


def _token_matches(authorization: str | None, x_admin_token: str | None) -> bool:
    expected = admin_token()
    if not expected:
        return False
    provided = x_admin_token
    if not provided and authorization and authorization.lower().startswith("bearer "):
        provided = authorization[7:]
    if not provided:
        return False
    # `compare_digest` `str` uchun faqat ASCII qabul qiladi — kirillcha header
    # `TypeError` bilan 500 berardi. Baytlar bilan har qanday matn taqqoslanadi.
    return secrets.compare_digest(provided.strip().encode("utf-8"), expected.encode("utf-8"))


def _same_site_request(request: Request) -> bool:
    """So‘rov o‘z saytimizdan kelganmi (CSRF).

    Brauzer `Origin` (yoki hech bo‘lmasa `Sec-Fetch-Site`) yuboradi. Origin
    `ILMIZ_PUBLIC_URL` ga yoki so‘rovning o‘z `Host` iga mos kelsa — o‘zimizniki.
    Ikkalasi ham yo‘q (curl, testlar, eski brauzer) — `SameSite=Lax` cookie
    o‘zi himoya qiladi, o‘tkazamiz.
    """
    origin = request.headers.get("origin")
    if origin:
        if origin.rstrip("/") == auth_service.public_base_url():
            return True
        host = request.headers.get("host", "")
        origin_host = origin.split("://", 1)[-1].rstrip("/")
        return bool(host) and origin_host.casefold() == host.casefold()
    fetch_site = request.headers.get("sec-fetch-site")
    if fetch_site:
        return fetch_site in {"same-origin", "none"}
    return True


def check_admin_access(
    db: Session,
    *,
    authorization: str | None,
    x_admin_token: str | None,
    session_token: str | None,
) -> None:
    """Barcha `/api/admin/*` so‘rovlarini himoyalaydi.

    Ikki yo‘l bor: `is_admin` bo‘lgan foydalanuvchining sessiyasi yoki
    `ILMIZ_ADMIN_TOKEN`. Token birinchi adminni tayinlash uchun zaxira yo‘l
    bo‘lib qoladi — hech bir admin yo‘q holatda tizimga kirib bo‘lmay
    qolmasligi uchun.
    """
    user = auth_service.user_for_token(db, session_token)
    if user is not None and user.is_admin:
        return
    if _token_matches(authorization, x_admin_token):
        # Token muddatsiz va auditsiz bearer — har ishlatilishi logda qolsin,
        # shunda oqib ketgan token sezilmay qolmaydi.
        logger.warning("Admin API'ga ILMIZ_ADMIN_TOKEN bilan kirildi")
        return
    if not admin_token() and not auth_service.any_admin_exists(db):
        raise HTTPException(
            status_code=503,
            detail=(
                "Admin API o‘chirilgan: birorta admin foydalanuvchi yo‘q va "
                "ILMIZ_ADMIN_TOKEN sozlanmagan."
            ),
        )
    raise HTTPException(status_code=401, detail="Admin huquqi yo‘q.")


def require_admin(
    request: Request,
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None),
    x_admin_token: str | None = Header(default=None),
) -> None:
    check_admin_access(
        db,
        authorization=authorization,
        x_admin_token=x_admin_token,
        session_token=request.cookies.get(auth_service.SESSION_COOKIE),
    )


MUTATING_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


@app.middleware("http")
async def csrf_guard(request: Request, call_next):
    """Cookie bilan kelgan o‘zgartiruvchi so‘rovlar faqat o‘z saytdan.

    Sessiya cookie'si `SameSite=Lax`; bu qatlam subdomen XSS yoki eski
    brauzer holatida ikkinchi to‘siq. Cookie'siz so‘rovlar (admin token,
    ommaviy GET'lar) tegmaydi.
    """
    if (
        request.method in MUTATING_METHODS
        and request.url.path.startswith("/api/")
        and request.cookies.get(auth_service.SESSION_COOKIE)
        and not _same_site_request(request)
    ):
        return JSONResponse(status_code=403, content={"detail": "So‘rov boshqa saytdan kelgan (CSRF)."})
    return await call_next(request)


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
            with SessionLocal() as db:
                check_admin_access(
                    db,
                    authorization=request.headers.get("authorization"),
                    x_admin_token=request.headers.get("x-admin-token"),
                    session_token=request.cookies.get(auth_service.SESSION_COOKIE),
                )
        except HTTPException as error:
            return JSONResponse(status_code=error.status_code, content={"detail": error.detail})
    return await call_next(request)


@app.middleware("http")
async def indexing_guard(request: Request, call_next):
    response = await call_next(request)
    if not seo.is_production_host() or request.url.path.startswith("/api/"):
        response.headers["X-Robots-Tag"] = "noindex, follow"
    return response


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


def activity_since_year() -> int:
    """Faollik oynasining boshlanish yili.

    Aniq sana bo‘yicha oxirgi 365 kun ishonchsiz: `publication_date` erkin
    matn va formati manbadan manbaga farq qiladi. `publication_year` esa
    butun bazada to‘ldirilgan, shuning uchun oyna yil bo‘yicha olinadi.
    """
    return datetime.utcnow().year - 1


def recent_counts_subquery(since_year: int):
    return (
        select(Article.journal_id.label("journal_id"), func.count().label("recent"))
        .where(Article.is_deleted.is_(False), Article.publication_year >= since_year)
        .group_by(Article.journal_id)
        .subquery()
    )


def journal_counts(db: Session, journal_ids: list[int] | None = None) -> dict[int, tuple[int, int, int]]:
    """Jurnal bo‘yicha maqola va son sonini bitta aggregate so‘rov bilan oladi.

    Ilgari `journal_payload` `journal.articles` ni o‘qir, `selectinload` esa
    barcha maqola obyektlarini xotiraga yuklardi — 493 ta jurnal uchun 100 mingdan
    ortiq ORM obyekti va ~3 soniya.
    """
    def compute() -> dict[int, tuple[int, int, int]]:
        since = activity_since_year()
        statement = (
            select(
                Article.journal_id,
                func.count(),
                func.count(distinct(_ISSUE_KEY)),
                func.sum(case((Article.publication_year >= since, 1), else_=0)),
            )
            .where(Article.is_deleted.is_(False))
            .group_by(Article.journal_id)
        )
        return {row[0]: (row[1], row[2], int(row[3] or 0)) for row in db.execute(statement)}

    # `count(distinct volume|issue|year)` 104 000 qator ustidan ishlaydi va
    # har bir katalog so‘rovida takrorlanardi (~300 ms). Qiymatlar faqat
    # harvest’dan keyin o‘zgaradi, shuning uchun to‘liq xarita keshlanadi va
    # kerakli jurnallar undan kesib olinadi.
    everything: dict[int, tuple[int, int, int]] = seo.cached("journal_counts", compute)
    if journal_ids is None:
        return everything
    wanted = set(journal_ids)
    return {key: value for key, value in everything.items() if key in wanted}


def journal_payload(
    journal: Journal,
    *,
    include_profile: bool = False,
    counts: tuple[int, int, int] = (0, 0, 0),
) -> dict[str, object]:
    article_count, issue_count, recent_count = counts
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
        # So‘nggi faollik: jurnallarni standart tartiblash shu bo‘yicha.
        "recentArticles": recent_count,
        "founded": journal.founded,
        "website": journal.website or "#",
        "description": journal.description or "",
    }
    if include_profile:
        payload["profile"] = profile_payload(journal)
    return payload



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


# Kirilldan lotinga — qidiruv uchun. Muallif ismlari bir jurnalda kirillda,
# boshqasida lotinda yoziladi; foydalanuvchi esa bittasini yozadi.
_CYRILLIC_TO_LATIN = str.maketrans({
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "yo", "ж": "j",
    "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m", "н": "n", "о": "o",
    "п": "p", "р": "r", "с": "s", "т": "t", "у": "u", "ф": "f", "х": "x", "ц": "ts",
    "ч": "ch", "ш": "sh", "щ": "sh", "ъ": "", "ы": "i", "ь": "", "э": "e", "ю": "yu",
    "я": "ya", "ғ": "g", "қ": "q", "ҳ": "h", "ў": "o",
})


def _search_forms(word: str) -> list[str]:
    """So'zning qidiriladigan shakllari: o'zi va lotin transliteratsiyasi."""
    forms = [word]
    latin = word.casefold().translate(_CYRILLIC_TO_LATIN)
    if latin and latin != word.casefold():
        forms.append(latin)
    return forms


def text_search_filter(query: str, columns: list):
    """Har bir so'z alohida qidiriladi va hammasi topilishi shart.

    Ilgari butun so'rov bitta bo'lak sifatida qidirilardi. Mualliflar esa
    familiya-birinchi saqlanadi ("Sharofiddinov, Kamoliddin"), shuning uchun
    "Kamoliddin Sharofiddinov" hech qachon topilmasdi.
    """
    conditions = []
    for word in query.split():
        needle = word.strip()
        if len(needle) < 2:
            continue
        variants = [
            column.ilike(f"%{escape_like(form)}%", escape=LIKE_ESCAPE)
            for form in _search_forms(needle)
            for column in columns
        ]
        conditions.append(or_(*variants))
    return conditions


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
    sort: str = Query(default="activity", pattern="^(activity|name)$"),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
) -> list[dict[str, object]]:
    statement = select(Journal).options(selectinload(Journal.harvest_sources))
    if q:
        for condition in text_search_filter(q, [Journal.name, Journal.publisher, Journal.issn]):
            statement = statement.where(condition)

    if oai_only:
        statement = statement.join(Journal.harvest_sources).distinct()
    allowed = matching_journal_ids(db, field, city)
    if allowed is not None:
        statement = statement.where(Journal.id.in_(allowed))
    # Limit filtrlardan keyin qo‘llanadi — ilgari SQL limiti oldin ishlab,
    # soha filtri faqat birinchi N jurnal ichidan qidirardi.
    # Umumiy son filtrlardan keyin, lekin tartiblash join'idan OLDIN hisoblanadi:
    # join faqat tartib uchun kerak, sanoqqa ta'sir qilmaydi va uni sekinlashtiradi.
    response.headers["X-Total-Count"] = str(_total_of(db, statement))

    if sort == "activity":
        # Tartiblash sahifalash limitidan OLDIN, SQL tarafida bo'lishi shart —
        # aks holda faqat joriy sahifa ichida tartiblanardi.
        recent = recent_counts_subquery(activity_since_year())
        statement = statement.outerjoin(recent, recent.c.journal_id == Journal.id).order_by(
            func.coalesce(recent.c.recent, 0).desc(), Journal.name
        )
    else:
        statement = statement.order_by(Journal.name)

    journals = list(db.scalars(statement.offset(offset).limit(limit)).unique())
    counts = journal_counts(db, [journal.id for journal in journals])
    return [journal_payload(journal, counts=counts.get(journal.id, (0, 0, 0))) for journal in journals]


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
    payload = journal_payload(journal, include_profile=True, counts=counts.get(journal.id, (0, 0, 0)))
    payload["archiveYears"] = list(db.scalars(
        select(Article.publication_year).where(
            Article.journal_id == journal.id, Article.is_deleted.is_(False),
            Article.publication_year.between(1000, 2999),
        ).distinct().order_by(Article.publication_year.desc())
    ))
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
        # FTS5 indeksi bo'lsa — mos kelish bo'yicha tartiblangan tez qidiruv.
        # Bo'lmasa (PostgreSQL yoki migratsiyasiz baza) eski yo'l ishlaydi:
        # `search_text` allaqachon kichik harf va lotinlashtirilgan, shuning
        # uchun `ilike` (ya'ni har qator uchun `lower()`) kerak emas.
        expression = search_index.match_expression(q) if search_index.available(db) else None
        if expression:
            statement = search_index.apply(statement, expression)
        else:
            for word in query_words(q):
                statement = statement.where(
                    Article.search_text.like(f"%{escape_like(word)}%", escape=LIKE_ESCAPE)
                )
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


@app.get("/api/articles/{article_id}")
def get_article(article_id: int, db: Session = Depends(get_db)) -> dict[str, object]:
    """Maqolaning to‘g‘ridan-to‘g‘ri sahifasi uchun — ro‘yxatdan qidirib
    o‘tirmasdan bitta yozuvni oladi."""
    article = db.scalar(
        select(Article).where(Article.id == article_id).options(selectinload(Article.journal))
    )
    if article is None or article.is_deleted:
        raise HTTPException(status_code=404, detail="Maqola topilmadi")
    payload = article_payload(article)
    payload["journalSlug"] = article.journal.slug if article.journal else None
    return payload


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


def _admin_error(error: Exception) -> HTTPException:
    """Admin amali xatosi: kutilgan xatolar matni bilan, qolgani umumiy xabar.

    `str(error)` httpx/SSL/SQLAlchemy xabarlarini (ichki yo‘llar, URL'lar)
    to‘g‘ridan-to‘g‘ri mijozga chiqarardi; ular endi faqat logga tushadi.
    """
    logger.exception("Admin amali yiqildi: %s", type(error).__name__)
    if isinstance(error, (OAIError, ValueError, journal_edit.ValidationError)):
        return HTTPException(status_code=422, detail=str(error))
    return HTTPException(status_code=422, detail="Amal bajarilmadi; batafsil sabab server logida.")


@admin.post("/sources/audit")
def audit(input: SourceInput, db: Session = Depends(get_db)) -> dict[str, object]:
    journal = db.scalar(select(Journal).where(Journal.slug == input.journal_slug))
    if journal is None:
        raise HTTPException(status_code=404, detail="Jurnal topilmadi")
    try:
        source = audit_source(db, journal, str(input.base_url))
    except Exception as error:
        raise _admin_error(error) from error
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
            raise _admin_error(error) from error
    try:
        run = ingest_source(db, source, from_date=input.from_date, page_limit=input.page_limit)
    except Exception as error:
        raise _admin_error(error) from error
    return {
        "runId": run.id,
        "status": run.status,
        "seen": run.records_seen,
        "created": run.records_created,
        "updated": run.records_updated,
        "deleted": run.records_deleted,
    }


class JournalEditInput(BaseModel):
    """Faqat yuborilgan maydonlar o‘zgaradi (`exclude_unset`)."""

    model_config = {"extra": "forbid"}

    name: str | None = None
    short_name: str | None = None
    publisher: str | None = None
    city: str | None = None
    fields: list[str] | None = None
    issn: str | None = None
    eissn: str | None = None
    languages: list[str] | None = None
    oak_status: str | None = None
    access: str | None = None
    founded: int | None = None
    website: str | None = None
    description: str | None = None
    # `journal_profiles` da turadi — to'liqlik bali aynan shularni sanaydi.
    summary: str | None = None
    address: str | None = None
    latest_issue: str | None = None


@admin.get("/journals")
def admin_journals(
    q: str | None = Query(default=None, max_length=200),
    limit: int = Query(default=30, ge=1, le=100),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    """Tahrirlash uchun jurnal qidirish."""
    # Manfiy `limit` SQLite'da "cheksiz" degani edi — butun jadval + har
    # jurnal uchun `manually_edited` so‘rovi.
    statement = select(Journal).order_by(Journal.name).limit(limit)
    if q and q.strip():
        conditions = text_search_filter(q.strip(), [Journal.name, Journal.publisher, Journal.issn])
        for condition in conditions:
            statement = statement.where(condition)
    journals = list(db.scalars(statement))
    manual = {
        journal.id: sorted(journal_edit.manually_edited(db, journal.id)) for journal in journals
    }
    return {
        "journals": [
            {
                "slug": journal.slug,
                "name": journal.name,
                "publisher": journal.publisher,
                "issn": journal.issn,
                "city": journal.city,
                "manualFields": manual[journal.id],
            }
            for journal in journals
        ]
    }


class ContactRow(BaseModel):
    kind: str
    value: str
    label: str | None = None


class ContactsInput(BaseModel):
    """Butun ro‘yxat almashtiriladi — forma bitta tugma bilan saqlanadi."""

    contacts: list[ContactRow]


def _journal_or_404(slug: str, db: Session) -> Journal:
    journal = db.scalar(select(Journal).where(Journal.slug == slug))
    if journal is None:
        raise HTTPException(status_code=404, detail="Jurnal topilmadi")
    return journal


@admin.get("/journals/{slug}")
def admin_journal(slug: str, db: Session = Depends(get_db)) -> dict[str, object]:
    journal = _journal_or_404(slug, db)
    return {
        **journal_edit.editable_payload(db, journal),
        "contacts": journal_edit.contacts_payload(journal),
    }


@admin.put("/journals/{slug}/contacts")
def admin_edit_contacts(
    slug: str, payload: ContactsInput, db: Session = Depends(get_db)
) -> dict[str, object]:
    """Aloqa ma‘lumotlarini almashtiradi.

    Scraper telefon raqamlarini buzib olgan (bazada 127 ta juftlashmagan
    qavsli yozuv) va ba‘zi «manzil» maydonlariga butun tahririyat ro‘yxati
    tushib qolgan — ularni shu yerdan tuzatiladi.
    """
    journal = _journal_or_404(slug, db)
    try:
        contacts, warnings = journal_edit.replace_contacts(
            db, journal, [row.model_dump() for row in payload.contacts]
        )
    except journal_edit.ValidationError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return {"contacts": contacts, "warnings": warnings}


@admin.patch("/journals/{slug}")
def admin_edit_journal(
    slug: str, payload: JournalEditInput, db: Session = Depends(get_db)
) -> dict[str, object]:
    """Jurnal maydonlarini qo‘lda tuzatadi.

    Yuqori manbalar (OAK reestri, tadqiq.uz) ham xato qiladi — shuning uchun
    tekshirgan odamning tuzatishi ustun turadi va `manual` belgisi bilan
    saqlanadi.
    """
    journal = _journal_or_404(slug, db)
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(status_code=422, detail="O‘zgartirish uchun maydon yuborilmadi")
    try:
        applied, warnings = journal_edit.apply_edits(db, journal, changes)
    except journal_edit.ValidationError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return {
        "applied": sorted(applied),
        "warnings": warnings,
        **journal_edit.editable_payload(db, journal),
        "contacts": journal_edit.contacts_payload(journal),
    }


@admin.post("/profiles/collect")
def collect_journal_profile(input: ProfileCollectInput, db: Session = Depends(get_db)) -> dict[str, object]:
    journal = db.scalar(select(Journal).where(Journal.slug == input.journal_slug))
    if journal is None:
        raise HTTPException(status_code=404, detail="Jurnal topilmadi")
    try:
        profile = collect_profile(db, journal)
    except Exception as error:
        raise _admin_error(error) from error
    return {
        "journalSlug": journal.slug,
        "status": "collected",
        "completenessScore": profile.completeness_score,
        "fetchedAt": profile.fetched_at,
    }


app.include_router(admin)


# --- Foydalanuvchi autentifikatsiyasi -------------------------------------

auth = APIRouter(prefix="/api/auth", tags=["auth"])


class ProfileInput(BaseModel):
    display_name: str | None = Field(default=None, max_length=200)
    affiliation: str | None = Field(default=None, max_length=300)
    scholar_url: HttpUrl | None = None


def current_user(request: Request, db: Session = Depends(get_db)) -> User | None:
    return auth_service.user_for_token(db, request.cookies.get(auth_service.SESSION_COOKIE))


def require_user(user: User | None = Depends(current_user)) -> User:
    if user is None:
        raise HTTPException(status_code=401, detail="Avval tizimga kiring.")
    return user


@auth.get("/providers")
def auth_providers() -> dict[str, object]:
    """Sozlangan provayderlar. Sozlanmagani tugma sifatida ko‘rsatilmaydi."""
    return {
        "providers": auth_service.available_providers(),
        # Google Scholar OAuth provayderi emas — profil havolasi qo‘lda kiritiladi.
        "scholarLinkOnly": True,
    }


@auth.get("/{provider}/start")
def auth_start(provider: str, redirect_to: str | None = None, db: Session = Depends(get_db)):
    try:
        config = auth_service.provider_config(provider)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    if not config.configured:
        raise HTTPException(
            status_code=503,
            detail=f"{provider} sozlanmagan: CLIENT_ID va CLIENT_SECRET muhit o‘zgaruvchilari kerak.",
        )
    state = auth_service.create_state(db, provider, auth_service.safe_redirect(redirect_to))
    return RedirectResponse(auth_service.authorize_url(provider, state), status_code=307)


@auth.get("/{provider}/callback")
def auth_callback(
    provider: str,
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    db: Session = Depends(get_db),
):
    if error:
        # Foydalanuvchi ruxsat bermadi — bu xato emas, oddiy bekor qilish.
        return RedirectResponse(f"{auth_service.public_base_url()}/?auth=bekor", status_code=307)
    if not code or not state:
        raise HTTPException(status_code=400, detail="code yoki state yetishmayapti")
    try:
        redirect_to = auth_service.consume_state(db, provider, state)
    except LookupError as failure:
        raise HTTPException(status_code=400, detail="state yaroqsiz yoki muddati o‘tgan") from failure
    # Saqlangan qiymat allaqachon tekshirilgan; bu yerda yana bir bor —
    # eski qatorlar yoki bazaga qo‘lda kiritilgan qiymatlarga ishonmaymiz.
    redirect_to = auth_service.safe_redirect(redirect_to)
    try:
        identity = auth_service.exchange_code(provider, code)
    except Exception as failure:  # noqa: BLE001 - provayder xatosi foydalanuvchiga ko‘rinmasin
        logger.exception("OAuth almashuvi yiqildi: %s", provider)
        raise HTTPException(status_code=502, detail="Provayder bilan almashuv amalga oshmadi") from failure

    user = auth_service.upsert_user(db, provider, identity)
    token = auth_service.create_session(db, user, user_agent=request.headers.get("user-agent"))
    response = RedirectResponse(redirect_to or f"{auth_service.public_base_url()}/", status_code=307)
    response.set_cookie(
        auth_service.SESSION_COOKIE,
        token,
        max_age=int(auth_service.SESSION_TTL.total_seconds()),
        httponly=True,
        samesite="lax",
        secure=auth_service.public_base_url().startswith("https://"),
        path="/",
    )
    return response


@auth.get("/me")
def auth_me(user: User | None = Depends(current_user)) -> dict[str, object]:
    return {"user": auth_service.user_payload(user) if user else None}


@auth.patch("/me")
def auth_update_me(
    payload: ProfileInput,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    if payload.display_name is not None:
        name = payload.display_name.strip()
        if not name:
            raise HTTPException(status_code=422, detail="Ism bo‘sh bo‘lmasin")
        user.display_name = name
    if payload.affiliation is not None:
        user.affiliation = payload.affiliation.strip() or None
    if payload.scholar_url is not None:
        user.scholar_url = str(payload.scholar_url)
    db.commit()
    db.refresh(user)
    return {"user": auth_service.user_payload(user)}


class ClaimInput(BaseModel):
    article_id: int


@auth.get("/me/articles")
def auth_my_articles(
    user: User = Depends(require_user), db: Session = Depends(get_db)
) -> dict[str, object]:
    """Foydalanuvchi o‘ziniki deb tasdiqlagan maqolalar."""
    return {
        "articles": [article_payload(article) for article in authorship.claimed(db, user)],
        "stats": authorship.stats(db, user),
    }


@auth.get("/me/article-suggestions")
def auth_article_suggestions(
    user: User = Depends(require_user), db: Session = Depends(get_db)
) -> dict[str, object]:
    """Foydalanuvchi ismiga mos, hali tasdiqlanmagan maqolalar.

    Bu faqat taxmin — mualliflik nomlar bo‘yicha aniqlanadi. Shuning uchun
    hech narsa avtomatik qo‘shilmaydi va har bir nomzod qaysi muallif yozuvi
    tufayli topilganini ko‘rsatadi.
    """
    if len(authorship.name_words(user.display_name)) < authorship.MIN_NAME_WORDS:
        return {"suggestions": [], "needsFullName": True}
    suggestions = authorship.suggest(db, user)
    return {
        "suggestions": [
            {
                **article_payload(item.article),
                "confidence": item.confidence,
                "matchedAuthor": item.matched_author,
            }
            for item in suggestions
        ],
        "needsFullName": False,
    }


@auth.post("/me/articles")
def auth_claim_article(
    payload: ClaimInput, user: User = Depends(require_user), db: Session = Depends(get_db)
) -> dict[str, object]:
    try:
        authorship.claim(db, user, payload.article_id)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return {"status": "ok", "stats": authorship.stats(db, user)}


@auth.delete("/me/articles/{article_id}")
def auth_unclaim_article(
    article_id: int, user: User = Depends(require_user), db: Session = Depends(get_db)
) -> dict[str, object]:
    if not authorship.unclaim(db, user, article_id):
        raise HTTPException(status_code=404, detail="Bu maqola profilingizda yo‘q.")
    return {"status": "ok", "stats": authorship.stats(db, user)}


@auth.post("/logout")
def auth_logout(request: Request, db: Session = Depends(get_db)) -> JSONResponse:
    auth_service.revoke_session(db, request.cookies.get(auth_service.SESSION_COOKIE))
    response = JSONResponse({"status": "ok"})
    response.delete_cookie(auth_service.SESSION_COOKIE, path="/")
    return response


app.include_router(auth)

# Diqqat: SEO routerida `/{full_path:path}` catch-all bor. U shu yerda, hamma
# API marshrutlaridan keyin ulanishi shart.
from .seo_routes import router as seo_router  # noqa: E402

app.include_router(seo_router)
