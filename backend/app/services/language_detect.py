"""Maqola tilini matnning o'zidan aniqlash.

OAI-PMH `dc:language` ga ko'p jurnallar maqolaning tilini emas, jurnalning
tillar ro'yxatini yoki birinchisini yozadi. Natijada prod'da 138 ming
sahifadan ~53 mingtasida `<html lang>` noto'g'ri edi: inglizcha sarlavha
`uz`, o'zbekcha lotin sarlavha `ru` va hokazo. Til sahifa uchun muhim
signal (`lang`, `og:locale`, `inLanguage`, `citation_language`), shuning
uchun u sarlavha va annotatsiyadan aniqlanadi; aniq bo'lmasa — metadata.

Faqat uch til ajratiladi (bazadagi matnlarning deyarli hammasi): o'zbek
(lotin va kirill), rus, ingliz.
"""
from __future__ import annotations

import re

from .search_text import normalize

DEFAULT_LANG = "uz"
# Metadata'dagi til nomi → BCP 47 kodi (ilgari `seo.py` da edi).
LANGUAGE_CODES = {
    "o‘zbek": "uz", "o'zbek": "uz", "ozbek": "uz", "uz": "uz", "uz_latn": "uz-Latn",
    "uz_cyrl": "uz-Cyrl", "rus": "ru", "ru": "ru", "ingliz": "en", "en": "en",
    "kaa": "kaa", "qoraqalpoq": "kaa", "kaz": "kk", "qozoq": "kk", "ara": "ar",
    "arab": "ar", "tojik": "tg", "turk": "tr", "nemis": "de", "fransuz": "fr",
}
# Qoraqalpoq va qozoq lotin/kirill harflari. Bu tillarni aniqlagich ajratmaydi —
# metadata shunday desa va matnda shu harflar bo'lsa, metadata saqlanadi.
_TURKIC_EXTRA = re.compile(r"[әөүңіǵíńóúáǴÍŃÓÚÁ]")


def language_code(value: str | None) -> str:
    return LANGUAGE_CODES.get(normalize(value), DEFAULT_LANG)


_CYRILLIC = re.compile(r"[а-яёўқғҳәөүңі]", re.I)
_LATIN = re.compile(r"[a-z]", re.I)
_UZ_CYRILLIC = re.compile(r"[ўқғҳ]", re.I)
_RU_ONLY = re.compile(r"[ыщ]", re.I)
_TOKEN = re.compile(r"[a-zʻʼ'‘’`]+", re.I)

_EN_WORDS = frozenset(
    "the of and in for with on to an is are by from as its this that these their between based study "
    "analysis effect role using use development system method methods problems features impact through "
    "towards among within into about new modern approach approaches assessment evaluation education learning "
    "teaching students children treatment patients case research english language".split()
)
_UZ_WORDS = frozenset(
    "va bilan uchun haqida orqali asosida hamda yoki ham bu ushbu qilish etish tahlili tadqiq "
    "rivojlantirish takomillashtirish xususiyatlari ahamiyati masalalari yo'llari usullari".split()
)
# "-lar" ataylab yo'q: inglizcha "molecular", "cardiovascular" ham shunday tugaydi.
_UZ_SUFFIXES = (
    "ning", "larni", "lari", "larning", "larda", "lardan", "larga", "ligi", "lik", "dagi", "ida",
    "ishning", "ishda", "ish", "lash", "ik", "iy", "li",
)
_UZ_APOSTROPHE = re.compile(r"\b(?:o|g)[ʻʼ'‘’`]", re.I)


def _latin_language(text: str) -> str | None:
    tokens = [token.casefold().replace("‘", "'").replace("ʻ", "'").replace("’", "'") for token in _TOKEN.findall(text)]
    if not tokens:
        return None
    lowered = text.casefold()
    en = sum(token in _EN_WORDS for token in tokens)
    uz = sum(token in _UZ_WORDS for token in tokens)
    uz += sum(1 for token in tokens if len(token) > 5 and token.endswith(_UZ_SUFFIXES))
    uz += 2 * len(_UZ_APOSTROPHE.findall(text))
    # O'zbek lotin alifbosida "w" va yakka "c" yo'q; "q" va "x" esa inglizchada
    # kam uchraydi — qisqa sarlavhada ham ishonchli belgi.
    en += len(re.findall(r"w|c(?!h)|\bth|tion\b", lowered)) * 0.5
    uz += len(re.findall(r"q|x", lowered)) * 0.5
    if en >= 2 and en > uz * 1.5:
        return "en"
    if uz >= 2 and uz > en * 1.5:
        return "uz"
    return None


def _guess(text: str) -> str | None:
    cyrillic = len(_CYRILLIC.findall(text))
    latin = len(_LATIN.findall(text))
    if cyrillic >= 10 and cyrillic > latin * 2:
        uz_marks = len(_UZ_CYRILLIC.findall(text))
        ru_marks = len(_RU_ONLY.findall(text))
        if uz_marks and uz_marks >= ru_marks:
            return "uz"
        return "ru" if ru_marks or not uz_marks else None
    if latin >= 10 and latin > cyrillic * 2:
        return _latin_language(text)
    return None


def detect_language(title: str | None, abstract: str | None = None) -> str | None:
    """`uz`, `ru`, `en` yoki `None` (ishonchli aniqlab bo'lmadi)."""
    found = _guess(title or "")
    if found:
        return found
    return _guess(f"{title or ''} {(abstract or '')[:600]}")


def effective_language(title: str | None, abstract: str | None, declared_code: str) -> str:
    """Sahifa tili: matndan aniqlangani, aniqlanmasa — metadata (`declared_code`).

    Metadata matn bilan bir oilada bo'lsa (masalan `uz-Latn` va `uz`) metadata
    afzal — u aniqroq ko'rinish beradi.
    """
    detected = detect_language(title, abstract)
    if detected is None or declared_code.split("-")[0] == detected:
        return declared_code
    if declared_code in ("kaa", "kk"):
        # Qoraqalpoq lotinida ham "w", "c" bor — inglizcha deb adashadi.
        # Faqat matn aniq ruscha bo'lsa (o'ziga xos harfsiz) almashtiramiz.
        if detected != "ru" or _TURKIC_EXTRA.search(f"{title or ''} {(abstract or '')[:600]}"):
            return declared_code
    return detected


def article_language(article) -> str:
    """Maqola sahifasining tili (`lang`, `inLanguage`, GOST bet belgisi uchun)."""
    return effective_language(
        getattr(article, "title", None), getattr(article, "abstract", None), language_code(getattr(article, "language", None))
    )


LANGUAGE_NAMES = {"uz": "O‘zbek", "ru": "Rus", "en": "Ingliz"}
