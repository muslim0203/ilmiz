"""Robotlarga qaraydigan marshrutlar: robots.txt, sitemap va HTML qobiq.

Bu router `main.py` da eng oxirida ulanadi — ichida `/{path:path}` catch-all
bor va u ilgari ulansa `/api/*` ni ham yutib yuborardi.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator
from urllib.parse import quote, urlsplit, parse_qsl

from fastapi import APIRouter, Depends, Request, HTTPException, Query
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse, RedirectResponse, Response, StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .db import get_db
from .models import Article, Journal
from .services import seo

router = APIRouter(include_in_schema=False)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
# Sitemap fayli 50 000 URL va 50 MB bilan cheklangan; 25 000 xavfsiz zaxira
# qoldiradi va faylni Search Console tez o'qiydi.
SITEMAP_CHUNK = 25_000
_XML = "application/xml; charset=utf-8"

_template_cache: tuple[float, str] | None = None

FALLBACK_TEMPLATE = (
    '<!doctype html>\n<html lang="uz">\n  <head>\n    <meta charset="UTF-8" />\n'
    '    <meta name="viewport" content="width=device-width, initial-scale=1.0" />\n'
    "  </head>\n  <body>\n    <div id=\"root\"></div>\n  </body>\n</html>\n"
)


def dist_dir() -> Path:
    override = os.getenv("ILMIZ_DIST_DIR", "").strip()
    return Path(override) if override else PROJECT_ROOT / "dist"


def shell_template() -> str:
    """`dist/index.html` — o'zgarganda qayta o'qiladi, aks holda keshdan."""
    global _template_cache
    index = dist_dir() / "index.html"
    try:
        stamp = index.stat().st_mtime
    except OSError:
        return FALLBACK_TEMPLATE
    if _template_cache is None or _template_cache[0] != stamp:
        _template_cache = (stamp, index.read_text(encoding="utf-8"))
    return _template_cache[1]


def _iso(value: datetime | None) -> str:
    if value is None:
        return datetime.now(timezone.utc).date().isoformat()
    return value.date().isoformat()


# --------------------------------------------------------------- robots.txt


@router.get("/robots.txt")
def robots() -> PlainTextResponse:
    base = seo.site_url()
    if not seo.is_production_host():
        # Staging yoki lokal nusxa indeksga tushib, asosiy domen bilan
        # dublikat bo'lib qolmasligi kerak.
        return PlainTextResponse("User-agent: *\nDisallow: /\n", media_type="text/plain")

    lines = [
        "User-agent: *",
        "Allow: /",
        "Disallow: /api/admin/",
        "Disallow: /api/auth/",
        "",
        # Yandex UTM va boshqa kuzatuv parametrlarini alohida URL deb
        # hisoblamasin — aks holda bitta maqola o'nlab dublikatga bo'linadi.
        "User-agent: Yandex",
        "Allow: /",
        "Disallow: /api/admin/",
        "Disallow: /api/auth/",
        "Clean-param: utm_source&utm_medium&utm_campaign&utm_term&utm_content&ref&from",
        f"Host: {base.split('//', 1)[-1]}",
        "",
        "User-agent: Googlebot",
        "Allow: /",
        "Disallow: /api/admin/",
        "Disallow: /api/auth/",
        "",
        f"Sitemap: {base}/sitemap.xml",
        "",
    ]
    return PlainTextResponse("\n".join(lines), media_type="text/plain")


# ------------------------------------------------------------------ sitemap


def _url(loc: str, lastmod: str | None = None, changefreq: str | None = None, priority: str | None = None) -> str:
    parts = [f"<loc>{seo.e(loc)}</loc>"]
    if lastmod:
        parts.append(f"<lastmod>{lastmod}</lastmod>")
    if changefreq:
        parts.append(f"<changefreq>{changefreq}</changefreq>")
    if priority:
        parts.append(f"<priority>{priority}</priority>")
    return f"<url>{''.join(parts)}</url>"


def _stream(urls: Iterator[str]) -> StreamingResponse:
    def generate() -> Iterator[str]:
        yield '<?xml version="1.0" encoding="UTF-8"?>'
        yield '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        yield from urls
        yield "</urlset>"

    return StreamingResponse(
        generate(),
        media_type=_XML,
        headers={"Cache-Control": "public, max-age=3600"},
    )


def _article_chunks(db: Session) -> int:
    total = db.scalar(select(func.count()).select_from(Article).where(Article.is_deleted.is_(False))) or 0
    return max(1, -(-total // SITEMAP_CHUNK))


@router.get("/sitemap.xml")
def sitemap_index(db: Session = Depends(get_db)) -> Response:
    base = seo.site_url()
    children = ["/sitemap-pages.xml", "/sitemap-journals.xml"]
    children += [f"/sitemap-articles-{index}.xml" for index in range(1, _article_chunks(db) + 1)]
    body = "".join(
        f"<sitemap><loc>{seo.e(base + path)}</loc></sitemap>" for path in children
    )
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        f"{body}</sitemapindex>"
    )
    return Response(xml, media_type=_XML, headers={"Cache-Control": "public, max-age=3600"})


@router.get("/sitemap-pages.xml")
def sitemap_pages(db: Session = Depends(get_db)) -> StreamingResponse:
    def rows() -> Iterator[str]:
        for path, freq, priority in (
            ("/", "daily", "1.0"),
            ("/jurnallar", "daily", "0.9"),
            ("/maqolalar", "daily", "0.9"),
            ("/yangi-maqolalar", "daily", "0.9"),
            ("/sohalar", "weekly", "0.8"),
            ("/shaharlar", "weekly", "0.7"),
            ("/loyiha", "monthly", "0.4"),
            ("/maxfiylik", "yearly", "0.2"),
            ("/shartlar", "yearly", "0.2"),
        ):
            yield _url(seo.absolute(path), changefreq=freq, priority=priority)
        for name in seo.all_fields():
            yield _url(seo.absolute(seo.field_path(name)), changefreq="weekly", priority="0.8")
        for name in seo.cities(db):
            yield _url(seo.absolute(seo.city_path(name)), changefreq="weekly", priority="0.6")
        # Ro'yxat sahifalari maqolalarga olib boradigan yagona ichki yo'l —
        # ularsiz chuqurdagi maqolalar orfan bo'lib qoladi.
        journals = db.scalar(select(func.count()).select_from(Journal)) or 0
        for page in range(2, -(-journals // seo.JOURNALS_PER_PAGE) + 1):
            yield _url(seo.absolute(f"/jurnallar?sahifa={page}"), changefreq="weekly", priority="0.4")

    return _stream(rows())


@router.get("/sitemap-journals.xml")
def sitemap_journals(db: Session = Depends(get_db)) -> StreamingResponse:
    def rows() -> Iterator[str]:
        years: dict[int, list[int]] = {}
        for journal_id, year in db.execute(
            select(Article.journal_id, Article.publication_year)
            .where(Article.is_deleted.is_(False), Article.publication_year.is_not(None))
            .group_by(Article.journal_id, Article.publication_year)
        ):
            years.setdefault(journal_id, []).append(year)
        for journal_id, slug, updated in db.execute(
            select(Journal.id, Journal.slug, Journal.updated_at).order_by(Journal.id)
        ):
            lastmod = _iso(updated)
            yield _url(seo.absolute(seo.journal_path(slug)), lastmod, "weekly", "0.8")
            for year in sorted(years.get(journal_id, []), reverse=True):
                yield _url(seo.absolute(seo.journal_year_path(slug, year)), lastmod, "monthly", "0.5")

    return _stream(rows())


@router.get("/sitemap-articles-{index}.xml")
def sitemap_articles(index: int, db: Session = Depends(get_db)) -> Response:
    chunks = _article_chunks(db)
    if index < 1 or index > chunks:
        return Response(status_code=404, content="", media_type=_XML)

    def rows() -> Iterator[str]:
        statement = (
            select(Article.id, Article.title, Article.updated_at)
            .where(Article.is_deleted.is_(False))
            .order_by(Article.id)
            .offset((index - 1) * SITEMAP_CHUNK)
            .limit(SITEMAP_CHUNK)
        )
        for article_id, title, updated in db.execute(statement):
            yield _url(
                seo.absolute(seo.article_path(article_id, title)),
                _iso(updated),
                "yearly",
                "0.6",
            )

    return _stream(rows())


# ------------------------------------------------------- IndexNow va tasdiqlash


@router.get("/{key}.txt")
def indexnow_key(key: str) -> Response:
    """IndexNow kalitini o'z faylida qaytaradi (Yandex, Bing, Seznam)."""
    expected = os.getenv("ILMIZ_INDEXNOW_KEY", "").strip()
    if expected and key == expected:
        return PlainTextResponse(expected, media_type="text/plain")
    return _static_or_shell(f"/{key}.txt")


