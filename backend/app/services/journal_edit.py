"""Jurnal ma'lumotlarini admin paneldan qo'lda tahrirlash.

Nega kerak: yuqori manbalar ham xato qiladi. OAK rasmiy reestrida Infolib
uchun boshqa jurnalning havolasi ko'rsatilgan edi, tadqiq.uz ham shu xatoni
takrorlagan (`docs/manual-corrections.md`). Bunday holatda yagona to'g'ri
manba — tekshirgan odam.

Har bir qo'lda kiritilgan o'zgarish `journal_profile_fields` da
`verification_status="manual"` bilan qayd etiladi. Bu ikki narsa beradi:
kim nimani o'zgartirganini ko'rsatuvchi iz, va importlar uchun "bu maydonga
tegmang" belgisi.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Journal, JournalContact, JournalProfileField
from .profile_collector import is_valid_phone

MANUAL_SOURCE = "admin:manual"
MANUAL_STATUS = "manual"

# ISSN formati: to'rt raqam, chiziqcha, uch raqam va nazorat belgisi (X ham).
ISSN_RE = re.compile(r"^\d{4}-\d{3}[\dX]$")
OAK_STATUSES = {"active", "removed"}
ACCESS_LEVELS = {"open", "closed", "mixed", "unknown"}
MIN_FOUNDED = 1860

TEXT_FIELDS = ("name", "short_name", "publisher", "city", "website", "description")
LIST_FIELDS = ("fields", "languages")
EDITABLE = TEXT_FIELDS + LIST_FIELDS + ("issn", "eissn", "oak_status", "access", "founded")

# Bo'sh qoldirilishi mumkin bo'lgan maydonlar. Qolganlari majburiy — jurnalning
# nomi yoki nashriyoti bo'sh bo'lib qolsa, yozuv ma'nosini yo'qotadi.
NULLABLE = {"issn", "eissn", "founded", "website", "description"}


class ValidationError(ValueError):
    """Kiritilgan qiymat noto'g'ri."""


def _clean_issn(value: str) -> str | None:
    text = value.strip().upper().replace("–", "-")
    if not text:
        return None
    if not ISSN_RE.match(text):
        raise ValidationError(f"ISSN formati noto‘g‘ri: {value!r}. Kutilgan shakl: 1234-567X")
    return text


def _clean_founded(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        year = int(value)
    except (TypeError, ValueError) as error:
        raise ValidationError(f"Asos solingan yil butun son bo‘lishi kerak: {value!r}") from error
    limit = datetime.now(timezone.utc).year + 1
    if not MIN_FOUNDED <= year <= limit:
        raise ValidationError(f"Asos solingan yil {MIN_FOUNDED}–{limit} oralig‘ida bo‘lsin")
    return year


def _clean_website(value: str) -> str | None:
    text = value.strip()
    if not text:
        return None
    if not text.startswith(("http://", "https://")):
        raise ValidationError("Sayt manzili http:// yoki https:// bilan boshlanishi kerak")
    return text


def _clean_list(name: str, value: Any) -> list[str]:
    if not isinstance(value, list):
        raise ValidationError(f"{name} ro‘yxat bo‘lishi kerak")
    cleaned = []
    for item in value:
        text = str(item).strip()
        if text and text not in cleaned:
            cleaned.append(text)
    return cleaned


def clean(field: str, value: Any) -> Any:
    """Bitta maydon qiymatini tekshiradi va normal shaklga keltiradi."""
    if field in ("issn", "eissn"):
        return _clean_issn("" if value is None else str(value))
    if field == "founded":
        return _clean_founded(value)
    if field == "website":
        return _clean_website("" if value is None else str(value))
    if field in LIST_FIELDS:
        return _clean_list(field, value)
    if field == "oak_status":
        text = str(value or "").strip()
        if text not in OAK_STATUSES:
            raise ValidationError(f"OAK holati {sorted(OAK_STATUSES)} dan biri bo‘lsin")
        return text
    if field == "access":
        text = str(value or "").strip()
        if text not in ACCESS_LEVELS:
            raise ValidationError(f"Kirish turi {sorted(ACCESS_LEVELS)} dan biri bo‘lsin")
        return text
    if field in TEXT_FIELDS:
        text = "" if value is None else str(value).strip()
        if not text:
            if field in NULLABLE:
                return None
            raise ValidationError(f"{field} bo‘sh bo‘lmasin")
        return text
    raise ValidationError(f"Bu maydonni tahrirlab bo‘lmaydi: {field}")


def duplicate_issn_warnings(db: Session, journal: Journal, changes: dict[str, Any]) -> list[str]:
    """ISSN dunyo bo‘ylab yagona. Takrorlansa — biri xato.

    Bloklamaymiz: bazada allaqachon 16 ta takror bor va ularni tuzatish
    jarayonida vaqtinchalik ikkilanish bo‘lishi tabiiy. Lekin ogohlantiramiz.
    """
    warnings: list[str] = []
    for field in ("issn", "eissn"):
        value = changes.get(field)
        if not value:
            continue
        clash = db.scalars(
            select(Journal).where(
                Journal.id != journal.id,
                (Journal.issn == value) | (Journal.eissn == value),
            )
        ).first()
        if clash is not None:
            warnings.append(
                f"{field.upper()} {value} allaqachon «{clash.name}» jurnalida turibdi — "
                "biri xato bo‘lishi mumkin."
            )
    return warnings


def record_manual(db: Session, journal: Journal, field: str, value: Any) -> None:
    """O'zgarishni provenance jadvaliga yozadi (import bu belgini hurmat qiladi)."""
    entry = db.scalar(
        select(JournalProfileField).where(
            JournalProfileField.journal_id == journal.id,
            JournalProfileField.field_name == f"manual:{field}",
        )
    )
    if entry is None:
        entry = JournalProfileField(
            journal_id=journal.id,
            field_name=f"manual:{field}",
            source_url=MANUAL_SOURCE,
        )
        db.add(entry)
    entry.value = value
    entry.confidence = 1.0
    entry.verification_status = MANUAL_STATUS
    entry.fetched_at = datetime.now(timezone.utc)


