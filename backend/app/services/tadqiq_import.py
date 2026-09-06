"""tadqiq.uz mahalliy OAK jurnallar katalogidan yetishmayotgan maydonlarni oladi.

Bizdagi OAK reestri importi jurnal nomi, nashriyot, shahar va fan sohalarini
beradi, lekin ISSN (493 tadan faqat 111 ta), rasmiy sayt, asos solingan yil,
chiqish davriyligi kabi maydonlar ko‘pincha bo‘sh qoladi. tadqiq.uz o‘sha
reestrni boyitilgan holda e’lon qiladi.

Siyosat:
- faqat bo‘sh maydonlar to‘ldiriladi, mavjud qiymat hech qachon almashtirilmaydi;
- har bir olingan qiymat manba URLi va vaqti bilan `journal_profile_fields` ga
  provenance sifatida yoziladi;
- moslashtirish ishonchi past bo‘lsa jurnal chetlab o‘tiladi va hisobotga
  tushadi — taxmin qilinmaydi.
"""
from __future__ import annotations

import json
import logging
import re
import time
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import HarvestSource, Journal, JournalProfile, JournalProfileField
from .ingest import ACTIVE_SOURCE_STATUSES

logger = logging.getLogger(__name__)

BASE_URL = "https://tadqiq.uz"
LISTING_PATH = "/mahalliy-oak-jurnallar"
USER_AGENT = "Mozilla/5.0 (compatible; IlmIzJournalProfiler/0.4; +public scholarly metadata index)"
REQUEST_DELAY_SECONDS = 1.0
MATCH_THRESHOLD = 0.80

SUBJECT_SLUGS = (
    "arxitektura", "biologiya-fanlari", "falsafa-fanlari", "farmatsevtika-fanlari",
    "filologiya-fanlari", "fizika-matematika-fanlari", "geografiya-fanlari",
    "geologiya-mineralogiya-fanlari", "harbiy-fanlar", "iqtisodiyot-fanlari",
    "islomshunoslik-fanlari", "kimyo-fanlari", "pedagogika-fanlari", "psixologiya-fanlari",
    "qishloq-xojaligi-fanlari", "sanatshunoslik-fanlari", "siyosiy-fanlar",
    "sotsiologiya-fanlari", "tarix-fanlari", "texnika-fanlari", "tibbiyot-fanlari",
    "veterinariya-fanlari", "yuridik-fanlar",
)

ISSN_RE = re.compile(r"^\d{4}-\d{3}[\dXx]$")
JSON_LD_RE = re.compile(r'<script type="application/ld\+json">(.*?)</script>', re.S)
DT_DD_RE = re.compile(r"<dt[^>]*>(.*?)</dt>\s*<dd[^>]*>(.*?)</dd>", re.S)
TEL_RE = re.compile(r'href="tel:([^"]+)"')
LABELLED_RE = re.compile(r">([^<>]{3,40})<!-- -->:</span>\s*(?:<!-- -->)?(.*?)</p>", re.S)
INDEXED_RE = re.compile(r"Indekslangan<!-- -->:</span>(.*?)</div>", re.S)
ABOUT_RE = re.compile(r"Jurnal haqida</h2>(.*?)</section>", re.S)
# Maʼlumot bo‘lmaganda sayt shablon matn yozadi — uni tavsif deb olmaymiz.
ABOUT_TEMPLATE_RE = re.compile(r"Oliy Attestatsiya Komissiyasi \(OAK\) tomonidan tasdiqlangan ilmiy jurnal")
# Bizning OAK importimiz ham har bir jurnalga shu bir xil matnni yozgan.
OAK_PLACEHOLDER_DESCRIPTION = "OAK rasmiy elektron reestridan import qilingan jurnal."
TAG_RE = re.compile(r"<[^>]+>")

