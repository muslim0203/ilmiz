from __future__ import annotations

import html
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib.parse import unquote, urljoin, urlparse

import httpx
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from . import completeness
from .text_clean import (
    BOILERPLATE_RE,
    MIN_PROSE_LENGTH,
    PHONE_RE,
    balance_parens,
    clean_address,
    clean_text,
    compact,
    is_valid_phone,
    prose,
    strip_boilerplate,
)
from ..models import (
    EditorialMember,
    Journal,
    JournalContact,
    JournalIndexingClaim,
    JournalLink,
    JournalPolicy,
    JournalProfile,
    JournalProfileField,
    JournalSection,
)

MANUAL_SOURCE = "admin:manual"
MANUAL_STATUS = "manual"
USER_AGENT = "Mozilla/5.0 (compatible; IlmIzJournalProfiler/0.4; +public scholarly metadata index)"
EMAIL_RE = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.I)
ORCID_RE = re.compile(r"\b\d{4}-\d{4}-\d{4}-[\dX]{4}\b", re.I)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def decode_response(response: httpx.Response) -> str:
    text = response.text
    if text.count("\ufffd") > max(3, len(text) // 1000):
        for encoding in ("cp1251", "windows-1251"):
            try:
                candidate = response.content.decode(encoding)
            except UnicodeDecodeError:
                continue
            if candidate.count("\ufffd") < text.count("\ufffd"):
                return candidate
    return text


@dataclass
class ParsedPage:
    url: str
    title: str = ""
    main_text: str = ""
    headings: list[str] = field(default_factory=list)
    paragraphs: list[str] = field(default_factory=list)
    list_items: list[str] = field(default_factory=list)
    links: list[tuple[str, str]] = field(default_factory=list)
    emails: list[str] = field(default_factory=list)
    address: str | None = None


class PageParser(HTMLParser):
    def __init__(self, url: str):
        super().__init__(convert_charrefs=True)
        self.url = url
        self.title_parts: list[str] = []
        self.main_parts: list[str] = []
        self.body_parts: list[str] = []
        self.headings: list[str] = []
        self.paragraphs: list[str] = []
        self.list_items: list[str] = []
        self.links: list[tuple[str, str]] = []
        self.emails: list[str] = []
        self.address_parts: list[str] = []
        self.depth = 0
        self.main_depth: int | None = None
        self.capture: tuple[str, int, list[str]] | None = None
        self.link: tuple[int, str, list[str]] | None = None
        self.in_title = False
        self.script_parts: list[str] = []
        self.in_script = False
        self.in_style = False
        self.body_depth: int | None = None
        self.address_depth: int | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_map = {key: value or "" for key, value in attrs}
        classes = set(attrs_map.get("class", "").split())
        self.depth += 1
        if tag == "title":
            self.in_title = True
        if tag == "script":
            self.in_script = True
            self.script_parts = []
        if tag == "style":
            self.in_style = True
        if tag == "body":
            self.body_depth = self.depth
        if self.main_depth is None and (
            attrs_map.get("id") == "pkp_content_main"
            or tag == "main"
            or "pkp_structure_main" in classes
        ):
            self.main_depth = self.depth
        if self.address_depth is None and "address" in classes:
            self.address_depth = self.depth
        if self.main_depth is not None and tag in {"h1", "h2", "h3", "h4", "p", "li"}:
            self.capture = (tag, self.depth, [])
        if tag == "a":
            href = attrs_map.get("href", "")
            self.link = (self.depth, urljoin(self.url, href), [])
            if href.lower().startswith("mailto:"):
                self.emails.append(unquote(href[7:].split("?", 1)[0]))

    def handle_endtag(self, tag: str) -> None:
        if self.capture and self.capture[1] == self.depth and self.capture[0] == tag:
            text = clean_text(" ".join(self.capture[2]))
            if text:
                if tag.startswith("h"):
                    self.headings.append(text)
                elif tag == "p":
                    self.paragraphs.append(text)
                elif tag == "li":
                    self.list_items.append(text)
            self.capture = None
        if self.link and self.link[0] == self.depth and tag == "a":
            label = clean_text(" ".join(self.link[2]))
            if self.link[1]:
                self.links.append((label, self.link[1]))
            self.link = None
        if tag == "title":
            self.in_title = False
        if tag == "script":
            decoded = unquote("".join(self.script_parts))
            self.emails.extend(EMAIL_RE.findall(decoded))
            self.in_script = False
        if tag == "style":
            self.in_style = False
        if self.body_depth == self.depth:
            self.body_depth = None
        if self.address_depth == self.depth:
            self.address_depth = None
        if self.main_depth == self.depth:
            self.main_depth = None
        self.depth -= 1

    def handle_data(self, data: str) -> None:
        if self.in_title:
            self.title_parts.append(data)
        if self.in_script:
            self.script_parts.append(data)
        if self.main_depth is not None:
            self.main_parts.append(data)
        if self.body_depth is not None and not self.in_script and not self.in_style:
            self.body_parts.append(data)
        if self.capture:
            self.capture[2].append(data)
        if self.link:
            self.link[2].append(data)
        if self.address_depth is not None:
            self.address_parts.append(data)

    def result(self) -> ParsedPage:
        main_text = clean_text(" ".join(self.main_parts)) or clean_text(" ".join(self.body_parts))
        emails = list(dict.fromkeys(value.lower() for value in self.emails + EMAIL_RE.findall(main_text)))
        return ParsedPage(
            url=self.url,
            title=clean_text(" ".join(self.title_parts)),
            main_text=main_text,
            headings=list(dict.fromkeys(self.headings)),
            paragraphs=list(dict.fromkeys(self.paragraphs)),
            list_items=list(dict.fromkeys(self.list_items)),
            links=list(dict.fromkeys(self.links)),
            emails=emails,
            address=clean_text(" ".join(self.address_parts)) or None,
        )


def parse_page(url: str, markup: str) -> ParsedPage:
    parser = PageParser(url)
    parser.feed(markup)
    return parser.result()


def ojs_routes(website: str) -> dict[str, str]:
    base = website.rstrip("/") + "/"
    return {
        "home": base,
        "about": urljoin(base, "about"),
        "contact": urljoin(base, "about/contact"),
        "editorial": urljoin(base, "about/editorialTeam"),
        "submissions": urljoin(base, "about/submissions"),
        "current": urljoin(base, "issue/current"),
    }


def fetch_pages(website: str, timeout: float = 20.0) -> dict[str, ParsedPage]:
    pages: dict[str, ParsedPage] = {}

    def fetch_batch(items: list[tuple[str, str]]) -> None:
        def fetch_one(kind: str, url: str) -> tuple[str, ParsedPage]:
            response = httpx.get(
                url,
                timeout=timeout,
                follow_redirects=True,
                headers={"User-Agent": USER_AGENT},
            )
            response.raise_for_status()
            return kind, parse_page(str(response.url), decode_response(response))

        with ThreadPoolExecutor(max_workers=min(4, len(items) or 1)) as executor:
            futures = {executor.submit(fetch_one, kind, url): kind for kind, url in items}
            for future in as_completed(futures):
                try:
                    kind, page = future.result()
                except (httpx.HTTPError, ValueError):
                    continue
                pages[kind] = page

    fetch_batch(list(ojs_routes(website).items()))
    if not pages:
        parsed = urlparse(website)
        variants: list[str] = []
        for scheme in (parsed.scheme, "http" if parsed.scheme == "https" else "https"):
            hosts = [parsed.netloc]
            hosts.append(parsed.netloc[4:] if parsed.netloc.startswith("www.") else f"www.{parsed.netloc}")
            for host in hosts:
                variants.append(parsed._replace(scheme=scheme, netloc=host).geturl())
        fetch_batch([(f"fallback_{index}", url) for index, url in enumerate(dict.fromkeys(variants))])
        if pages:
            pages["home"] = next(iter(pages.values()))
    home = pages.get("home")
    if home:
        host = urlparse(website).netloc
        classifiers = {
            "aims": ("aim", "purpose", "цели", "задачи", "maqsad"),
            "editorial_custom": ("editor", "редактор", "редакци", "tahrir"),
            "privacy": ("privacy", "конфиденц", "maxfiy"),
            "ethics": ("ethic", "этик", "odob"),
            "authors": ("author", "автор", "muallif"),
            "open_access": ("open access", "открыт", "ochiq"),
            "peer_review": ("peer review", "реценз", "taqriz"),
            "contact_custom": ("contact", "контакт", "aloqa"),
        }
        candidates: dict[str, str] = {}
        for label, url in home.links:
            lowered = f"{label} {url}".lower()
            if urlparse(url).netloc != host or "/article/" in lowered or "/issue/" in lowered:
                continue
            for kind, needles in classifiers.items():
                if kind not in candidates and any(needle in lowered for needle in needles):
                    candidates[kind] = url
        fetch_batch(list(candidates.items())[:12])
    if not pages:
        raise RuntimeError("Jurnal saytidan ochiq sahifalar olinmadi")
    return pages


# Sahifadan matn olganda footer skripti va brauzer ogohlantirishlari ham
# qo'shilib ketadi. Haqiqiy matn odatda boshida turadi, shuning uchun shu
# belgilardan keyingi hamma narsani kesamiz.
def extract_editorial_members(page: ParsedPage | None) -> list[dict[str, str | None]]:
    if not page:
        return []
    candidates = page.paragraphs + page.list_items
    members: list[dict[str, str | None]] = []
    role = None
    for heading in page.headings:
        lowered = heading.lower()
        if any(word in lowered for word in ("editor", "редактор", "tahrir", "chief")):
            role = heading
            break
    for value in candidates:
        text = clean_text(value)
        if len(text) < 4 or len(text) > 500:
            continue
        lowered = text.lower()
        if not any(word in lowered for word in ("editor", "редактор", "prof", "phd", "d.sc", "doktor", "академ")):
            continue
        role_match = re.match(
            r"(?P<role>главный редактор|заместитель редактора|editor[- ]in[- ]chief|deputy editor|bosh muharrir|muharrir)\s*[:—-]?\s*(?P<name>.+)",
            text,
            re.I,
        )
        if role_match:
            detected_role = clean_text(role_match.group("role"))
            name = clean_text(role_match.group("name")).strip(" .")[:500]
        else:
            detected_role = role or "Tahrir hay’ati a’zosi"
            name = text[:500]
        if name.lower() == detected_role.lower():
            continue
        parts = [clean_text(item) for item in re.split(r"[;|]", text) if clean_text(item)]
        members.append({
            "name": name,
            "role": detected_role,
            "affiliation": parts[1][:1000] if len(parts) > 1 else None,
            "orcid": next(iter(ORCID_RE.findall(text)), None),
            "email": next(iter(EMAIL_RE.findall(text)), None),
        })
    unique: dict[str, dict[str, str | None]] = {}
    for member in members:
        unique[member["name"].lower()] = member
    return list(unique.values())[:100]


def extract_indexing_claims(pages: dict[str, ParsedPage]) -> list[str]:
    text = " ".join(page.main_text for page in pages.values()).lower()
    providers = {
        "Crossref": ("crossref",),
        "DOAJ": ("doaj", "directory of open access journals"),
        "OpenAlex": ("openalex",),
        "ResearchBib": ("researchbib",),
        "Index Copernicus": ("index copernicus",),
        "Google Scholar": ("google scholar", "google академ"),
        "Scopus": ("scopus",),
        "Web of Science": ("web of science",),
    }
    return [provider for provider, needles in providers.items() if any(needle in text for needle in needles)]


def extract_links(home: ParsedPage, website: str) -> list[dict[str, str]]:
    host = urlparse(website).netloc
    found: list[dict[str, str]] = [{"kind": "website", "label": "Rasmiy sayt", "url": website}]
    for label, url in home.links:
        lowered = f"{label} {url}".lower()
        if "submission" in lowered or "maqola" in lowered or "подать" in lowered:
            kind = "submission"
        elif "archive" in lowered or "/issue" in lowered:
            kind = "archive"
        elif "editor" in lowered or "tahrir" in lowered or "редкол" in lowered:
            kind = "editorial"
        elif "contact" in lowered or "aloqa" in lowered or "контакт" in lowered:
            kind = "contact"
        else:
            continue
        if urlparse(url).netloc and urlparse(url).netloc != host:
            continue
        found.append({"kind": kind, "label": label or kind.title(), "url": url})
    unique: dict[tuple[str, str], dict[str, str]] = {}
    for item in found:
        unique[(item["kind"], item["url"])] = item
    return list(unique.values())[:40]


def collect_profile(db: Session, journal: Journal) -> JournalProfile:
    if not journal.website or journal.website == "#":
        raise ValueError("Jurnalning rasmiy sayti ko‘rsatilmagan")
    pages = fetch_pages(journal.website)
    now = utcnow()
    home = pages.get("home") or next(iter(pages.values()))
    about = pages.get("aims") or pages.get("about")
    contact_candidates = list({
        page.url: page for page in (
            pages.get("contact_custom"),
            pages.get("contact"),
            pages.get("editorial_custom"),
            pages.get("about"),
            pages.get("home"),
        ) if page
    }.values())
    contact = max(
        contact_candidates,
        key=lambda page: bool(page.address) * 4 + len(page.emails) * 2 + len(PHONE_RE.findall(page.main_text)),
        default=None,
    )
    editorial = pages.get("editorial_custom") or pages.get("editorial")
    submissions = pages.get("submissions")
    current = pages.get("current")

    summary = best_summary(about) or best_summary(home)
    aims_scope = best_summary(about)
    address = (contact.address if contact else None) or None
    address_page = contact
    address_pages = {page.url: page for page in [editorial, contact, *pages.values()] if page}
    for page in address_pages.values():
        if not page:
            continue
        for paragraph in page.paragraphs:
            lowered = paragraph.lower()
            if any(needle in lowered for needle in ("почтовый адрес", "postal address", "manzil")):
                address = re.sub(r"^[^:]{0,80}:\s*", "", paragraph).strip()
                address_page = page
                break
        if address and any(token in address.lower() for token in ("tashkent", "ташкент", "uzbek", "ўзбекистон")):
            break
    latest_issue = None
    if current:
        headings = [item for item in current.headings if item.lower() not in {"current issue", "текущий выпуск", "joriy son"}]
        latest_issue = compact(headings[0] if headings else current.title, 300)

    profile = journal.profile or JournalProfile(journal=journal)
    profile.summary = summary
    profile.aims_scope = aims_scope
    address = clean_address(address)
    profile.address = compact(address, 1000)
    profile.latest_issue = latest_issue
    profile.source_url = about.url if about else home.url
    profile.fetched_at = now

    page_text = " ".join(page.main_text for page in pages.values()).lower()
    review_needles = ("peer review", "реценз", "taqriz")
    profile.peer_review = "Taqriz jarayoni jurnal saytida ko‘rsatilgan" if any(n in page_text for n in review_needles) else None
    frequency_match = re.search(r"(?:quarterly|monthly|annual|ежекварталь\w*|har chorak|yiliga)\D{0,30}", page_text, re.I)
    profile.publication_frequency = compact(frequency_match.group(0), 200) if frequency_match else None
    founded_match = re.search(r"(?:издается с|founded|asos solingan)\s+(\d{4})", page_text, re.I)
    if founded_match:
        journal.founded = int(founded_match.group(1))
    typed_issns = re.findall(r"\b(\d{4}-\d{3}[\dX])\s*\((online|print)\)", page_text, re.I)
    for value, kind in typed_issns:
        if kind.lower() == "online":
            journal.eissn = value
        elif kind.lower() == "print":
            journal.issn = value
    if not typed_issns:
        discovered_issns = list(dict.fromkeys(re.findall(r"\b\d{4}-\d{3}[\dX]\b", page_text, re.I)))
        if discovered_issns and not journal.issn:
            journal.issn = discovered_issns[0]
        if len(discovered_issns) > 1 and not journal.eissn:
            journal.eissn = discovered_issns[1]

    language_labels = " ".join(label.lower() for page in pages.values() for label, _ in page.links)
    detected_languages: list[str] = []
    for language, needles in {
        "O‘zbek": ("o'zbek", "o‘zbek", "ўзбек"),
        "Ingliz": ("english", "ingliz"),
        "Rus": ("русский", "russian", "rus tili"),
        "Qoraqalpoq": ("qaraqalpaq", "qoraqalpoq", "қарақалпоқ"),
    }.items():
        if any(needle in language_labels for needle in needles):
            detected_languages.append(language)
    if detected_languages:
        journal.languages = sorted({*journal.languages, *detected_languages})
        profile.submission_languages = detected_languages

    for model in (EditorialMember, JournalPolicy, JournalSection, JournalIndexingClaim, JournalLink):
        db.execute(delete(model).where(model.journal_id == journal.id))
    # Admin qo'lda kiritgan ma'lumot qayta yig'ishda yo'qolmasin: aloqa
    # yozuvlarining manbasi `admin:manual` bo'lganlari va `manual` belgili
    # provenance qatorlari saqlanadi.
    db.execute(
        delete(JournalContact).where(
            JournalContact.journal_id == journal.id,
            JournalContact.source_url != MANUAL_SOURCE,
        )
    )
    db.execute(
        delete(JournalProfileField).where(
            JournalProfileField.journal_id == journal.id,
            JournalProfileField.verification_status != MANUAL_STATUS,
        )
    )
    db.flush()
    # Qo'lda kiritilgani turgan bo'lsa, xuddi shu yozuvni qayta qo'shmaymiz —
    # (journal_id, kind, value) yagona bo'lishi kerak.
    kept_contacts = {
        (contact.kind, contact.value)
        for contact in db.scalars(
            select(JournalContact).where(JournalContact.journal_id == journal.id)
        )
    }

    contacts: list[JournalContact] = []
    if address:
        address_value = compact(address, 1000) or address
        if ("address", address_value) not in kept_contacts:
            contacts.append(JournalContact(journal=journal, kind="address", label="Manzil", value=address_value, source_url=address_page.url if address_page else home.url, fetched_at=now))
    seen_contacts: set[tuple[str, str]] = set(kept_contacts)
    for page in contact_candidates:
        for email in page.emails:
            key = ("email", email.lower())
            if key not in seen_contacts:
                contacts.append(JournalContact(journal=journal, kind="email", label="Email", value=email.lower(), source_url=page.url, fetched_at=now))
                seen_contacts.add(key)
        for phone in dict.fromkeys(
            balance_parens(clean_text(item)) for item in PHONE_RE.findall(page.main_text)
        ):
            if not is_valid_phone(phone):
                continue
            key = ("phone", phone)
            if key not in seen_contacts:
                contacts.append(JournalContact(journal=journal, kind="phone", label="Telefon", value=phone, source_url=page.url, fetched_at=now))
                seen_contacts.add(key)
    db.add_all(contacts)

    members = extract_editorial_members(editorial)
    db.add_all([EditorialMember(journal=journal, source_url=editorial.url, fetched_at=now, **member) for member in members] if editorial else [])

    policies: list[JournalPolicy] = []
    policy_pages = {
        "submissions": ("Mualliflar uchun talablar", submissions),
        "peer_review": ("Taqriz siyosati", pages.get("peer_review")),
        "publication_ethics": ("Nashr etikasi", pages.get("ethics")),
        "privacy": ("Maxfiylik bayonoti", pages.get("privacy")),
        "open_access": ("Ochiq kirish siyosati", pages.get("open_access")),
        "author_guidelines": ("Mualliflar uchun qoida", pages.get("authors")),
    }
    for policy_type, (title, page) in policy_pages.items():
        if not page:
            continue
        # Sahifada faqat menyu bo'lsa `prose` `None` qaytaradi — bo'sh
        # siyosat yozuvini saqlashdan ko'ra umuman saqlamagan ma'qul.
        content = prose(page.main_text, 5000)
        if not content:
            continue
        policies.append(JournalPolicy(journal=journal, policy_type=policy_type, title=title, content=content, url=page.url, source_url=page.url, fetched_at=now))
    db.add_all(policies)

    section_names: list[str] = []
    if submissions:
        for heading in submissions.headings:
            if 3 < len(heading) < 150 and heading not in section_names:
                section_names.append(heading)
    db.add_all([JournalSection(journal=journal, name=name, source_url=submissions.url, fetched_at=now) for name in section_names[:20]] if submissions else [])

    providers = extract_indexing_claims(pages)
    db.add_all([JournalIndexingClaim(journal=journal, provider=provider, status="claimed", source_url=home.url, fetched_at=now) for provider in providers])

    db.add_all([JournalLink(journal=journal, source_url=home.url, fetched_at=now, **item) for item in extract_links(home, journal.website)])

    provenance = {
        "summary": (summary, profile.source_url, 0.72),
        "address": (address, contact.url if contact else home.url, 0.90),
        "latest_issue": (latest_issue, current.url if current else home.url, 0.82),
        "contacts": ([item.value for item in contacts], contact.url if contact else home.url, 0.90),
        "editorial_members": ([item["name"] for item in members], editorial.url if editorial else home.url, 0.68),
        "indexing_claims": (providers, home.url, 0.55),
    }
    for field_name, (value, source_url, confidence) in provenance.items():
        if value:
            db.add(JournalProfileField(journal=journal, field_name=field_name, value=value, source_url=source_url, confidence=confidence, verification_status="collected", fetched_at=now))

    db.add(profile)
    # Ball bazadagi holatdan hisoblanadi (lokal o'zgaruvchilardan emas),
    # shunda qo'lda tahrirdan keyin ham xuddi shu funksiya ishlatiladi.
    db.flush()
    completeness.refresh(db, journal)
    db.commit()
    db.refresh(profile)
    return profile
