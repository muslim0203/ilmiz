from __future__ import annotations

import hashlib
import html as html_module
import json
import re
import urllib.request
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Journal, OakImportRun, OakRegistryEntry, OakRegistrySnapshotEntry, OakRegistrySnapshotMeta
from .ingest import normalize_title

REGISTRY_URL = "https://journal-statistics-oak.vercel.app/"
PUSH_PATTERN = re.compile(r'self\.__next_f\.push\(\[1,"((?:\\.|[^"\\])*)"\]\)</script>', re.DOTALL)
PUBLICATION_COUNT_PATTERN = re.compile(r"(\d[\d\s\u00a0]*)\s*ta jurnal", re.I)

AREA_NAMES = {
    "Физика-математика фанлари": "Fizika-matematika",
    "Кимё фанлари": "Kimyo",
    "Биология фанлари": "Biologiya",
    "Геология-минералогия фанлари": "Geologiya-mineralogiya",
    "Техника фанлари": "Texnika",
    "Қишлоқ хўжалиги фанлари": "Qishloq xo‘jaligi",
    "Ижтимоий-гуманитар фанлар": "Ijtimoiy-gumanitar",
    "Тарих фанлари": "Tarix",
    "Иқтисодиёт фанлари": "Iqtisodiyot",
    "Фалсафа фанлари": "Falsafa",
    "Филология фанлари": "Filologiya",
    "Юридик фанлар": "Yuridik",
    "Педагогика фанлари": "Pedagogika",
    "Тиббиёт фанлари": "Tibbiyot",
    "Фармацевтика фанлари": "Farmatsevtika",
    "Ветеринария фанлари": "Veterinariya",
    "Санъатшунослик фанлари": "San’atshunoslik",
    "Архитектура": "Arxitektura",
    "Психология фанлари": "Psixologiya",
    "Социология фанлари": "Sotsiologiya",
    "Сиёсий фанлар": "Siyosiy fanlar",
    "География фанлари": "Geografiya",
    "Ҳарбий фанлар": "Harbiy fanlar",
    "Исломшунослик фанлари": "Islomshunoslik",
}

CYRILLIC_MAP = str.maketrans({
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "yo", "ж": "j",
    "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m", "н": "n", "о": "o",
    "п": "p", "р": "r", "с": "s", "т": "t", "у": "u", "ф": "f", "х": "x", "ц": "s",
    "ч": "ch", "ш": "sh", "щ": "sh", "ъ": "", "ы": "i", "ь": "", "э": "e", "ю": "yu",
    "я": "ya", "қ": "q", "ғ": "g", "ҳ": "h", "ў": "o",
})


def fetch_registry_html(url: str = REGISTRY_URL, timeout: int = 45) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": "IlmIz-OAK-Importer/0.3", "Accept": "text/html"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8")


def extract_registry_payload(document: str) -> dict[str, Any]:
    for match in PUSH_PATTERN.finditer(document):
        try:
            decoded = json.loads(f'"{match.group(1)}"')
        except json.JSONDecodeError:
            continue
        marker = '"payload":'
        position = decoded.find(marker)
        if position < 0:
            continue
        payload, _ = json.JSONDecoder().raw_decode(decoded[position + len(marker):])
        if isinstance(payload, dict) and "columns" in payload and "dicts" in payload:
            return payload
    raise ValueError("OAK registry payload topilmadi")


def decode_registry_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    columns = payload.get("columns")
    dictionaries = payload.get("dicts")
    rows = payload.get("data") or payload.get("rows") or payload.get("records")
    if not isinstance(columns, list) or not isinstance(dictionaries, dict) or not isinstance(rows, list):
        raise ValueError(f"Noma’lum registry payload: {sorted(payload.keys())}")
    records: list[dict[str, Any]] = []
    for row in rows:
        if isinstance(row, dict):
            records.append(row)
            continue
        if not isinstance(row, list):
            continue
        record: dict[str, Any] = {}
        for index, column in enumerate(columns):
            value = row[index] if index < len(row) else None
            dictionary = dictionaries.get(column)
            if isinstance(value, int) and isinstance(dictionary, list) and 0 <= value < len(dictionary):
                value = dictionary[value]
            record[str(column)] = value
        records.append(record)
    return records


def extract_publication_count(document: str) -> int | None:
    match = PUBLICATION_COUNT_PATTERN.search(document)
    if not match:
        return None
    digits = re.sub(r"\D", "", match.group(1))
    return int(digits) if digits else None


def slugify(value: str) -> str:
    value = value.casefold().translate(CYRILLIC_MAP)
    value = re.sub(r"https?://\S+", "", value)
    value = re.sub(r"[^a-z0-9]+", "-", value).strip("-")
    return value[:150] or f"jurnal-{hashlib.sha1(value.encode()).hexdigest()[:10]}"