# O‘zbek kirilchasini lotinga o‘tkazish — bizdagi nomlar ko‘pincha kirillcha,
# tadqiq.uz esa lotincha yozadi.
CYRILLIC_TO_LATIN = str.maketrans({
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "yo", "ж": "j",
    "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m", "н": "n", "о": "o",
    "п": "p", "р": "r", "с": "s", "т": "t", "у": "u", "ф": "f", "х": "x", "ц": "ts",
    "ч": "ch", "ш": "sh", "щ": "sh", "ъ": "", "ы": "i", "ь": "", "э": "e", "ю": "yu",
    "я": "ya", "ғ": "g", "қ": "q", "ҳ": "h", "ў": "o",
})
APOSTROPHES = "ʻʼ'‘’`"
# Bu so‘zlar deyarli har bir jurnal nomida uchraydi, shuning uchun o‘xshashlikni
# sun’iy oshiradi.
# Ruscha nomlar transliteratsiyadan keyin shu ko‘rinishga keladi. Ular deyarli
# har bir nomda uchraydi: "ЖУРНАЛ ПРАВОВЫХ ИССЛЕДОВАНИЙ" va "Журнал социальных
# исследований" ikkita umumiy token bo‘yicha mos kelib qolardi.
STOPWORDS = frozenset({
    "ilmiy", "jurnal", "jurnali", "zhurnal", "xalqaro", "international", "journal",
    "nashri", "elektron", "the", "and", "for", "of",
    "issledovaniy", "issledovaniya", "issledovaniyah", "innovatsii", "innovatsiya",
    "mejdunarodniy", "mejdunarodnaya", "nauchno", "nauchniy",
    "teoreticheskiy", "prakticheskiy", "seriya",
})


def normalize_name(value: str) -> str:
    value = unicodedata.normalize("NFKC", value or "").casefold()
    for mark in APOSTROPHES:
        value = value.replace(mark, "")
    value = value.translate(CYRILLIC_TO_LATIN)
    value = re.sub(r"\(.*?\)", " ", value)
    value = re.sub(r"[^a-z0-9\s]", " ", value)
    return " ".join(value.split())


def name_tokens(value: str) -> set[str]:
    return {word for word in normalize_name(value).split() if len(word) > 2 and word not in STOPWORDS}


MIN_SHARED_TOKENS = 2
MIN_JACCARD = 0.4


def containment(source: set[str], target: set[str]) -> float:
    """Qisqaroq nom uzunroq nomga to‘liq kirsa 1.0.

    Jaccard yolg‘iz yaramaydi: bizdagi "Ўзбекистон замини" ularning
    "Oʻzbekiston zamini ilmiy-amaliy va innovatsion jurnali" nomiga to‘liq
    kiradi, lekin Jaccard 0.5 ball berardi.

    Faqat containment ham yetarli emas. Bazamizda "Молия", "Психология" kabi
    bir so‘zli nomlar bor; ular boshqa jurnalning uzun nomida uchrab qolsa
    containment 1.0 chiqib, butunlay boshqa jurnalga bog‘lanardi. Shuning uchun
    kamida ikkita umumiy token va Jaccard pastki chegarasi talab qilinadi.
    """
    if not source or not target:
        return 0.0
    shared = source & target
    if len(shared) < MIN_SHARED_TOKENS:
        return 0.0
    if len(shared) / len(source | target) < MIN_JACCARD:
        return 0.0
    return len(shared) / min(len(source), len(target))


def raw_containment(source: set[str], target: set[str]) -> float:
    """Chegarasiz containment — faqat ISSNni tasdiqlash uchun."""
    if not source or not target:
        return 0.0
    return len(source & target) / min(len(source), len(target))


def names_agree(candidates: list[str], our_name: str) -> bool:
    """ISSN mosligini nom bilan tasdiqlaydi.

    ISSN faqat bizdagi qiymat to‘g‘ri bo‘lsagina ishonchli kalit. Seed’dagi
    demo jurnallarda ISSN qo‘lda yozilgan va bir nechtasi boshqa jurnalniki
    bo‘lib chiqdi — natijada butunlay boshqa jurnalga bog‘lanardi. Shuning
    uchun nom ham hech bo‘lmasa qisman mos kelishi shart.
    """
    ours = normalize_name(our_name)
    our_tokens = name_tokens(our_name)
    for candidate in candidates:
        if not candidate:
            continue
        theirs = normalize_name(candidate)
        if not theirs or not ours:
            continue
        if theirs == ours or theirs.startswith(ours) or ours.startswith(theirs):
            return True
        if raw_containment(name_tokens(candidate), our_tokens) >= 0.5:
            return True
    return False


