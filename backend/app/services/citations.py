from __future__ import annotations

import re

from ..models import Article


def _authors(article: Article, *, conjunction: str = "&") -> str:
    names = [name.strip() for name in article.authors if name.strip()]
    if not names:
        return "Noma’lum muallif"
    if len(names) == 1:
        return names[0]
    return f"{', '.join(names[:-1])}, {conjunction} {names[-1]}"


def _location(article: Article) -> str:
    parts: list[str] = []
    if article.volume:
        parts.append(article.volume)
    if article.issue:
        parts[-1:] = [f"{parts[-1]}({article.issue})"] if parts else [f"({article.issue})"]
    if article.pages:
        parts.append(article.pages)
    return ", ".join(parts)


def _url(article: Article) -> str:
    if article.doi:
        return f"https://doi.org/{article.doi}"
    return article.landing_url or article.pdf_url or ""


def gost_citation(article: Article) -> str:
    """GOST R 7.0.5 uslubi — OAK dissertatsiyalari va o'zbek jurnallarida talab qilinadi.

    Namuna: «Nurmatova Sh. Sarlavha // Фан спортга. – 2026. – T. 9, № 3. – B. 3–3.»
    Bet belgisi tilga qarab: o'zbekcha B., ruscha С., boshqalari P.
    """
    names = [name.strip() for name in article.authors if name.strip()]
    if len(names) > 3:
        author_part = f"{names[0]} va b."
    else:
        author_part = ", ".join(names) or "Noma’lum muallif"
    year = str(article.publication_year or "b. y.")
    parts = [f"{author_part} {article.title} // {article.journal.name}. – {year}."]
    location = []
    if article.volume:
        location.append(f"T. {article.volume}")
    if article.issue:
        location.append(f"№ {article.issue}")
    if location:
        parts.append(" – " + ", ".join(location) + ".")
    if article.pages:
        language = (article.language or "").casefold()
        marker = "B." if language in {"o‘zbek", "o'zbek", "uz", "ozbek"} else "С." if language in {"rus", "ru"} else "P."
        parts.append(f" – {marker} {article.pages}.")
    if article.doi:
        parts.append(f" – DOI: {article.doi}.")
    return "".join(parts)


def citation_formats(article: Article) -> dict[str, str]:
    year = str(article.publication_year or "n.d.")
    journal = article.journal.name
    location = _location(article)
    location_suffix = f", {location}" if location else ""
    url = _url(article)
    url_suffix = f" {url}" if url else ""
    authors_amp = _authors(article)
    authors_and = _authors(article, conjunction="and")
    key_author = re.sub(r"[^a-z0-9]+", "", (article.authors[0] if article.authors else "article").casefold()) or "article"
    bib_key = f"{key_author}{article.publication_year or 'nd'}"
    bib_fields = [
        f"  title = {{{article.title}}}",
        f"  author = {{{' and '.join(article.authors) or 'Unknown'}}}",
        f"  journal = {{{journal}}}",
        f"  year = {{{year}}}",
    ]
    for name, value in (("volume", article.volume), ("number", article.issue), ("pages", article.pages), ("doi", article.doi), ("url", url)):
        if value:
            bib_fields.append(f"  {name} = {{{value}}}")
    return {
        "apa": f"{authors_amp} ({year}). {article.title}. {journal}{location_suffix}.{url_suffix}".strip(),
        "gost": gost_citation(article),
        "mla": f'{authors_and}. “{article.title}.” {journal}{location_suffix}, {year}.{url_suffix}'.strip(),
        "chicago": f'{authors_and}. “{article.title}.” {journal}{location_suffix} ({year}).{url_suffix}'.strip(),
        "harvard": f"{authors_and} ({year}) ‘{article.title}’, {journal}{location_suffix}.{url_suffix}".strip(),
        "bibtex": "@article{" + bib_key + ",\n" + ",\n".join(bib_fields) + "\n}",
    }
