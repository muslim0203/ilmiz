from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from ..db import SessionLocal
from ..models import HarvestSource, Journal, JournalProfile, ProfileJob
from .profile_collector import collect_profile


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def enqueue_profiles(db: Session, *, limit: int | None = None, refresh: bool = False) -> int:
    statement = (
        select(Journal)
        .where(Journal.oak_status == "active", Journal.website.is_not(None))
        .options(selectinload(Journal.profile), selectinload(Journal.harvest_sources))
        .order_by(Journal.id)
    )
    journals = list(db.scalars(statement).unique())
    created = 0
    for journal in journals:
        website = (journal.website or "").strip()
        if not website.startswith(("http://", "https://")):
            continue
        existing = db.scalar(select(ProfileJob).where(ProfileJob.journal_id == journal.id))
        if existing is not None:
            if refresh and existing.status in {"succeeded", "partial", "failed"}:
                existing.status = "queued"
                existing.last_error = None
                existing.finished_at = None
            continue
        if journal.profile is not None and not refresh:
            continue
        is_ojs = "/index.php/" in website or any(source.status == "healthy" for source in journal.harvest_sources)
        priority = 10 if is_ojs else 100
        db.add(ProfileJob(journal=journal, source_url=website, priority=priority))
        created += 1
        if limit is not None and created >= limit:
            break
    db.commit()
    return created


def _process_claimed_job(job_id: int) -> str:
    with SessionLocal() as worker_db:
        job = worker_db.scalar(
            select(ProfileJob).where(ProfileJob.id == job_id).options(selectinload(ProfileJob.journal))
        )
        if job is None:
            return "failed"
        try:
            profile = collect_profile(worker_db, job.journal)
            job.completeness_score = profile.completeness_score
            job.status = "succeeded" if profile.completeness_score >= 70 else "partial"
            job.last_error = None
        except Exception as error:
            worker_db.rollback()
            job = worker_db.get(ProfileJob, job_id)
            if job is None:
                return "failed"
            job.status = "failed"
            job.last_error = str(error)[:4000]
        job.finished_at = utcnow()
        worker_db.commit()
        return job.status


def process_profile_jobs(db: Session, *, limit: int = 3, workers: int = 1) -> dict[str, int]:
    jobs = list(
        db.scalars(
            select(ProfileJob)
            .where(ProfileJob.status.in_(["queued", "retry"]))
            .order_by(ProfileJob.priority, ProfileJob.created_at)
            .limit(limit)
        )
    )
    result = {"processed": len(jobs), "succeeded": 0, "partial": 0, "failed": 0}
    for job in jobs:
        job.status = "running"
        job.started_at = utcnow()
        job.attempts += 1
    db.commit()
    job_ids = [job.id for job in jobs]
    with ThreadPoolExecutor(max_workers=min(max(1, workers), len(job_ids) or 1)) as executor:
        futures = [executor.submit(_process_claimed_job, job_id) for job_id in job_ids]
        for future in as_completed(futures):
            status = future.result()
            result[status if status in result else "failed"] += 1
    db.expire_all()
    return result


def profile_queue_stats(db: Session) -> dict[str, int]:
    rows = db.execute(select(ProfileJob.status, func.count()).group_by(ProfileJob.status)).all()
    return {str(status): count for status, count in rows}


def requeue_failed_profiles(db: Session, *, max_attempts: int = 2) -> int:
    jobs = list(
        db.scalars(
            select(ProfileJob).where(
                ProfileJob.status == "failed",
                ProfileJob.attempts < max_attempts,
            )
        )
    )
    for job in jobs:
        job.status = "retry"
        job.last_error = None
        job.finished_at = None
    db.commit()
    return len(jobs)


def requeue_incomplete_profiles(db: Session, *, score_below: float = 70, max_attempts: int = 3) -> int:
    jobs = list(
        db.scalars(
            select(ProfileJob).where(
                ProfileJob.status.in_(["partial", "failed"]),
                ProfileJob.attempts < max_attempts,
            )
        )
    )
    selected = [job for job in jobs if job.completeness_score is None or job.completeness_score < score_below]
    for job in selected:
        job.status = "retry"
        job.last_error = None
        job.finished_at = None
    db.commit()
    return len(selected)


def profile_stats(db: Session) -> dict[str, float | int]:
    count = db.scalar(select(func.count()).select_from(JournalProfile)) or 0
    average = db.scalar(select(func.avg(JournalProfile.completeness_score))) or 0
    return {"collected": count, "averageCompleteness": round(float(average), 1)}