@dataclass
class TadqiqJournal:
    slug: str
    name: str = ""
    alternate_name: str = ""
    issn: str = ""
    eissn: str = ""
    publisher: str = ""
    city: str = ""
    website: str = ""
    phone: str = ""
    language: str = ""
    frequency: str = ""
    founded: int | None = None
    editor_in_chief: str = ""
    peer_review: str = ""
    indexed_in: list[str] = field(default_factory=list)
    latest_issue: str = ""
    description: str = ""
    issn_conflict: str = ""

    @property
    def source_url(self) -> str:
        return f"{BASE_URL}{LISTING_PATH}/{self.slug}"


@dataclass
class MatchResult:
    record: TadqiqJournal
    journal_id: int | None
    journal_name: str
    method: str
    score: float


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", TAG_RE.sub(" ", value or "")).strip()


def parse_detail(slug: str, html_text: str) -> TadqiqJournal:
    """Detal sahifadan maydonlarni ajratadi.

    Asosiy manba — JSON-LD `Periodical` bloki; u nomni, kirillcha muqobil nomni,
    ISSN va rasmiy sayt havolasini ishonchli beradi. Qolgan maydonlar yon
    paneldagi `<dl>` dan olinadi.
    """
    record = TadqiqJournal(slug=slug)
    for block in JSON_LD_RE.findall(html_text):
        try:
            data = json.loads(block)
        except json.JSONDecodeError:
            continue
        if not isinstance(data, dict) or data.get("@type") != "Periodical":
            continue
        record.name = str(data.get("name") or "")
        alternate = data.get("alternateName") or ""
        record.alternate_name = alternate if isinstance(alternate, str) else ""
        issn = str(data.get("issn") or "").strip()
        record.issn = issn if ISSN_RE.match(issn) else ""
        publisher = data.get("publisher")
        if isinstance(publisher, dict):
            record.publisher = str(publisher.get("name") or "")
        location = data.get("locationCreated")
        if isinstance(location, dict):
            record.city = str(location.get("name") or "")
        same_as = data.get("sameAs")
        if isinstance(same_as, str) and same_as.startswith(("http://", "https://")):
            record.website = same_as
        break

    for raw_label, raw_value in DT_DD_RE.findall(html_text):
        label = _clean(raw_label).casefold()
        value = _clean(raw_value)
        # Sayt bo‘sh maydonlarni "Maʼlumot topilmadi" matni bilan ko‘rsatadi;
        # uni qiymat deb saqlab qo‘ymaslik kerak.
        if value in {"", "—", "-"} or "topilmadi" in value.casefold():
            continue
        if label == "issn" and not record.issn and ISSN_RE.match(value):
            record.issn = value
        elif label in {"e-issn", "eissn"} and ISSN_RE.match(value):
            record.eissn = value
        elif label.startswith("so") and label.endswith("son"):
            record.latest_issue = value
        elif label == "til":
            record.language = value
        elif label.startswith("chiqish"):
            record.frequency = value
        elif label.startswith("asos solingan"):
            year = re.search(r"(?:18|19|20)\d{2}", value)
            if year:
                record.founded = int(year.group(0))
        elif label == "shahar" and not record.city:
            record.city = value

    phone = TEL_RE.search(html_text)
    if phone:
        record.phone = phone.group(1).strip()

    for raw_label, raw_value in LABELLED_RE.findall(html_text):
        label = _clean(raw_label).casefold()
        value = _clean(raw_value)
        if not value or "topilmadi" in value.casefold():
            continue
        if label.startswith("bosh muharrir"):
            record.editor_in_chief = value
        elif label.startswith("taqriz"):
            record.peer_review = value

    about = ABOUT_RE.search(html_text)
    if about:
        text = _clean(about.group(1))
        if text and not ABOUT_TEMPLATE_RE.search(text):
            record.description = text

    indexed = INDEXED_RE.search(html_text)
    if indexed:
        record.indexed_in = [item for item in (_clean(part) for part in re.findall(r"<span[^>]*>(.*?)</span>", indexed.group(1))) if item]

    return record