def _clean(value: Any) -> str | None:
    if value is None:
        return None
    rendered = html_module.unescape(str(value)).strip().rstrip("\\")
    return rendered or None


def _is_national(record: dict[str, Any]) -> bool:
    kind = (_clean(record.get("kind")) or "").casefold()
    return "миллий" in kind or "milliy" in kind or "national" in kind


def _is_removed(record: dict[str, Any]) -> bool:
    status = " ".join(filter(None, [_clean(record.get("status")), _clean(record.get("removed")), _clean(record.get("name"))])).casefold()
    return any(token in status for token in ("чиқарил", "chiqaril", "removed", "исключ"))


def import_registry(db: Session, *, url: str = REGISTRY_URL, document: str | None = None) -> OakImportRun:
    run = OakImportRun(source_url=url)
    db.add(run)
    db.commit()
    try:
        document = document if document is not None else fetch_registry_html(url)
        run.source_sha256 = hashlib.sha256(document.encode("utf-8")).hexdigest()
        payload = extract_registry_payload(document)
        records = decode_registry_rows(payload)
        run.records_seen = len(records)
        publication_count = extract_publication_count(document)
        if publication_count is not None:
            run.snapshot_meta = OakRegistrySnapshotMeta(publication_count=publication_count, raw_row_count=len(records))
        existing_entries = list(db.scalars(select(OakRegistryEntry)))
        entry_by_key = {entry.source_key: entry for entry in existing_entries}
        seen_snapshot_keys: set[str] = set()
        current_journals = list(db.scalars(select(Journal)))
        journal_by_name = {normalize_title(journal.name): journal for journal in current_journals}
        used_slugs = {journal.slug for journal in current_journals}

        grouped: dict[str, list[tuple[dict[str, Any], OakRegistryEntry]]] = {}
        for raw in records:
            cleaned = {key: _clean(value) for key, value in raw.items()}
            name = cleaned.get("name")
            if not name:
                continue
            source_key = hashlib.sha256(json.dumps(cleaned, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
            entry = entry_by_key.get(source_key)
            if entry is None:
                entry = OakRegistryEntry(
                    import_run=run,
                    source_key=source_key,
                    name=name,
                    place=cleaned.get("place"),
                    organization=cleaned.get("org"),
                    specialty_code=cleaned.get("code"),
                    area=cleaned.get("area"),
                    note=cleaned.get("note"),
                    kind=cleaned.get("kind"),
                    status=cleaned.get("status"),
                    added=cleaned.get("added"),
                    year=cleaned.get("year"),
                    removed=cleaned.get("removed"),
                    decision=cleaned.get("decision"),
                    source_reference=cleaned.get("src"),
                    link=cleaned.get("link"),
                    raw_payload=cleaned,
                )
                db.add(entry)
                entry_by_key[source_key] = entry
                run.registry_created += 1
            if source_key not in seen_snapshot_keys:
                db.add(OakRegistrySnapshotEntry(import_run=run, registry_entry=entry))
                seen_snapshot_keys.add(source_key)
            if _is_national(cleaned):
                grouped.setdefault(normalize_title(name), []).append((cleaned, entry))

        db.flush()
        for normalized_name, items in grouped.items():
            first = items[0][0]
            journal = journal_by_name.get(normalized_name)
            if journal is None:
                base_slug = slugify(first["name"])
                slug = base_slug
                suffix = 2
                while slug in used_slugs:
                    slug = f"{base_slug}-{suffix}"
                    suffix += 1
                journal = Journal(
                    slug=slug,
                    name=first["name"],
                    short_name=first["name"][:110],
                    publisher=first.get("org") or "Noma’lum tashkilot",
                    city=first.get("place") or "Noma’lum",
                    fields=[],
                    languages=[],
                    oak_status="active",
                    access="unknown",
                    website=next((item[0].get("link") for item in items if item[0].get("link")), None),
                    description="OAK rasmiy elektron reestridan import qilingan jurnal.",
                )
                db.add(journal)
                db.flush()
                journal_by_name[normalized_name] = journal
                used_slugs.add(slug)
                run.journals_created += 1
            else:
                run.journals_updated += 1
            areas = {AREA_NAMES.get(item[0].get("area") or "", item[0].get("area")) for item in items}
            journal.fields = sorted({*journal.fields, *(area for area in areas if area)})
            journal.oak_status = "removed" if all(_is_removed(item[0]) for item in items) else "active"
            if not journal.website:
                journal.website = next((item[0].get("link") for item in items if item[0].get("link")), None)
            for _, entry in items:
                entry.journal = journal

        run.status = "succeeded"
    except Exception as error:
        run.status = "failed"
        run.error_summary = str(error)[:2000]
        raise
    finally:
        run.finished_at = datetime.now(timezone.utc)
        db.commit()
    db.refresh(run)
    return run
