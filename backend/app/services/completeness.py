"""Profil to'liqligi ballini yagona joyda hisoblaydi.

Ilgari hisob `collect_profile` ichida, yig'ish paytidagi lokal
o'zgaruvchilar ustidan bajarilardi. Natijada admin ma'lumotni qo'lda
kiritsa, ball eski holida qolib ketardi — «to'liqlik» aslida «scraper
nima topa oldi» degani edi.

Endi hisob bazadagi holatdan olinadi, shuning uchun uni qo'lda tahrirdan
keyin ham chaqirish mumkin.
"""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import (
    EditorialMember,
    Journal,
    JournalContact,
    JournalIndexingClaim,
    JournalPolicy,
    JournalProfile,
)

# Ball shu 10 belgining nechtasi to'ldirilganini o'lchaydi.
# Yorliqlar admin panelda «nima yetishmayapti» ro'yxati uchun.
FIELD_LABELS: dict[str, str] = {
    "summary": "Tavsif",
    "address": "Manzil",
    "contacts": "Aloqa ma’lumotlari",
    "editorial_members": "Tahririyat a’zolari",
    "policies": "Siyosat sahifalari",
    "latest_issue": "So‘nggi son",
    "indexing_claims": "Indekslanish",
    "issn": "ISSN",
    "fields": "Ilmiy sohalar",
    "languages": "Tillar",
}


def _count(db: Session, model, journal_id: int) -> int:
    return db.scalar(
        select(func.count()).select_from(model).where(model.journal_id == journal_id)
    ) or 0


def breakdown(db: Session, journal: Journal) -> dict[str, bool]:
    """Har bir belgi to'ldirilganmi.

    Diqqat: `address` profil ustunidan olinadi, `journal_contacts` dagi
    manzil yozuvidan emas — bular ikki xil joy va bir-birini almashtirmaydi.
    """
    profile = db.scalar(
        select(JournalProfile).where(JournalProfile.journal_id == journal.id)
    )
    return {
        "summary": bool(profile and profile.summary),
        "address": bool(profile and profile.address),
        "contacts": _count(db, JournalContact, journal.id) > 0,
        "editorial_members": _count(db, EditorialMember, journal.id) > 0,
        "policies": _count(db, JournalPolicy, journal.id) > 0,
        "latest_issue": bool(profile and profile.latest_issue),
        "indexing_claims": _count(db, JournalIndexingClaim, journal.id) > 0,
        "issn": bool(journal.issn),
        "fields": bool(journal.fields),
        "languages": bool(journal.languages),
    }


def score(db: Session, journal: Journal) -> float:
    checks = breakdown(db, journal)
    return round(100 * sum(checks.values()) / len(checks), 1)


def refresh(db: Session, journal: Journal) -> float | None:
    """Ballni qayta hisoblab profilga yozadi (commit qilmaydi).

    Profil yozuvi bo'lmasa `None` — ball saqlanadigan joy yo'q.
    """
    profile = db.scalar(
        select(JournalProfile).where(JournalProfile.journal_id == journal.id)
    )
    if profile is None:
        return None
    profile.completeness_score = score(db, journal)
    return profile.completeness_score


def missing_labels(db: Session, journal: Journal) -> list[str]:
    """To'ldirilmagan belgilarning o'qiladigan nomlari."""
    return [FIELD_LABELS[key] for key, ok in breakdown(db, journal).items() if not ok]


__all__ = ["FIELD_LABELS", "breakdown", "missing_labels", "refresh", "score"]