def fetch_page(client: httpx.Client, path: str, cache_dir: Path | None) -> str:
    """Sahifani oladi; kesh berilgan bo‘lsa saytga qayta murojaat qilmaydi."""
    cached: Path | None = None
    if cache_dir is not None:
        name = re.sub(r"[^a-z0-9]+", "_", path.strip("/").casefold()) + ".html"
        cached = cache_dir / name
        if cached.exists() and cached.stat().st_size > 5000:
            return cached.read_text(encoding="utf-8")
    time.sleep(REQUEST_DELAY_SECONDS)
    response = client.get(BASE_URL + path)
    response.raise_for_status()
    if cached is not None:
        cached.parent.mkdir(parents=True, exist_ok=True)
        cached.write_text(response.text, encoding="utf-8")
    return response.text


def collect_slugs(client: httpx.Client, cache_dir: Path | None) -> list[str]:
    """Fan sohasi sahifalarini (sahifalash bilan) aylanib slug ro‘yxatini yig‘adi."""
    link_re = re.compile(r'href="' + re.escape(LISTING_PATH) + r'/([a-z0-9-]+)"')
    slugs: dict[str, None] = {}
    for subject in SUBJECT_SLUGS:
        page = 1
        while True:
            suffix = "" if page == 1 else f"?page={page}"
            html_text = fetch_page(client, f"{LISTING_PATH}/soha/{subject}{suffix}", cache_dir)
            found = [slug for slug in link_re.findall(html_text) if slug not in {"soha", "shahar"}]
            if not found:
                break
            for slug in found:
                slugs.setdefault(slug, None)
            if f"{subject}?page={page + 1}" not in html_text:
                break
            page += 1
    return list(slugs)


def match_records(db: Session, records: list[TadqiqJournal]) -> list[MatchResult]:
    """Har bir yozuvni bizdagi jurnalga bog‘laydi.

    Tartib: ISSN -> aniq nom -> tokenlar containment'i. Ball chegaradan past
    bo‘lsa `journal_id` None qoladi va yozuv qo‘llanmaydi.
    """
    rows = db.execute(select(Journal.id, Journal.name, Journal.issn, Journal.eissn)).all()
    by_issn: dict[str, tuple[int, str]] = {}
    by_name: dict[str, list[tuple[int, str]]] = {}
    token_index: list[tuple[int, str, set[str]]] = []
    for journal_id, name, issn, eissn in rows:
        for code in (issn, eissn):
            if code and ISSN_RE.match(code.strip()):
                by_issn.setdefault(code.strip(), (journal_id, name))
        by_name.setdefault(normalize_name(name), []).append((journal_id, name))
        token_index.append((journal_id, name, name_tokens(name)))

    results: list[MatchResult] = []
    for record in records:
        candidates = [item for item in (record.name, record.alternate_name) if item]
        if record.issn and record.issn in by_issn:
            journal_id, name = by_issn[record.issn]
            if names_agree(candidates, name):
                results.append(MatchResult(record, journal_id, name, "issn", 1.0))
                continue
            # ISSN mos, lekin nom butunlay boshqa — bizdagi ISSN xato bo‘lishi
            # mumkin. Ishonmaymiz va nom bo‘yicha izlashda davom etamiz.
            logger.warning(
                "ISSN %s mos keldi, lekin nomlar farq qiladi: %r <-> %r",
                record.issn, record.name, name,
            )
            record.issn_conflict = name
        exact = next(
            (by_name[key][0] for key in map(normalize_name, candidates) if len(by_name.get(key, [])) == 1),
            None,
        )
        if exact is not None:
            results.append(MatchResult(record, exact[0], exact[1], "aniq-nom", 1.0))
            continue
        best_id, best_name, best_score = None, "", 0.0
        for candidate in candidates:
            source = name_tokens(candidate)
            for journal_id, name, target in token_index:
                score = containment(source, target)
                if score > best_score:
                    best_id, best_name, best_score = journal_id, name, score
        if best_score >= MATCH_THRESHOLD:
            results.append(MatchResult(record, best_id, best_name, "oxshash-nom", best_score))
        else:
            results.append(MatchResult(record, None, best_name, "mos-yoq", best_score))
    return results


