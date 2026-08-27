"""Bir jurnalning kirill va lotin yozuvidagi nusxalarini birlashtiradi.

OAK reestrida bir jurnal ikki xil yozuvda ro‘yxatga olingan holatlar bor:
`Meros` / `Мерос`, `Farmatsevtika jurnali` uch marta. Bu jurnal sonini
shishiradi, maqolalarni ikkiga bo‘ladi va bir OAI endpointini bir nechta
jurnalga biriktirib qo‘yadi.

Har bir bog‘liq jadvalning unique cheklovi boshqacha, shuning uchun ko‘chirish
jadval bo‘yicha alohida qilinadi: to‘qnashadigan qatorlar ko‘chirilmaydi,
o‘chiriladi.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import (
    Article,
    AuditJob,
    EditorialMember,
    HarvestRun,
    HarvestSource,
    Journal,
    JournalContact,
    JournalIndexingClaim,
    JournalLink,
    JournalPolicy,
    JournalProfile,
    JournalProfileField,
    JournalSection,
    OakRegistryEntry,
    ProfileJob,
    SourceRecord,
)
from .tadqiq_import import normalize_name

logger = logging.getLogger(__name__)

# (model, cheklovga kiruvchi ustunlar) — journal_id dan tashqari.
SCOPED_TABLES: tuple[tuple[type, tuple[str, ...]], ...] = (
    (JournalContact, ("kind", "value")),
    (EditorialMember, ("name", "role")),
    (JournalPolicy, ("policy_type",)),
    (JournalSection, ("name",)),
    (JournalIndexingClaim, ("provider",)),
    (JournalLink, ("kind", "url")),
    (JournalProfileField, ("field_name",)),
    (AuditJob, ("candidate_url",)),
)
# Jurnalga bittadan bo‘ladigan jadvallar.
SINGLETON_TABLES: tuple[type, ...] = (JournalProfile, ProfileJob)


@dataclass
class MergePlan:
    canonical_id: int
    canonical_name: str
    duplicate_ids: list[int] = field(default_factory=list)
    duplicate_names: list[str] = field(default_factory=list)
    articles: int = 0


def find_duplicate_groups(db: Session) -> list[MergePlan]:
    """Normalizatsiyalangan nomi bir xil jurnallarni guruhlaydi.

    Kanonik jurnal — maqolasi eng ko‘pi; teng bo‘lsa profili bori, keyin
    eng eski ID. Shu bilan ko‘chiriladigan ma’lumot hajmi eng kichik bo‘ladi.
    """
    article_counts = dict(
        db.execute(
            select(Article.journal_id, func.count())
            .where(Article.is_deleted.is_(False))
            .group_by(Article.journal_id)
        ).all()
    )
    with_profile = set(db.scalars(select(JournalProfile.journal_id)))

    groups: dict[str, list[Journal]] = defaultdict(list)
    for journal in db.scalars(select(Journal)):
        groups[normalize_name(journal.name)].append(journal)

    plans: list[MergePlan] = []
    for members in groups.values():
        if len(members) < 2:
            continue
        members.sort(
            key=lambda item: (
                -article_counts.get(item.id, 0),
                0 if item.id in with_profile else 1,
                item.id,
            )
        )
        canonical, *duplicates = members
        plans.append(
            MergePlan(
                canonical_id=canonical.id,
                canonical_name=canonical.name,
                duplicate_ids=[item.id for item in duplicates],
                duplicate_names=[item.name for item in duplicates],
                articles=sum(article_counts.get(item.id, 0) for item in members),
            )
        )
    return sorted(plans, key=lambda plan: -plan.articles)


def _merge_sources(db: Session, canonical_id: int, duplicate_id: int, stats: dict[str, int]) -> None:
    """OAI manbalarini ko‘chiradi; bir xil URL bo‘lsa yozuvlarini birlashtiradi."""
    existing = {
        (source.base_url, source.metadata_prefix): source
        for source in db.scalars(select(HarvestSource).where(HarvestSource.journal_id == canonical_id))
    }
    for source in list(db.scalars(select(HarvestSource).where(HarvestSource.journal_id == duplicate_id))):
        twin = existing.get((source.base_url, source.metadata_prefix))
        if twin is None:
            source.journal_id = canonical_id
            existing[(source.base_url, source.metadata_prefix)] = source
            stats["manba_kochirildi"] += 1
            continue
        # Bir xil endpoint ikkalasida ham bor: yozuvlarni kanonikka o‘tkazamiz.
        seen = {record.oai_identifier for record in twin.records}
        for record in list(source.records):
            if record.oai_identifier in seen:
                db.delete(record)
            else:
                record.source_id = twin.id
                seen.add(record.oai_identifier)
        for run in list(db.scalars(select(HarvestRun).where(HarvestRun.source_id == source.id))):
            run.source_id = twin.id
        db.delete(source)
        stats["manba_birlashtirildi"] += 1


def _merge_articles(db: Session, canonical_id: int, duplicate_id: int, stats: dict[str, int]) -> None:
    """Maqolalarni ko‘chiradi; kanonikda ayni maqola bo‘lsa yozuvlarini bog‘laydi."""
    canonical_articles = list(db.scalars(select(Article).where(Article.journal_id == canonical_id)))
    by_doi = {item.doi: item for item in canonical_articles if item.doi}
    by_title = {(item.normalized_title, item.publication_year): item for item in canonical_articles}

    for article in list(db.scalars(select(Article).where(Article.journal_id == duplicate_id))):
        twin = None
        if article.doi and article.doi in by_doi:
            twin = by_doi[article.doi]
        else:
            twin = by_title.get((article.normalized_title, article.publication_year))
        if twin is None:
            article.journal_id = canonical_id
            by_title[(article.normalized_title, article.publication_year)] = article
            if article.doi:
                by_doi[article.doi] = article
            stats["maqola_kochirildi"] += 1
            continue
        for record in list(db.scalars(select(SourceRecord).where(SourceRecord.article_id == article.id))):
            record.article_id = twin.id
        db.delete(article)
        stats["maqola_birlashtirildi"] += 1


def _merge_scoped(db: Session, canonical_id: int, duplicate_id: int, stats: dict[str, int]) -> None:
    for model, columns in SCOPED_TABLES:
        taken = {
            tuple(getattr(row, column) for column in columns)
            for row in db.scalars(select(model).where(model.journal_id == canonical_id))
        }
        for row in list(db.scalars(select(model).where(model.journal_id == duplicate_id))):
            key = tuple(getattr(row, column) for column in columns)
            if key in taken:
                db.delete(row)
                stats["takroriy_ochirildi"] += 1
            else:
                row.journal_id = canonical_id
                taken.add(key)
                stats["yozuv_kochirildi"] += 1

    for model in SINGLETON_TABLES:
        canonical_row = db.scalar(select(model).where(model.journal_id == canonical_id))
        for row in list(db.scalars(select(model).where(model.journal_id == duplicate_id))):
            if canonical_row is None:
                row.journal_id = canonical_id
                canonical_row = row
                stats["yozuv_kochirildi"] += 1
            else:
                db.delete(row)
                stats["takroriy_ochirildi"] += 1

    for row in list(db.scalars(select(OakRegistryEntry).where(OakRegistryEntry.journal_id == duplicate_id))):
        row.journal_id = canonical_id
        stats["reestr_kochirildi"] += 1


def merge_group(db: Session, plan: MergePlan) -> dict[str, int]:
    stats = {
        "manba_kochirildi": 0, "manba_birlashtirildi": 0,
        "maqola_kochirildi": 0, "maqola_birlashtirildi": 0,
        "yozuv_kochirildi": 0, "takroriy_ochirildi": 0,
        "reestr_kochirildi": 0, "jurnal_ochirildi": 0,
    }
    for duplicate_id in plan.duplicate_ids:
        _merge_sources(db, plan.canonical_id, duplicate_id, stats)
        _merge_articles(db, plan.canonical_id, duplicate_id, stats)
        _merge_scoped(db, plan.canonical_id, duplicate_id, stats)
        db.flush()
        duplicate = db.get(Journal, duplicate_id)
        if duplicate is not None:
            db.delete(duplicate)
            stats["jurnal_ochirildi"] += 1
    return stats


def merge_duplicates(db: Session, *, dry_run: bool = True, limit: int | None = None) -> dict[str, object]:
    plans = find_duplicate_groups(db)
    if limit:
        plans = plans[:limit]
    totals: dict[str, int] = {}
    detail: list[dict[str, object]] = []
    for plan in plans:
        detail.append(
            {
                "kanonik": plan.canonical_name[:60],
                "nusxalar": [name[:60] for name in plan.duplicate_names],
                "maqola": plan.articles,
            }
        )
        if dry_run:
            continue
        for key, value in merge_group(db, plan).items():
            totals[key] = totals.get(key, 0) + value

    if dry_run:
        db.rollback()
    else:
        db.commit()
        logger.info("Dublikat jurnallar birlashtirildi: %s", totals)
    return {
        "guruhlar": len(plans),
        "jurnallar": sum(1 + len(plan.duplicate_ids) for plan in plans),
        "rejim": "dry-run" if dry_run else "apply",
        "natija": totals,
        "tafsilot": detail,
    }
