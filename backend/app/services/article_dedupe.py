"""Takror maqolalarni birlashtirish (`manage.py dedupe-articles`).

Takror — bir jurnal, bir xil normallashtirilgan sarlavha va bir xil yil.
Asosan bir maqola OAI-PMH va OpenAlex orqali ikki marta kirgan (OpenAlex
importi sarlavhani boshqacha normallashtirardi). Har guruhdan bitta kanonik
nusxa qoladi:

    DOI bor > annotatsiya uzunroq > kalit so'z ko'proq > ID kichikroq

Qolganlari o'chirilmaydi: `is_deleted` + `duplicate_of` — sahifasi kanonikka
301 bilan o'tadi, ya'ni Google'dagi eski URL yo'qolmaydi. Manba yozuvlari va
muallif bog'lanishlari kanonikka ko'chiriladi, shunda keyingi harvest
takrorni qayta tiriltirmaydi.

Ehtiyot — bir xil sarlavha alohida maqolalarda ham uchraydi:
- sarlavhasi juda qisqa ("Kirish", "Front matter") guruhlar tegilmaydi;
- annotatsiyalari har xil bo'lsa — bular boshqa maqolalar (prod'da 191 guruh,
  betlari ham har xil edi), tegilmaydi;
- DOI'lari har xil bo'lsa, faqat annotatsiya bir xil bo'lganda birlashtiriladi:
  bitta maqola jurnal va Zenodo'da alohida DOI olgan (321 guruh shunday edi).
Tegilmaganlari hisobotda.
"""
from __future__ import annotations

import csv
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from ..models import Article, SourceRecord, UserArticle

MIN_TITLE_LENGTH = 20
# Annotatsiya boshini solishtirish yetarli: takrorda matn aynan bir xil.
ABSTRACT_PREFIX = 300


def _abstract_key(value: str | None) -> str:
    return re.sub(r"\W+", " ", (value or "").casefold()).strip()[:ABSTRACT_PREFIX]


def _rank(row) -> tuple:
    return (bool(row.doi), row.abstract_length or 0, row.keywords or 0, -row.id)


def plan_duplicates(db: Session) -> tuple[list[tuple[int, list[int], str]], list[tuple[list[int], str, str]]]:
    """`(kanonik, [takrorlar], sarlavha)` va o'tkazib yuborilgan guruhlar."""
    rows = db.execute(
        select(
            Article.id, Article.journal_id, Article.normalized_title, Article.publication_year, Article.doi,
            func.length(func.coalesce(Article.abstract, "")).label("abstract_length"),
            func.json_array_length(Article.keywords).label("keywords"),
        ).where(Article.is_deleted.is_(False))
    ).all()
    groups: dict[tuple, list] = defaultdict(list)
    for row in rows:
        groups[(row.journal_id, row.normalized_title, row.publication_year)].append(row)

    candidates = {key: members for key, members in groups.items() if len(members) > 1}
    member_ids = [member.id for members in candidates.values() for member in members]
    abstracts: dict[int, str] = {}
    for start in range(0, len(member_ids), 500):
        chunk = member_ids[start : start + 500]
        abstracts.update(
            (article_id, _abstract_key(text))
            for article_id, text in db.execute(select(Article.id, Article.abstract).where(Article.id.in_(chunk)))
        )

    merges: list[tuple[int, list[int], str]] = []
    skipped: list[tuple[list[int], str, str]] = []
    for (_, title, _), members in candidates.items():
        ids = sorted(member.id for member in members)
        if len(title or "") < MIN_TITLE_LENGTH:
            skipped.append((ids, title, "sarlavha juda qisqa"))
            continue
        texts = {abstracts[member.id] for member in members if abstracts.get(member.id)}
        if len(texts) > 1:
            skipped.append((ids, title, "annotatsiyalar har xil"))
            continue
        if len({member.doi for member in members if member.doi}) > 1 and not texts:
            skipped.append((ids, title, "DOI'lar har xil, annotatsiya yo'q"))
            continue
        canonical = max(members, key=_rank)
        merges.append((canonical.id, sorted(member.id for member in members if member.id != canonical.id), title))
    return merges, skipped


def dedupe_articles(db: Session, *, dry_run: bool = True, report_dir: Path | None = None) -> dict[str, object]:
    merges, skipped = plan_duplicates(db)
    result: dict[str, object] = {
        "guruh": len(merges),
        "takror": sum(len(duplicates) for _, duplicates, _ in merges),
        "otkazildi_guruh": len(skipped),
        "rejim": "dry-run" if dry_run else "apply",
    }
    if report_dir is not None:
        report_dir.mkdir(parents=True, exist_ok=True)
        with (report_dir / "duplicates.csv").open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(["kanonik_id", "takror_id", "sarlavha"])
            for canonical, duplicates, title in merges:
                for duplicate in duplicates:
                    writer.writerow([canonical, duplicate, title])
        with (report_dir / "duplicates_skipped.csv").open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(["idlar", "sarlavha", "sabab"])
            for ids, title, reason in skipped:
                writer.writerow([" ".join(map(str, ids)), title, reason])
    if dry_run:
        return result

    now = datetime.now(timezone.utc)
    moved_records = moved_links = 0
    for canonical, duplicates, _ in merges:
        moved_records += db.execute(
            update(SourceRecord).where(SourceRecord.article_id.in_(duplicates)).values(article_id=canonical)
        ).rowcount or 0
        claimed = set(db.scalars(select(UserArticle.user_id).where(UserArticle.article_id == canonical)))
        for link in db.scalars(select(UserArticle).where(UserArticle.article_id.in_(duplicates))).all():
            if link.user_id in claimed:
                db.delete(link)
            else:
                link.article_id = canonical
                claimed.add(link.user_id)
                moved_links += 1
        db.execute(
            update(Article)
            .where(Article.id.in_(duplicates))
            .values(is_deleted=True, duplicate_of=canonical, updated_at=now)
        )
        db.execute(update(Article).where(Article.id == canonical).values(updated_at=now))
    db.commit()
    from . import seo

    seo.reset_cache()
    result["kochirilgan_manba_yozuvi"] = moved_records
    result["kochirilgan_muallif_boglanishi"] = moved_links
    return result
