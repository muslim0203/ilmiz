"""Butun platformaga ulangan OAI manbasini alohida jurnal manbalariga ajratadi.

OJS ko‘p jurnalli o‘rnatmasida `/index.php/index/oai` manzili o‘sha saytdagi
HAMMA jurnalni qaytaradi. Bunday manba bitta jurnalga biriktirilsa, o‘nlab
boshqa jurnalning maqolalari o‘sha bitta jurnalga yozilib qoladi —
`tadqiqot.uz` dan 13 900 ta maqola bitta bolalar tibbiyoti jurnaliga tushgan.

Har bir jurnalning o‘z endpointi bor (`/index.php/<jurnal>/oai`), va uning
`repositoryName` maydoni bizdagi jurnalga moslashtirish uchun yetarli.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from harvester.oai_harvester import OAIError, identify

from ..models import Article, HarvestRun, HarvestSource, Journal, SourceRecord
from .tadqiq_import import name_tokens, normalize_name, raw_containment

logger = logging.getLogger(__name__)

# Bu chegaradan past moslikda jurnal biriktirilmaydi — noto‘g‘ri biriktirish
# hech narsa qilmaslikdan yomonroq. 0.5 da "ЖУРНАЛ ПРАВОВЫХ ИССЛЕДОВАНИЙ"
# butunlay boshqa jurnalga bog‘lanardi. 0.67 ham yetarli emas: "ИССЛЕДОВАНИЕ
# РЕНЕССАНСА ЦЕНТРАЛЬНОЙ АЗИИ" faqat geografik so‘zlar bo‘yicha "Экономика
# Центральной Азии" ga tushardi. Shuning uchun faqat deyarli aniq mosliklar.
MATCH_THRESHOLD = 0.9
PATH_RE = re.compile(r"/index\.php/([^/?#]+)/")


@dataclass
class PathCandidate:
    path: str
    articles: int
    oai_url: str = ""
    repository_name: str = ""
    journal_id: int | None = None
    journal_name: str = ""
    score: float = 0.0
    note: str = ""


def platform_root(base_url: str) -> str:
    parts = urlsplit(base_url)
    return urlunsplit((parts.scheme, parts.netloc, "", "", ""))


def article_paths(db: Session, source_id: int) -> dict[str, int]:
    """Manbadan kelgan maqolalar qaysi jurnal yo‘llarida joylashganini sanaydi."""
    counts: dict[str, int] = {}
    rows = db.execute(
        select(Article.landing_url)
        .join(SourceRecord, SourceRecord.article_id == Article.id)
        .where(SourceRecord.source_id == source_id, Article.landing_url.is_not(None))
    )
    for (url,) in rows:
        match = PATH_RE.search(url or "")
        if not match:
            continue
        path = match.group(1)
        if path and path != "index":
            counts[path] = counts.get(path, 0) + 1
    return counts


def _match_journal(repository: str, journals: list[tuple[int, str]]) -> tuple[int | None, str, float]:
    repository_tokens = name_tokens(repository)
    normalized = normalize_name(repository)
    best_id, best_name, best_score = None, "", 0.0
    for journal_id, name in journals:
        score = raw_containment(repository_tokens, name_tokens(name))
        if normalized and normalize_name(name) == normalized:
            score = 1.0
        if score > best_score:
            best_id, best_name, best_score = journal_id, name, score
    return best_id, best_name, best_score


def inspect_platform(db: Session, source_id: int, *, timeout: int = 20) -> list[PathCandidate]:
    """Har bir jurnal yo‘li uchun endpointni tekshiradi va jurnalga moslashtiradi."""
    source = db.get(HarvestSource, source_id)
    if source is None:
        raise ValueError(f"manba topilmadi: {source_id}")
    root = platform_root(source.base_url)
    journals = [(row.id, row.name) for row in db.scalars(select(Journal))]

    candidates: list[PathCandidate] = []
    for path, count in sorted(article_paths(db, source_id).items(), key=lambda item: -item[1]):
        candidate = PathCandidate(path=path, articles=count, oai_url=f"{root}/index.php/{path}/oai")
        try:
            identity = identify(candidate.oai_url, timeout=timeout, verify_ssl=not source.insecure_ssl)
        except (OAIError, Exception) as error:  # noqa: BLE001 - sabab hisobotga chiqsin
            candidate.note = f"endpoint javob bermadi: {type(error).__name__}"
            candidates.append(candidate)
            continue
        candidate.repository_name = str(identity.get("repository_name") or "")
        journal_id, journal_name, score = _match_journal(candidate.repository_name, journals)
        candidate.score = score
        if score >= MATCH_THRESHOLD:
            candidate.journal_id, candidate.journal_name = journal_id, journal_name
        else:
            candidate.note = f"bizdagi jurnalga mos kelmadi (eng yaqin: {journal_name[:40]!r} {score:.2f})"
        candidates.append(candidate)
    return candidates


def purge_source(db: Session, source_id: int) -> int:
    """Manbani va faqat undan kelgan maqolalarni o‘chiradi."""
    article_ids = set(
        db.scalars(
            select(SourceRecord.article_id).where(
                SourceRecord.source_id == source_id, SourceRecord.article_id.is_not(None)
            )
        )
    )
    shared = set(
        db.scalars(
            select(SourceRecord.article_id).where(
                SourceRecord.article_id.in_(article_ids), SourceRecord.source_id != source_id
            )
        )
    )
    doomed = list(article_ids - shared)
    db.execute(delete(SourceRecord).where(SourceRecord.source_id == source_id))
    for start in range(0, len(doomed), 500):
        db.execute(delete(Article).where(Article.id.in_(doomed[start : start + 500])))
    db.execute(delete(HarvestRun).where(HarvestRun.source_id == source_id))
    source = db.get(HarvestSource, source_id)
    if source is not None:
        db.delete(source)
    return len(doomed)


def split_platform_source(db: Session, source_id: int, *, dry_run: bool = True, timeout: int = 20) -> dict[str, object]:
    """Platforma manbasini ajratadi: mos jurnallarga endpoint ochadi, eskisini o‘chiradi."""
    candidates = inspect_platform(db, source_id, timeout=timeout)
    matched = [item for item in candidates if item.journal_id is not None]
    result: dict[str, object] = {
        "manba": source_id,
        "yo_llar": len(candidates),
        "moslashgan": len(matched),
        "moslashmagan": len(candidates) - len(matched),
        "o_chiriladigan_maqola": 0,
        "yaratilgan_manba": 0,
        "rejim": "dry-run" if dry_run else "apply",
        "tafsilot": [
            {
                "yol": item.path,
                "maqola": item.articles,
                "repo": item.repository_name[:60],
                "jurnal": item.journal_name[:60],
                "ball": round(item.score, 2),
                "izoh": item.note,
            }
            for item in candidates
        ],
    }
    if dry_run:
        return result

    # Avval eski manbani tozalaymiz: maqola boshqa jurnalga bog‘langan holda
    # qolsa, qayta harvest uni to‘g‘ri jurnalga ko‘chira olmaydi (dedupe DOI
    # bo‘yicha eski yozuvni topib, journal_id ni o‘zgartirmaydi).
    result["o_chiriladigan_maqola"] = purge_source(db, source_id)

    created = 0
    for item in matched:
        exists = db.scalar(
            select(HarvestSource).where(HarvestSource.base_url == item.oai_url)
        )
        if exists is not None:
            continue
        db.add(
            HarvestSource(
                journal_id=item.journal_id,
                base_url=item.oai_url,
                repository_name=item.repository_name,
                status="pending",
            )
        )
        created += 1
    result["yaratilgan_manba"] = created
    db.commit()
    logger.info("Platforma manbasi ajratildi: %s", result)
    return result
