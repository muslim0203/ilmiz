"""Profil to'liqligi ballini yagona joyda hisoblaydi.

Ilgari hisob `collect_profile` ichida, yig'ish paytidagi lokal
o'zgaruvchilar ustidan bajarilardi. Natijada admin ma'lumotni qo'lda
kiritsa, ball eski holida qolib ketardi — «to'liqlik» aslida «scraper
nima topa oldi» degani edi.

Endi hisob bazadagi holatdan olinadi, shuning uchun uni qo'lda tahrirdan
keyin ham chaqirish mumkin.
"""
from __future__ import annotations

import re

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
from .text_clean import clean_address, prose

# ISSN formati: to'rt raqam, chiziqcha, uch raqam va nazorat belgisi.
ISSN_RE = re.compile(r"^\d{4}-\d{3}[\dX]$", re.I)

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


def _usable_contacts(db: Session, journal_id: int) -> bool:
    """Manzilning o'zi «aloqa ma'lumoti» emas — bog'lanish uchun kerak emas."""
    return bool(
        db.scalar(
            select(JournalContact.id).where(
                JournalContact.journal_id == journal_id,
                JournalContact.kind.in_(("email", "phone")),
            )
        )
    )


def _has_policy_text(db: Session, journal_id: int) -> bool:
    return bool(
        db.scalar(
            select(JournalPolicy.id).where(
                JournalPolicy.journal_id == journal_id,
                JournalPolicy.content.is_not(None),
                JournalPolicy.content != "",
            )
        )
    )


def _is_issue_reference(value: str | None) -> bool:
    """So'nggi son raqamsiz bo'lmaydi.

    Scraper 238 tadan 48 tasiga sahifa tugmalarini yozib qo'ygan:
    «Login», «Maqolalar», «Full Issue» — bular son ma'lumoti emas.
    """
    return bool(value) and any(char.isdigit() for char in value)


def breakdown(db: Session, journal: Journal) -> dict[str, bool]:
    """Har bir belgi to'ldirilganmi.

    Tekshiruv shunchaki «bo'sh emasmi» degani emas: axlat ham to'ldirilgan
    hisoblanib ballni ko'tarardi. Endi har bir belgi qiymat haqiqatan shu
    maydonga o'xshashini talab qiladi.

    Diqqat: `address` profil ustunidan olinadi, `journal_contacts` dagi
    manzil yozuvidan emas — bular ikki xil joy va bir-birini almashtirmaydi.
    """
    profile = db.scalar(
        select(JournalProfile).where(JournalProfile.journal_id == journal.id)
    )
    summary = profile.summary if profile else None
    address = profile.address if profile else None
    return {
        # `prose` qisqa qoldiq, sahifa kodi va menyuni rad etadi.
        "summary": prose(summary) is not None,
        # Saqlangan qiymat tozalashdan o'zgarmasa — bu haqiqatan manzil.
        "address": bool(address) and clean_address(address) == address,
        "contacts": _usable_contacts(db, journal.id),
        "editorial_members": _count(db, EditorialMember, journal.id) > 0,
        "policies": _has_policy_text(db, journal.id),
        "latest_issue": _is_issue_reference(profile.latest_issue if profile else None),
        "indexing_claims": _count(db, JournalIndexingClaim, journal.id) > 0,
        "issn": bool(journal.issn) and bool(ISSN_RE.match(journal.issn.strip())),
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