# Jurnal ustuni -> yozuvdagi maydon. Faqat shular to‘g‘ridan-to‘g‘ri yoziladi.
JOURNAL_FIELDS = (("issn", "issn"), ("eissn", "eissn"), ("website", "website"), ("founded", "founded"))
PROFILE_FIELDS = (
    ("publication_frequency", "frequency"),
    ("peer_review", "peer_review"),
    ("latest_issue", "latest_issue"),
)


def split_languages(value: str) -> list[str]:
    """"Oʻzbek, Rus, Ingliz" bitta satr bo‘lib keladi — ro‘yxatga ajratamiz."""
    return [part.strip() for part in re.split(r"[,;/]", value) if part.strip()]


def site_host(url: str) -> str:
    try:
        return (urlparse(url).hostname or "").casefold().removeprefix("www.")
    except ValueError:
        return ""


def journals_with_dead_sites(db: Session) -> set[int]:
    """Sayti ishlamayotgani isbotlangan jurnallar.

    OAI manbalari bor, lekin hech biri `healthy` emas. Bunday jurnalda bizdagi
    sayt manzili eskirgan bo‘lishi ehtimoli yuqori — `maturidijournal.uz`
    o‘lgan, haqiqiysi `maturidijournal.org` bo‘lgani kabi.
    """
    statuses: dict[int, set[str]] = {}
    for journal_id, status in db.execute(select(HarvestSource.journal_id, HarvestSource.status)):
        statuses.setdefault(journal_id, set()).add(status)
    return {journal_id for journal_id, values in statuses.items() if values and values.isdisjoint(ACTIVE_SOURCE_STATUSES)}


def _is_empty(value: object) -> bool:
    return value is None or (isinstance(value, str) and value.strip() in {"", "—", "-"})


def apply_match(
    db: Session,
    result: MatchResult,
    *,
    now: datetime,
    provenance_cache: dict[tuple[int, str], JournalProfileField] | None = None,
    replace_dead_site: bool = False,
) -> dict[str, str]:
    """Bo‘sh maydonlarni to‘ldiradi va provenance yozadi. Mavjud qiymat tegilmaydi."""
    journal = db.get(Journal, result.journal_id)
    if journal is None:
        return {}
    record = result.record
    if provenance_cache is None:
        provenance_cache = {}
    applied: dict[str, str] = {}

    for column, attribute in JOURNAL_FIELDS:
        value = getattr(record, attribute)
        if not value:
            continue
        current = getattr(journal, column)
        if _is_empty(current):
            setattr(journal, column, value)
            applied[column] = str(value)
        elif (
            column == "website"
            and replace_dead_site
            and site_host(str(current)) != site_host(str(value))
        ):
            # Bizdagi manzil ishlamayapti va host boshqa — eskirganini
            # almashtiramiz, eskisi provenance'da qoladi.
            journal.website = value
            applied["website (almashtirildi)"] = f"{current} -> {value}"

    # Bizdagi tavsif OAK importining shabloni bo‘lsa, u maʼlumot emas —
    # tadqiq.uz dagi haqiqiy tavsif bilan almashtiramiz.
    if record.description and (
        _is_empty(journal.description) or journal.description == OAK_PLACEHOLDER_DESCRIPTION
    ):
        journal.description = record.description
        applied["description"] = "tavsif"

    if any(getattr(record, attribute) for _, attribute in PROFILE_FIELDS) or record.language or record.description:
        profile = journal.profile
        if profile is None:
            profile = JournalProfile(journal=journal, source_url=record.source_url, fetched_at=now)
            db.add(profile)
        for column, attribute in PROFILE_FIELDS:
            value = getattr(record, attribute)
            if value and _is_empty(getattr(profile, column)):
                setattr(profile, column, value)
                applied[column] = value
        if record.description and _is_empty(profile.summary):
            profile.summary = record.description
            applied["summary"] = "tavsif"
        if record.language and not profile.submission_languages:
            profile.submission_languages = split_languages(record.language)
            applied["submission_languages"] = record.language

    # Provenance: qo‘llangan-qo‘llanmaganidan qat’i nazar hammasi saqlanadi.
    provenance = {
        "issn": record.issn,
        "eissn": record.eissn,
        "website": record.website,
        "latest_issue": record.latest_issue,
        "description": record.description,
        "founded": record.founded,
        "language": record.language,
        "publication_frequency": record.frequency,
        "phone": record.phone,
        "editor_in_chief": record.editor_in_chief,
        "peer_review": record.peer_review,
        "indexed_in": record.indexed_in,
    }
    for name, value in provenance.items():
        if not value:
            continue
        field_name = f"tadqiq:{name}"
        key = (journal.id, field_name)
        # Sessiya `autoflush=False` bilan ochilgan, shuning uchun `select` shu
        # tranzaksiyada qo‘shilgan qatorni ko‘rmaydi. tadqiq.uz da bir jurnal
        # ikki slug bilan uchraydi va bazamizda ham dublikatlar bor — keshsiz
        # ikkinchi INSERT unique constraintni buzardi.
        existing = provenance_cache.get(key)
        if existing is None:
            existing = db.scalar(
                select(JournalProfileField).where(
                    JournalProfileField.journal_id == journal.id,
                    JournalProfileField.field_name == field_name,
                )
            )
        if existing is None:
            existing = JournalProfileField(journal_id=journal.id, field_name=field_name)
            db.add(existing)
        provenance_cache[key] = existing
        existing.value = value
        existing.source_url = record.source_url
        existing.confidence = round(result.score, 2)
        existing.verification_status = "external"
        existing.fetched_at = now
    return applied


