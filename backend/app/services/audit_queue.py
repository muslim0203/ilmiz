from __future__ import annotations

import re
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from urllib.parse import urljoin, urlsplit, urlunsplit

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from ..db import SessionLocal
from ..models import AuditJob, HarvestSource, Journal
from .ingest import ACTIVE_SOURCE_STATUSES, audit_source

USER_AGENT = "IlmIz-OAI-Discovery/0.2"


# Bu saytlar bitta jurnalning repozitoriysi emas, ko‘p jurnalli agregatorlar.
# Ularning `/oai` manzili butun platformani beradi: bir marta `cyberleninka.ru/oai`
# jurnal endpointi deb qabul qilinib, 9 192 ta begona maqola bitta jurnalga
# yozilgan edi.
AGGREGATOR_HOSTS = frozenset({
    "cyberleninka.ru",
    "elibrary.ru",
    "doaj.org",
    "core.ac.uk",
    "base-search.net",
    "semanticscholar.org",
    "researchgate.net",
    "academia.edu",
    "scholar.google.com",
    "openalex.org",
    "zenodo.org",
    "figshare.com",
    "portal.issn.org",
    "scholarzest.com",
    # O‘zbekistondagi ko‘p jurnalli katalog/kutubxona platformalari. slib.uz
    # jurnal ro‘yxati sahifasidan 20 ta begona email, 3 ta siyosat matni va
    # navigatsiya matni bitta jurnalga "profil" bo‘lib yozilgan edi.
    "slib.uz",
    "uzjournals.edu.uz",
    "lib.uz",
    "natlib.uz",
})


def is_aggregator(url: str) -> bool:
    host = (urlsplit(url).hostname or "").casefold().removeprefix("www.")
    if not host:
        return False
    return any(host == item or host.endswith("." + item) for item in AGGREGATOR_HOSTS)


def endpoint_candidates(website: str) -> list[str]:
    parsed = urlsplit(website.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return []
    if is_aggregator(website):
        return []
    path = parsed.path.rstrip("/")
    candidates: list[str] = []
    if path.endswith("/oai"):
        candidates.append(urlunsplit((parsed.scheme, parsed.netloc, path, "", "")))
    if "/index.php/" in path:
        prefix, remainder = path.split("/index.php/", 1)
        journal_key = remainder.split("/", 1)[0]
        if journal_key:
            candidates.append(urlunsplit((parsed.scheme, parsed.netloc, f"{prefix}/index.php/{journal_key}/oai", "", "")))
    candidates.append(urlunsplit((parsed.scheme, parsed.netloc, "/oai", "", "")))
    candidates.append(urlunsplit((parsed.scheme, parsed.netloc, "/index.php/index/oai", "", "")))
    return list(dict.fromkeys(candidates))[:4]


def discovered_endpoint_candidates(website: str, *, timeout: int = 8) -> list[str]:
    candidates = endpoint_candidates(website)
    try:
        request = urllib.request.Request(website, headers={"User-Agent": USER_AGENT, "Accept": "text/html"})
        with urllib.request.urlopen(request, timeout=timeout) as response:
            html = response.read(1_500_000).decode(response.headers.get_content_charset() or "utf-8", errors="replace")
        hrefs = re.findall(r'''href=["']([^"']+)["']''', html, flags=re.IGNORECASE)
        for href in hrefs:
            absolute = urljoin(website, href)
            parsed = urlsplit(absolute)
            match = re.search(r"(/index\.php/([^/?#]+))", parsed.path, flags=re.IGNORECASE)
            if not match or match.group(2).casefold() in {"index", "user", "search", "about", "login"}:
                continue
            candidate = urlunsplit((parsed.scheme, parsed.netloc, f"{match.group(1)}/oai", "", ""))
            if not is_aggregator(candidate):
                candidates.append(candidate)
    except Exception:
        pass
    return [item for item in dict.fromkeys(candidates) if not is_aggregator(item)][:10]


def enqueue_audits(db: Session, *, limit: int | None = None) -> int:
    statement = (
        select(Journal)
        .where(Journal.oak_status == "active", Journal.website.is_not(None))
        .options(selectinload(Journal.harvest_sources))
        .order_by(Journal.id)
    )
    journals = list(db.scalars(statement).unique())
    created = 0
    for journal in journals:
        if any(source.status in ACTIVE_SOURCE_STATUSES for source in journal.harvest_sources):
            continue
        website = (journal.website or "").strip()
        if not endpoint_candidates(website):
            continue
        priority = 10 if "/index.php/" in website else 100
        existing = db.scalar(
            select(AuditJob).where(AuditJob.journal_id == journal.id, AuditJob.candidate_url == website)
        )
        if existing is not None:
            existing.priority = priority
            continue
        db.add(AuditJob(journal=journal, candidate_url=website, priority=priority))
        created += 1
        if limit is not None and created >= limit:
            break
    db.commit()
    return created


def _process_claimed_job(job_id: int) -> str:
    with SessionLocal() as worker_db:
        job = worker_db.scalar(select(AuditJob).where(AuditJob.id == job_id).options(selectinload(AuditJob.journal)))
        if job is None:
            return "failed"
        errors: list[str] = []
        for candidate in discovered_endpoint_candidates(job.candidate_url):
            try:
                audit_source(worker_db, job.journal, candidate, timeout=8, allow_insecure_ssl=True)
                job = worker_db.get(AuditJob, job_id)
                if job is None:
                    return "failed"
                job.status = "succeeded"
                job.discovered_base_url = candidate
                job.last_error = None
                break
            except Exception as error:
                errors.append(f"{candidate}: {error}")
        job = worker_db.get(AuditJob, job_id)
        if job is None:
            return "failed"
        if job.status != "succeeded":
            job.status = "failed"
            job.last_error = " | ".join(errors)[:4000]
        job.finished_at = datetime.now(timezone.utc)
        worker_db.commit()
        return job.status


def process_audit_jobs(db: Session, *, limit: int = 10, workers: int = 1) -> dict[str, int]:
    jobs = list(
        db.scalars(
            select(AuditJob)
            .where(AuditJob.status.in_(["queued", "retry"]))
            .options(selectinload(AuditJob.journal))
            .order_by(AuditJob.priority, AuditJob.created_at)
            .limit(limit)
        )
    )
    result = {"processed": len(jobs), "succeeded": 0, "failed": 0}
    for job in jobs:
        job.status = "running"
        job.started_at = datetime.now(timezone.utc)
        job.attempts += 1
    db.commit()
    with ThreadPoolExecutor(max_workers=min(max(1, workers), len(jobs) or 1)) as executor:
        futures = [executor.submit(_process_claimed_job, job.id) for job in jobs]
        for future in as_completed(futures):
            status = future.result()
            result[status if status in result else "failed"] += 1
    db.expire_all()
    return result


def requeue_failed_audits(db: Session, *, max_attempts: int = 2) -> int:
    jobs = list(db.scalars(select(AuditJob).where(AuditJob.status == "failed", AuditJob.attempts < max_attempts)))
    for job in jobs:
        job.status = "retry"
        job.last_error = None
        job.finished_at = None
    db.commit()
    return len(jobs)


def queue_stats(db: Session) -> dict[str, int]:
    rows = db.execute(select(AuditJob.status, func.count()).group_by(AuditJob.status)).all()
    return {str(status): count for status, count in rows}
