#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import select

from backend.app.db import SessionLocal, init_db
from backend.app.models import HarvestSource, Journal
from backend.app.seed import seed_database
from backend.app.services.audit_queue import enqueue_audits, process_audit_jobs, requeue_failed_audits
from backend.app.services.ingest import (
    audit_source,
    drop_raw_metadata_column,
    ingest_all_sources,
    ingest_source,
    rebuild_search_index,
    reparse_bibliographic,
)
from backend.app.services import indexnow
from backend.app.services.oak_registry import import_registry
from backend.app.services.profile_collector import collect_profile
from backend.app.services.auth import grant_admin
from backend.app.services.merge_duplicates import merge_duplicates
from backend.app.services.platform_split import split_platform_source
from backend.app.services.tadqiq_import import import_tadqiq
from backend.app.services.profile_queue import enqueue_profiles, process_profile_jobs, requeue_failed_profiles, requeue_incomplete_profiles


def configure_logging() -> Path:
    """Xatolar konsolga ham, `logs/ilmiz.log` ga ham yozilsin.

    Ilgari harvest xatolari hech qayerda saqlanmagani uchun yiqilgan
    manbaning sababini aniqlab bo‘lmasdi.
    """
    log_dir = PROJECT_ROOT / "logs"
    log_dir.mkdir(exist_ok=True)
    log_path = log_dir / "ilmiz.log"
    handlers: list[logging.Handler] = [logging.FileHandler(log_path, encoding="utf-8")]
    stream = logging.StreamHandler()
    stream.setLevel(logging.WARNING)
    handlers.append(stream)
    logging.basicConfig(
        level=getattr(logging, os.getenv("ILMIZ_LOG_LEVEL", "INFO").upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        handlers=handlers,
        force=True,
    )
    return log_path


def journal_by_slug(db, slug: str) -> Journal:
    journal = db.scalar(select(Journal).where(Journal.slug == slug))
    if journal is None:
        raise SystemExit(f"Jurnal topilmadi: {slug}")
    return journal


def main() -> int:
    parser = argparse.ArgumentParser(description="IlmIz backend boshqaruv CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("init")
    # Sxemani qo'lda yangilash. `init_db()` buni ishga tushishda o'zi
    # bajaradi; bu buyruq deploydan oldin alohida tekshirish uchun.
    subparsers.add_parser("migrate")
    import_oak = subparsers.add_parser("import-oak")
    import_oak.add_argument("--url", default="https://journal-statistics-oak.vercel.app/")
    queue_audits = subparsers.add_parser("queue-audits")
    queue_audits.add_argument("--limit", type=int)
    process_audits = subparsers.add_parser("process-audits")
    process_audits.add_argument("--limit", type=int, default=10)
    process_audits.add_argument("--workers", type=int, default=4)
    drain_audits = subparsers.add_parser("drain-audits")
    drain_audits.add_argument("--batch-size", type=int, default=24)
    drain_audits.add_argument("--workers", type=int, default=4)
    retry_audits = subparsers.add_parser("retry-audits")
    retry_audits.add_argument("--max-attempts", type=int, default=2)
    profile = subparsers.add_parser("profile")
    profile.add_argument("journal_slug")
    queue_profiles = subparsers.add_parser("queue-profiles")
    queue_profiles.add_argument("--limit", type=int)
    queue_profiles.add_argument("--refresh", action="store_true")
    process_profiles = subparsers.add_parser("process-profiles")
    process_profiles.add_argument("--limit", type=int, default=3)
    process_profiles.add_argument("--workers", type=int, default=3)
    drain_profiles = subparsers.add_parser("drain-profiles")
    drain_profiles.add_argument("--batch-size", type=int, default=25)
    drain_profiles.add_argument("--workers", type=int, default=3)
    drain_profiles.add_argument("--max-batches", type=int)
    retry_profiles = subparsers.add_parser("retry-profiles")
    retry_profiles.add_argument("--max-attempts", type=int, default=2)
    refresh_incomplete = subparsers.add_parser("refresh-incomplete")
    refresh_incomplete.add_argument("--score-below", type=float, default=70)
    refresh_incomplete.add_argument("--max-attempts", type=int, default=3)
    audit = subparsers.add_parser("audit")
    audit.add_argument("journal_slug")
    audit.add_argument("base_url")
    harvest = subparsers.add_parser("harvest")
    harvest.add_argument("journal_slug")
    harvest.add_argument("base_url")
    harvest.add_argument("--from-date")
    harvest.add_argument("--page-limit", type=int)
    harvest_all = subparsers.add_parser("harvest-all")
    harvest_all.add_argument("--from-date")
    harvest_all.add_argument("--page-limit", type=int)
    harvest_all.add_argument("--workers", type=int, default=3)
    harvest_all.add_argument("--source-id", action="append", type=int, dest="source_ids")
    tadqiq = subparsers.add_parser("import-tadqiq")
    tadqiq.add_argument("--apply", action="store_true", help="Standart holatda faqat quruq yurish")
    tadqiq.add_argument("--cache-dir", help="Yuklangan sahifalar keshi (saytga qayta murojaat qilmaslik uchun)")
    tadqiq.add_argument("--limit", type=int, help="Faqat birinchi N jurnal")
    tadqiq.add_argument("--fix-dead-sites", action="store_true",
                        help="OAI manbasi yiqilgan jurnallarda eskirgan sayt manzilini almashtirish")
    admin_cmd = subparsers.add_parser("grant-admin")
    admin_cmd.add_argument("identifier", help="ORCID iD yoki e-pochta")
    admin_cmd.add_argument("--revoke", action="store_true", help="Huquqni olib tashlash")
    subparsers.add_parser("rebuild-search-index")
    merge_dups = subparsers.add_parser("merge-duplicates")
    merge_dups.add_argument("--apply", action="store_true", help="Standart holatda faqat quruq yurish")
    merge_dups.add_argument("--limit", type=int, help="Faqat birinchi N guruh")
    split_platform = subparsers.add_parser("split-platform-source")
    split_platform.add_argument("source_id", type=int)
    split_platform.add_argument("--apply", action="store_true", help="Standart holatda faqat quruq yurish")
    drop_raw = subparsers.add_parser("drop-raw-metadata")
    drop_raw.add_argument("--no-vacuum", action="store_true", help="Ustunni o‘chiradi, lekin faylni siqmaydi")
    reparse = subparsers.add_parser("reparse-bibliographic")
    reparse.add_argument("--apply", action="store_true", help="Standart holatda faqat quruq yurish")
    index_now = subparsers.add_parser(
        "indexnow", help="O‘zgargan URL'larni Yandex/Bing'ga bildirish (IndexNow)"
    )
    index_now.add_argument("--days", type=int, default=7, help="So‘nggi necha kunlik o‘zgarishlar")
    index_now.add_argument("--limit", type=int, default=indexnow.BATCH)
    index_now.add_argument("--apply", action="store_true", help="Standart holatda faqat quruq yurish")
    args = parser.parse_args()

    log_path = configure_logging()
    logging.getLogger(__name__).info("Buyruq boshlandi: %s", args.command)

    init_db()
    with SessionLocal() as db:
        seed_database(db)
        if args.command == "init":
            print(json.dumps({"status": "ok", "message": "Database initialized"}, ensure_ascii=False))
            return 0
        if args.command == "migrate":
            # `init_db()` yuqorida allaqachon `alembic upgrade head` ni
            # bajardi; bu yerda faqat natijadagi versiyani ko'rsatamiz.
            from alembic.runtime.migration import MigrationContext

            from backend.app.db import engine

            with engine.connect() as connection:
                revision = MigrationContext.configure(connection).get_current_revision()
            print(json.dumps({"status": "ok", "revision": revision}, ensure_ascii=False))
            return 0
        if args.command == "import-oak":
            run = import_registry(db, url=args.url)
            print(json.dumps({
                "run_id": run.id,
                "status": run.status,
                "records_seen": run.records_seen,
                "registry_created": run.registry_created,
                "journals_created": run.journals_created,
                "journals_updated": run.journals_updated,
            }, ensure_ascii=False, indent=2))
            return 0
        if args.command == "queue-audits":
            count = enqueue_audits(db, limit=args.limit)
            print(json.dumps({"queued": count}, ensure_ascii=False, indent=2))
            return 0
        if args.command == "process-audits":
            result = process_audit_jobs(db, limit=args.limit, workers=args.workers)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0
        if args.command == "drain-audits":
            totals = {"processed": 0, "succeeded": 0, "failed": 0}
            batches = 0
            while True:
                result = process_audit_jobs(db, limit=args.batch_size, workers=args.workers)
                if result["processed"] == 0:
                    break
                batches += 1
                for key in totals:
                    totals[key] += result[key]
                print(json.dumps({"batch": batches, **result}, ensure_ascii=False), flush=True)
            print(json.dumps({"status": "drained", "batches": batches, **totals}, ensure_ascii=False, indent=2))
            return 0
        if args.command == "retry-audits":
            count = requeue_failed_audits(db, max_attempts=args.max_attempts)
            print(json.dumps({"requeued": count, "max_attempts": args.max_attempts}, ensure_ascii=False, indent=2))
            return 0
        if args.command == "harvest-all":
            result = ingest_all_sources(db, from_date=args.from_date, page_limit=args.page_limit, workers=args.workers, selected_source_ids=args.source_ids)
            result["logFile"] = str(log_path)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0
        if args.command == "import-tadqiq":
            result = import_tadqiq(
                db,
                dry_run=not args.apply,
                cache_dir=Path(args.cache_dir) if args.cache_dir else None,
                limit=args.limit,
                fix_dead_sites=args.fix_dead_sites,
            )
            result["logFile"] = str(log_path)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0
        if args.command == "grant-admin":
            user = grant_admin(db, args.identifier, revoke=args.revoke)
            if user is None:
                print(json.dumps({"xato": f"foydalanuvchi topilmadi: {args.identifier}"}, ensure_ascii=False))
                return 1
            print(json.dumps({
                "id": user.id, "ism": user.display_name, "orcid": user.orcid,
                "email": user.email, "is_admin": user.is_admin,
            }, ensure_ascii=False, indent=2))
            return 0
        if args.command == "rebuild-search-index":
            print(json.dumps(rebuild_search_index(db), ensure_ascii=False, indent=2))
            return 0
        if args.command == "merge-duplicates":
            result = merge_duplicates(db, dry_run=not args.apply, limit=args.limit)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0
        if args.command == "split-platform-source":
            result = split_platform_source(db, args.source_id, dry_run=not args.apply)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0
        if args.command == "drop-raw-metadata":
            db.close()
            result = drop_raw_metadata_column(vacuum=not args.no_vacuum)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0
        if args.command == "indexnow":
            urls = indexnow.changed_urls(db, days=args.days, limit=args.limit)
            if not args.apply:
                print(json.dumps({
                    "rejim": "dry-run",
                    "topildi": len(urls),
                    "namuna": urls[:5],
                    "izoh": "Yuborish uchun --apply qo‘shing",
                }, ensure_ascii=False, indent=2))
                return 0
            print(json.dumps(indexnow.submit(urls), ensure_ascii=False, indent=2))
            return 0
        if args.command == "reparse-bibliographic":
            result = reparse_bibliographic(db, dry_run=not args.apply)
            result["rejim"] = "apply" if args.apply else "dry-run"
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0
        if args.command == "profile":
            journal = journal_by_slug(db, args.journal_slug)
            result = collect_profile(db, journal)
            print(json.dumps({
                "journal": journal.name,
                "status": "collected",
                "completeness_score": result.completeness_score,
                "fetched_at": result.fetched_at,
            }, ensure_ascii=False, indent=2, default=str))
            return 0
        if args.command == "queue-profiles":
            count = enqueue_profiles(db, limit=args.limit, refresh=args.refresh)
            print(json.dumps({"queued": count}, ensure_ascii=False, indent=2))
            return 0
        if args.command == "process-profiles":
            result = process_profile_jobs(db, limit=args.limit, workers=args.workers)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0
        if args.command == "drain-profiles":
            totals = {"processed": 0, "succeeded": 0, "partial": 0, "failed": 0}
            batch = 0
            while args.max_batches is None or batch < args.max_batches:
                result = process_profile_jobs(db, limit=args.batch_size, workers=args.workers)
                if result["processed"] == 0:
                    break
                batch += 1
                for key in totals:
                    totals[key] += result[key]
                print(json.dumps({"batch": batch, **result}, ensure_ascii=False), flush=True)
            print(json.dumps({"status": "drained", "batches": batch, **totals}, ensure_ascii=False, indent=2))
            return 0
        if args.command == "retry-profiles":
            count = requeue_failed_profiles(db, max_attempts=args.max_attempts)
            print(json.dumps({"requeued": count, "max_attempts": args.max_attempts}, ensure_ascii=False, indent=2))
            return 0
        if args.command == "refresh-incomplete":
            count = requeue_incomplete_profiles(db, score_below=args.score_below, max_attempts=args.max_attempts)
            print(json.dumps({"requeued": count, "score_below": args.score_below, "max_attempts": args.max_attempts}, ensure_ascii=False, indent=2))
            return 0
        journal = journal_by_slug(db, args.journal_slug)
        source = db.scalar(
            select(HarvestSource).where(
                HarvestSource.journal_id == journal.id,
                HarvestSource.base_url == args.base_url,
            )
        )
        if source is None or source.status != "healthy":
            source = audit_source(db, journal, args.base_url)
        if args.command == "audit":
            print(json.dumps({
                "id": source.id,
                "journal": journal.name,
                "repository": source.repository_name,
                "status": source.status,
                "formats": source.available_formats,
            }, ensure_ascii=False, indent=2, default=str))
            return 0
        run = ingest_source(db, source, from_date=args.from_date, page_limit=args.page_limit)
        print(json.dumps({
            "run_id": run.id,
            "status": run.status,
            "seen": run.records_seen,
            "created": run.records_created,
            "updated": run.records_updated,
            "deleted": run.records_deleted,
        }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
