"""Bazadagi maqolalarni bir martalik tozalash (`manage.py clean-articles`).

Yangi harvest endi toza yozadi (`ingest._upsert_record`), bu modul esa
avval yig'ilganlarini to'g'rilaydi:

- `html`   — sarlavha va annotatsiyadagi HTML teg/entity'lar;
- `split`  — PDF'dan ko'chishda bo'lingan so'zlar (korpus chastotasi bo'yicha);
- `fields` — soha jurnaldan emas, maqolaning o'zidan (`field_classify`);
  admin qo'lda qo'ygan soha (`fields_manual`) tegilmaydi.

Standart holatda quruq yurish: hech narsa yozilmaydi, faqat hisobot.
Hisobot CSV'lari `report_dir` ga yoziladi (Excel uchun UTF-8 BOM bilan).
"""
from __future__ import annotations

import csv
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import bindparam, select, update
from sqlalchemy.orm import Session

from ..models import Article, Journal
from .article_text import SplitWordFixer, clean_markup, clean_title, suspect_fragments
from .field_classify import classify
from .search_text import article_search_text

STEPS = ("html", "split", "fields")


def _normalize_title(value: str) -> str:
    # `ingest.normalize_title` bilan bir xil bo'lishi shart (takror kaliti).
    from .ingest import normalize_title

    return normalize_title(value)


def _write_csv(path: Path, header: list[str], rows: list[list[object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)


def clean_articles(
    db: Session,
    *,
    dry_run: bool = True,
    steps: tuple[str, ...] = STEPS,
    report_dir: Path | None = None,
    batch_size: int = 2000,
) -> dict[str, object]:
    unknown = set(steps) - set(STEPS)
    if unknown:
        raise ValueError(f"Noma'lum qadam: {', '.join(sorted(unknown))}")
    journal_fields = {journal_id: fields or [] for journal_id, fields in db.execute(select(Journal.id, Journal.fields))}
    rows = db.execute(
        select(
            Article.id, Article.journal_id, Article.title, Article.abstract, Article.keywords,
            Article.authors, Article.fields, Article.fields_manual,
        ).where(Article.is_deleted.is_(False))
    ).all()

    # 1-o'tish: HTML tozalangan matn (split lug'ati ham toza matndan quriladi).
    cleaned: dict[int, tuple[str, str | None]] = {}
    for row in rows:
        if "html" in steps:
            cleaned[row.id] = (clean_title(row.title) or row.title, clean_markup(row.abstract))
        else:
            cleaned[row.id] = (row.title, row.abstract)

    fixer = None
    if "split" in steps:
        fixer = SplitWordFixer.from_texts(text for pair in cleaned.values() for text in pair)

    totals: Counter[str] = Counter()
    split_rows: list[list[object]] = []
    suspect_rows: list[list[object]] = []
    field_rows: list[list[object]] = []
    planned: list[dict[str, object]] = []
    now = datetime.now(timezone.utc)

    for row in rows:
        totals["tekshirildi"] += 1
        title, abstract = cleaned[row.id]
        if title != row.title:
            totals["html_sarlavha"] += 1
        if abstract != row.abstract:
            totals["html_annotatsiya"] += 1

        if fixer is not None:
            fixed_title, title_changes = fixer.fix(title)
            fixed_abstract, abstract_changes = fixer.fix(abstract)
            changes = title_changes + abstract_changes
            if changes:
                totals["split_maqola"] += 1
                totals["split_tuzatish"] += len(changes)
                if title_changes:
                    totals["split_sarlavha"] += 1
                for before, after in changes:
                    split_rows.append([row.id, before, after])
            title, abstract = fixed_title or title, fixed_abstract
            for fragment in suspect_fragments(abstract):
                suspect_rows.append([row.id, fragment])
            totals["split_shubhali"] += bool(suspect_fragments(abstract))

        fields = list(row.fields or [])
        if "fields" in steps and not row.fields_manual:
            fields = classify(title, row.keywords or [], abstract, journal_fields.get(row.journal_id))
            if fields != list(row.fields or []):
                totals["soha_ozgardi"] += 1
                field_rows.append([row.id, "; ".join(row.fields or []), "; ".join(fields)])
        totals["soha_bosh" if not fields else "soha_bor"] += 1
        totals["soha_qolda"] += bool(row.fields_manual)

        if title != row.title or abstract != row.abstract or fields != list(row.fields or []):
            totals["yangilanadi"] += 1
            planned.append({
                "_id": row.id,
                "title": title,
                "normalized_title": _normalize_title(title),
                "abstract": abstract,
                "fields": fields,
                "search_text": article_search_text(title, abstract, row.authors),
                "updated_at": now,
            })

    if report_dir is not None:
        _write_csv(report_dir / "split_words_fixed.csv", ["article_id", "oldin", "keyin"], split_rows)
        _write_csv(report_dir / "split_words_suspects.csv", ["article_id", "bolak"], suspect_rows)
        _write_csv(report_dir / "fields_changed.csv", ["article_id", "eski_soha", "yangi_soha"], field_rows)

    result: dict[str, object] = dict(totals)
    result["rejim"] = "dry-run" if dry_run else "apply"
    if dry_run or not planned:
        return result

    # O'qish tugagach yoziladi: oqim o'rtasida commit kursorni buzardi
    # (`reparse_bibliographic` dagi kabi). FTS triggeri `search_text` ni
    # har qatorda o'zi yangilaydi.
    table = Article.__table__
    statement = (
        update(table)
        .where(table.c.id == bindparam("_id"))
        .values(
            title=bindparam("title"),
            normalized_title=bindparam("normalized_title"),
            abstract=bindparam("abstract"),
            fields=bindparam("fields"),
            search_text=bindparam("search_text"),
            updated_at=bindparam("updated_at"),
        )
    )
    for start in range(0, len(planned), batch_size):
        db.connection().execute(statement, planned[start : start + batch_size])
        db.commit()
    from . import seo

    seo.reset_cache()
    return result
