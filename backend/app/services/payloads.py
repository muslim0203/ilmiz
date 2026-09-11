"""API va server HTML uchun umumiy JSON ko'rinishlar.

`article_payload` ilgari `main.py` da edi. Endi SEO qobig'i ham uni
sahifaga `<script id="ilmiz-data">` sifatida joylaydi: React birinchi
yuklashda `/api/articles/{id}` ga qayta murojaat qilmaydi. Googlebot har
maqola uchun ikki so'rov (HTML + API) sarflardi — nginx logida 6 054 sahifa
va 5 919 API so'rovi; endi bittasi yetadi, ya'ni o'sha crawl-byudjet ikki
barobar ko'p sahifaga yetadi.
"""
from __future__ import annotations

from ..models import Article
from .citations import citation_formats


def article_payload(article: Article) -> dict[str, object]:
    return {
        "id": str(article.id),
        "title": article.title,
        "authors": article.authors,
        "journalId": article.journal.slug,
        "journalName": article.journal.name,
        "publicationDate": article.publication_date,
        "year": article.publication_year or 0,
        "volume": article.volume or "—",
        "issue": article.issue or "—",
        "pages": article.pages or "—",
        "language": article.language or "Noma’lum",
        "fields": article.fields,
        "abstract": article.abstract or "Annotatsiya taqdim etilmagan.",
        "keywords": article.keywords,
        "doi": article.doi,
        "hasPdf": bool(article.pdf_url),
        "pdfUrl": article.pdf_url,
        "harvestedAt": article.harvested_at.isoformat(),
        "landingUrl": article.landing_url,
        "citations": citation_formats(article),
        "isDemo": bool(article.doi and article.doi.startswith("10.0000/demo")),
    }
