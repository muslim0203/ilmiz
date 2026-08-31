"""IndexNow — yangi va o‘zgargan URL'larni qidiruv tizimlariga darhol bildirish.

Yandex, Bing va Seznam bitta protokolni qo‘llab-quvvatlaydi: bitta POST bilan
10 000 tagacha manzil yuboriladi va ular sitemap'ni qayta so‘rab o‘tirmasdan
navbatga qo‘yiladi. Google IndexNow'ga qo‘shilmagan — u sitemap va
`lastmod` orqali ishlaydi, shuning uchun sitemap baribir kerak.

Bu yerda hech narsa avtomatik yuborilmaydi: yuborish tashqi xizmatga
murojaat, shuning uchun uni `manage.py indexnow --apply` bilan qo‘lda
boshlanadi.
"""
from __future__ import annotations

import json
import os
import urllib.request
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Article, Journal
from . import seo

ENDPOINT = "https://api.indexnow.org/indexnow"
# Protokol chegarasi: bitta so‘rovda 10 000 URL.
BATCH = 10_000


def api_key() -> str:
    return os.getenv("ILMIZ_INDEXNOW_KEY", "").strip()


def changed_urls(db: Session, *, days: int = 7, limit: int = BATCH) -> list[str]:
    """So‘nggi `days` kun ichida o‘zgargan sahifalar.

    Har safar butun indeksni yuborish protokolni suiiste’mol qilish bo‘lardi;
    IndexNow'ning butun ma’nosi — faqat o‘zgarganini bildirish.
    """
    since = datetime.now(timezone.utc) - timedelta(days=days)
    urls: list[str] = []

    for slug, in db.execute(select(Journal.slug).where(Journal.updated_at >= since)):
        urls.append(seo.absolute(seo.journal_path(slug)))

    remaining = max(0, limit - len(urls))
    if remaining:
        rows = db.execute(
            select(Article.id, Article.title)
            .where(Article.is_deleted.is_(False), Article.updated_at >= since)
            .order_by(Article.updated_at.desc())
            .limit(remaining)
        )
        urls += [seo.absolute(seo.article_path(article_id, title)) for article_id, title in rows]

    return urls[:limit]


def submit(urls: list[str], *, timeout: int = 30) -> dict[str, object]:
    """URL'larni IndexNow'ga yuboradi. Kalit va prod domeni shart."""
    key = api_key()
    if not key:
        raise RuntimeError("ILMIZ_INDEXNOW_KEY sozlanmagan.")
    if not seo.is_production_host():
        raise RuntimeError("Prod domeni sozlanmagan: ILMIZ_SITE_URL kerak.")
    if not urls:
        return {"status": "skipped", "reason": "yuboriladigan URL yo‘q", "submitted": 0}

    host = seo.site_url().split("//", 1)[-1]
    payload = {
        "host": host,
        "key": key,
        # Kalit fayli saytning ildizida turadi — protokol egalikni shu bilan
        # tekshiradi.
        "keyLocation": seo.absolute(f"/{key}.txt"),
        "urlList": urls[:BATCH],
    }
    request = urllib.request.Request(
        ENDPOINT,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return {
            "status": "sent",
            "httpStatus": response.status,
            "submitted": len(payload["urlList"]),
            "host": host,
        }