# ------------------------------------------------------------------ HTML qobiq


def _static_file(path: str) -> FileResponse | None:
    """`dist` ichidagi haqiqiy fayl (favicon, verification, og-image...)."""
    candidate = (dist_dir() / path.lstrip("/")).resolve()
    root = dist_dir().resolve()
    if not candidate.is_relative_to(root) or not candidate.is_file():
        return None
    immutable = "/assets/" in path
    return FileResponse(
        candidate,
        headers={
            "Cache-Control": "public, max-age=31536000, immutable" if immutable
            else "public, max-age=3600"
        },
    )


def _static_or_shell(path: str) -> Response:
    found = _static_file(path)
    return found if found is not None else Response(status_code=404)


@router.get("/api/seo")
def page_metadata(response: Response, path: str = Query(max_length=2048), db: Session = Depends(get_db)) -> dict:
    try:
        parsed = urlsplit(path)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid page path")
    if not path.startswith("/") or path.startswith("//") or parsed.scheme or parsed.netloc:
        raise HTTPException(status_code=400, detail="Only local page paths are accepted")
    meta = seo.build_page(db, parsed.path, dict(parse_qsl(parsed.query)))
    if meta.redirect:
        meta = seo.build_page(db, meta.path, dict(parse_qsl(parsed.query)))
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Robots-Tag"] = "noindex"
    return {"head": seo.render_head(meta), "body": meta.body, "status": meta.status, "path": meta.path}


@router.get("/{full_path:path}")
def shell(full_path: str, request: Request, db: Session = Depends(get_db)) -> Response:
    path = "/" + full_path
    if path == "/index.html":
        return RedirectResponse("/", status_code=301)
    static = _static_file(path)
    if static is not None:
        return static

    params = {key: value for key, value in request.query_params.items()}
    if path != "/" and path.endswith("/"):
        target = path.rstrip("/")
        return RedirectResponse(target + (f"?{request.url.query}" if request.url.query else ""), status_code=301)
    meta = seo.build_page(db, path, params)
    if meta.redirect:
        query = request.url.query
        target = f"{meta.redirect}?{query}" if query else meta.redirect
        return RedirectResponse(target, status_code=301)

    html = seo.render_shell(shell_template(), meta)
    return HTMLResponse(
        html,
        status_code=meta.status,
        headers={
            "Cache-Control": "public, max-age=300, stale-while-revalidate=86400",
            "X-Robots-Tag": seo.effective_robots(meta),
            "Link": f'<{quote(meta.canonical, safe=":/?=&#")}>; rel="canonical"',
        },
    )