def manually_edited(db: Session, journal_id: int) -> set[str]:
    """Shu jurnalda qo'lda tahrirlangan maydonlar nomi."""
    names = db.scalars(
        select(JournalProfileField.field_name).where(
            JournalProfileField.journal_id == journal_id,
            JournalProfileField.verification_status == MANUAL_STATUS,
        )
    )
    return {name.split(":", 1)[1] for name in names if ":" in name}


def apply_edits(
    db: Session, journal: Journal, changes: dict[str, Any]
) -> tuple[dict[str, Any], list[str]]:
    """Tekshiradi, qo'llaydi va nimalar o'zgarganini qaytaradi.

    Faqat haqiqatan boshqa bo'lgan qiymatlar yoziladi — shunda tegilmagan
    maydon uchun ortiqcha "qo'lda tahrirlangan" belgisi qo'yilmaydi.
    """
    unknown = set(changes) - set(EDITABLE)
    if unknown:
        raise ValidationError(f"Noma’lum maydon: {', '.join(sorted(unknown))}")

    cleaned = {field: clean(field, value) for field, value in changes.items()}
    warnings = duplicate_issn_warnings(db, journal, cleaned)

    applied: dict[str, Any] = {}
    for field, value in cleaned.items():
        if getattr(journal, field) == value:
            continue
        setattr(journal, field, value)
        record_manual(db, journal, field, value)
        applied[field] = value

    if applied:
        db.commit()
        db.refresh(journal)
    return applied, warnings


def editable_payload(db: Session, journal: Journal) -> dict[str, Any]:
    """Tahrirlash formasi uchun joriy qiymatlar va qaysilari qo'lda o'zgargani."""
    return {
        "slug": journal.slug,
        "values": {field: getattr(journal, field) for field in EDITABLE},
        "manualFields": sorted(manually_edited(db, journal.id)),
        "updatedAt": journal.updated_at.isoformat() if journal.updated_at else None,
        "choices": {
            "oakStatus": sorted(OAK_STATUSES),
            "access": sorted(ACCESS_LEVELS),
        },
    }


__all__ = [
    "EDITABLE",
    "ValidationError",
    "apply_edits",
    "clean",
    "editable_payload",
    "manually_edited",
]


# --- Aloqa ma'lumotlari ---------------------------------------------------

CONTACT_KINDS = ("address", "email", "phone")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")
MAX_ADDRESS = 400
KIND_LABELS = {"address": "Manzil", "email": "Email", "phone": "Telefon"}


