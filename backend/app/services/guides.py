"""`/yoriqnoma` qo'llanmalarini admin paneldan boshqarish."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Guide

SLUG_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{1,118}[a-z0-9])$")
MAX_BODY = 60_000


class GuideError(ValueError):
    """Kiritilgan qiymat noto'g'ri."""


def payload(guide: Guide) -> dict[str, Any]:
    return {
        "id": guide.id,
        "slug": guide.slug,
        "title": guide.title,
        "summary": guide.summary,
        "body": guide.body,
        "isPublished": guide.is_published,
        "words": len((guide.body or "").split()),
        "updatedAt": guide.updated_at.isoformat() if guide.updated_at else None,
    }


def _clean(db: Session, values: dict[str, Any], current: Guide | None) -> dict[str, Any]:
    slug = str(values.get("slug") or "").strip().lower()
    if not SLUG_RE.match(slug):
        raise GuideError("Manzil (slug) faqat kichik lotin harflari, raqam va chiziqchadan iborat bo‘lsin, 3–120 belgi")
    clash = db.scalar(select(Guide).where(Guide.slug == slug))
    if clash is not None and (current is None or clash.id != current.id):
        raise GuideError(f"«{slug}» manzili band")
    title = str(values.get("title") or "").strip()
    if not 5 <= len(title) <= 300:
        raise GuideError("Sarlavha 5–300 belgi bo‘lsin")
    body = str(values.get("body") or "").strip()
    if len(body) > MAX_BODY:
        raise GuideError(f"Matn {MAX_BODY} belgidan uzun bo‘lmasin")
    published = bool(values.get("isPublished"))
    if published and len(body.split()) < 150:
        # Yupqa sahifani indeksga taklif qilmaymiz — sifat mezoni bilan bir xil tamoyil.
        raise GuideError("Chop etish uchun matn kamida 150 so‘z bo‘lsin")
    summary = str(values.get("summary") or "").strip() or None
    return {"slug": slug, "title": title, "summary": summary, "body": body, "is_published": published}


def save(db: Session, values: dict[str, Any], guide: Guide | None = None) -> Guide:
    cleaned = _clean(db, values, guide)
    if guide is None:
        guide = Guide(**cleaned)
        db.add(guide)
    else:
        for key, value in cleaned.items():
            setattr(guide, key, value)
        guide.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(guide)
    return guide