def import_tadqiq(
    db: Session,
    *,
    dry_run: bool = True,
    cache_dir: Path | None = None,
    limit: int | None = None,
    fix_dead_sites: bool = False,
) -> dict[str, object]:
    cache = Path(cache_dir) if cache_dir else None
    totals: dict[str, object] = {
        "yozuvlar": 0, "issn": 0, "aniq-nom": 0, "oxshash-nom": 0, "mos-yoq": 0,
        "yangilangan_jurnal": 0, "toldirilgan_maydon": {}, "rejim": "dry-run" if dry_run else "apply",
    }
    with httpx.Client(timeout=30, follow_redirects=True, headers={"User-Agent": USER_AGENT}) as client:
        slugs = collect_slugs(client, cache)
        if limit:
            slugs = slugs[:limit]
        records: list[TadqiqJournal] = []
        for slug in slugs:
            try:
                html_text = fetch_page(client, f"{LISTING_PATH}/{slug}", cache / "details" if cache else None)
            except httpx.HTTPError as error:
                logger.warning("tadqiq.uz sahifasi olinmadi: %s (%s)", slug, error)
                continue
            record = parse_detail(slug, html_text)
            if record.name:
                records.append(record)

    totals["yozuvlar"] = len(records)
    totals["issn-nom-zid"] = 0
    now = datetime.now(timezone.utc)
    filled: dict[str, int] = {}
    provenance_cache: dict[tuple[int, str], JournalProfileField] = {}
    dead_sites = journals_with_dead_sites(db) if fix_dead_sites else set()
    for result in match_records(db, records):
        totals[result.method] = int(totals[result.method]) + 1
        if result.journal_id is None:
            continue
        applied = apply_match(
            db,
            result,
            now=now,
            provenance_cache=provenance_cache,
            replace_dead_site=result.journal_id in dead_sites,
        )
        if applied:
            totals["yangilangan_jurnal"] = int(totals["yangilangan_jurnal"]) + 1
            for name in applied:
                filled[name] = filled.get(name, 0) + 1
    totals["toldirilgan_maydon"] = filled
    totals["issn-nom-zid"] = sum(1 for record in records if record.issn_conflict)

    if dry_run:
        db.rollback()
    else:
        db.commit()
        logger.info("tadqiq.uz importi: %s", totals)
    return totals