def _balance_parens(value: str) -> str:
    """Juftlashmagan qavslarni olib tashlaydi.

    Scraper'ning `\+?\d[\d ()\-]{7,}\d` naqshi raqamdan boshlanadi,
    shuning uchun `+998(71) 262-31-69` dan `+99871) 262-31-69` qolgan —
    bazada 127 ta shunday yozuv bor. Ochuvchi qavsni qayerga qo'yishni
    taxmin qilmaymiz: ortiqcha qavsni olib tashlash raqamni buzmaydi.
    """
    depth = 0
    kept: list[str] = []
    for char in value:
        if char == "(":
            depth += 1
        elif char == ")":
            if depth == 0:
                continue
            depth -= 1
        kept.append(char)
    if depth:  # ochilgan, lekin yopilmagan
        remaining = depth
        result = []
        for char in reversed(kept):
            if char == "(" and remaining:
                remaining -= 1
                continue
            result.append(char)
        kept = list(reversed(result))
    return re.sub(r"\s{2,}", " ", "".join(kept)).strip()


def clean_contact(kind: str, value: str, label: str | None) -> tuple[str, str, str | None]:
    """Bitta aloqa yozuvini tekshiradi va normal shaklga keltiradi."""
    kind = (kind or "").strip()
    if kind not in CONTACT_KINDS:
        raise ValidationError(f"Aloqa turi {list(CONTACT_KINDS)} dan biri bo‘lsin")
    text = (value or "").strip()
    if not text:
        raise ValidationError("Aloqa qiymati bo‘sh bo‘lmasin")

    if kind == "email":
        text = text.lower()
        if not EMAIL_RE.match(text):
            raise ValidationError(f"Email manzili noto‘g‘ri: {value!r}")
    elif kind == "phone":
        text = _balance_parens(text)
        # `is_valid_phone` sana, ISSN va yillar ro'yxatini telefondan ajratadi.
        if not is_valid_phone(text):
            raise ValidationError(f"Telefon raqami noto‘g‘ri: {value!r}")
    else:
        if len(text) > MAX_ADDRESS:
            raise ValidationError(
                f"Manzil {MAX_ADDRESS} belgidan uzun bo‘lmasin (hozir {len(text)}). "
                "Tahririyat ro‘yxati manzil emas."
            )

    clean_label = (label or "").strip() or KIND_LABELS[kind]
    return kind, text, clean_label


def contacts_payload(journal: Journal) -> list[dict[str, Any]]:
    return [
        {
            "id": contact.id,
            "kind": contact.kind,
            "label": contact.label,
            "value": contact.value,
            "sourceUrl": contact.source_url,
            "isManual": contact.source_url == MANUAL_SOURCE,
        }
        for contact in sorted(journal.contacts, key=lambda item: (item.kind, item.id))
    ]


def replace_contacts(
    db: Session, journal: Journal, rows: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], list[str]]:
    """Jurnalning aloqa ro'yxatini butunlay almashtiradi.

    Hammasi avval tekshiriladi — bittasi xato bo'lsa hech narsa o'zgarmaydi.
    O'zgarmagan yozuvning manbasi saqlanadi, shunda qayerdan olingani
    ma'lum bo'lib qoladi.
    """
    cleaned: list[tuple[str, str, str | None]] = []
    seen: set[tuple[str, str]] = set()
    warnings: list[str] = []
    for row in rows:
        kind, value, label = clean_contact(
            str(row.get("kind", "")), str(row.get("value", "")), row.get("label")
        )
        if (kind, value) in seen:
            warnings.append(f"Takrorlangan yozuv tashlab ketildi: {value}")
            continue
        seen.add((kind, value))
        cleaned.append((kind, value, label))

    previous = {(contact.kind, contact.value): contact.source_url for contact in journal.contacts}
    now = datetime.now(timezone.utc)
    for contact in list(journal.contacts):
        db.delete(contact)
    db.flush()
    for kind, value, label in cleaned:
        db.add(
            JournalContact(
                journal_id=journal.id,
                kind=kind,
                label=label,
                value=value,
                # Yangi yoki tuzatilgan yozuv qo'lda kiritilgan hisoblanadi.
                source_url=previous.get((kind, value), MANUAL_SOURCE),
                fetched_at=now,
            )
        )
    db.commit()
    db.refresh(journal)
    return contacts_payload(journal), warnings
