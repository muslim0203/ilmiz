"""Sahifadan yig'ilgan matnni tozalash qoidalari.

Bu funksiyalar `profile_collector` da tug'ilgan, lekin ular tozalash
qoidasi — yig'ish mexanikasi emas. Alohida turgani uchun `completeness`
va `journal_edit` ham ulardan foydalana oladi (ilgari `journal_edit`
`profile_collector` ga bog'langan edi, `completeness` esa bog'lansa
aylanma import chiqardi).
"""
from __future__ import annotations

import html
import re

def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(value)).strip()



PHONE_RE = re.compile(r"(?:\+?\d[\d ()\-]{7,}\d)")
# `PHONE_RE` shunchaki raqam-probel-qavs ketma-ketligini topadi, shuning uchun
# sana ("2024-07-08 04"), ISSN ("3093-8805 2025 5"), yillar ro‘yxati va sahifa
# raqamlari ham telefon bo‘lib yozilardi — 1 185 tadan 556 tasi shunday edi.
DATE_LIKE_RE = re.compile(r"\b(?:19|20)\d{2}[-/.]\d{1,2}[-/.]\d{1,2}\b")
ISSN_LIKE_RE = re.compile(r"^\d{4}-\d{3}[\dXx](?:\s.*)?$")


# Aloqa sahifasidan manzil olganda yonidagi matn ham qo'shilib ketadi:
# tahririyat a'zolari ro'yxati, `document.write(unescape(...))` bilan
# yashirilgan email, yoki butunlay boshqa sahifa (mualliflar uchun qoida,
# maxfiylik siyosati). Shu belgilardan keyingisi manzil emas.
ADDRESS_JUNK_RE = re.compile(
    r"(?i)document\.write|principal contact|support contact|"
    r"представитель редакции|представитель технической|"
    r"editorial representative|tahririyat vakili|"
    r"\bтелефон\b|\btel\.?:|\btelefon\b|\bphone\b"
)
# «Manzil:» dan keyin haqiqiy manzil turadi.
ADDRESS_MARKER_RE = re.compile(r"(?i)(?:tahririyat\s+)?manzil(?:i)?\s*:|адрес\s*:")
# Manzilda ko'cha/shahar so'zi bo'ladi. «manzil» so'zining o'zi yaramaydi —
# «elektron manzil», «IP-manzili» hamma joyda uchraydi.
PLACE_WORDS_RE = re.compile(
    r"(?i)ko[‘'ʻ`]?cha|kocha|shahri|shahar|tuman|viloyat|mavze|qo[‘'ʻ`]?rg|"
    r"\buy\b|-uy|xona|qavat|bino|"
    r"street|district|\bcity\b|building|\bstr\b|avenue|\broad\b|"
    r"к[ўу]часи|улиц|город|район|проспект|\bдом\b|шох"
)
# Raqamlangan band — qoida matni ("6. Maqolaning...", "1) sarlavha:").
NUMBERED_CLAUSE_RE = re.compile(r"^\s*\d+(?:\.\d+)*\s*[.)]\s")
MIN_ADDRESS_LENGTH = 15


def clean_address(value: str | None) -> str | None:
    """Manzil matnidan begona qismni kesadi, manzil bo'lmasa `None`.

    Qoida ataylab ehtiyotkor — shubhalisi saqlanadi. «Manzilga o'xshamasa
    tashla» degan qat'iy qoida haqiqiy manzillarni ham yeb qo'yardi:
    «114, Shota Rustaveli, Tashkent, Uzbekistan» da ko'cha so'zi yo'q,
    «г.Ташкент, М.Улугбекский район» da esa raqam yo'q.
    """
    if not value:
        return None
    cut = ADDRESS_JUNK_RE.search(value)
    head = value if cut is None else value[: cut.start()]
    marker = None
    for marker in ADDRESS_MARKER_RE.finditer(head):
        pass  # oxirgisi kerak
    if cut is None and marker is None:
        text = value
    else:
        source = head if marker is None else head[marker.end():]
        text = re.sub(r"\s{2,}", " ", source).strip().strip(" ,;–—-").strip()

    if len(text) < MIN_ADDRESS_LENGTH and not re.search(r"\d|@", text):
        return None
    if NUMBERED_CLAUSE_RE.match(text):
        return None
    placed = bool(re.search(r"\d", text)) and bool(PLACE_WORDS_RE.search(text))
    if len(text) > 100:
        # Uzun matn manzil tuzilishisiz — sahifadan tushgan boshqa matn.
        return text if placed else None
    return text if (re.search(r"\d|@", text) or PLACE_WORDS_RE.search(text)) else None


def balance_parens(value: str) -> str:
    """Juftlashmagan qavslarni olib tashlaydi.

    `PHONE_RE` raqamdan boshlanadi, shuning uchun `+998(71) 262-31-69` dan
    `+99871) 262-31-69` qolgan — bazada 127 ta shunday yozuv topilgan.
    Ochuvchi qavs qayerda turganini taxmin qilmaymiz: ortiqchasini olib
    tashlash raqamni buzmaydi.
    """
    depth = 0
    kept: list[str] = []
    for char in value:
        if char == "(":
            depth += 1
        elif char == ")":
            if depth == 0:
                continue
            depth -= 1
        kept.append(char)
    if depth:  # ochilgan, lekin yopilmagan
        remaining = depth
        result: list[str] = []
        for char in reversed(kept):
            if char == "(" and remaining:
                remaining -= 1
                continue
            result.append(char)
        kept = list(reversed(result))
    return re.sub(r"\s{2,}", " ", "".join(kept)).strip()


def is_valid_phone(value: str) -> bool:
    value = value.strip()
    digits = re.sub(r"\D", "", value)
    if not 7 <= len(digits) <= 15:
        return False
    if DATE_LIKE_RE.search(value) or ISSN_LIKE_RE.match(value):
        return False
    # "2021 2022 2023" yoki "1 2 3 4 5" — mustaqil sonlar ro‘yxati, telefon emas.
    # Telefon bo‘laklarida "+", qavs yoki tire bo‘ladi yoki bo‘lak 100 dan katta
    # va yil emas ("71 244 35 47" — haqiqiy raqam).
    parts = value.split()
    if len(parts) >= 3 and all(part.isdigit() for part in parts):
        def looks_like_plain_number(part: str) -> bool:
            number = int(part)
            return 1900 <= number <= 2100 or number <= 100
        if all(looks_like_plain_number(part) for part in parts):
            return False
    return True
BOILERPLATE_RE = re.compile(
    r"(?i)"
    r"\$\(function|\$\(document|\bvar\s+\w+\s*=|JSON\.parse|<script|"
    r"\.addClass\(|\.removeClass\(|"
    r"your browser does not support html5|"
    r"all rights reserved|copyright\s*©|©\s*\d{4}|"
    r"javascript[^.]{0,60}(disabled|enable|o.chir|yoqing|qo.llab)|"
    r"(disabled|enable)[^.]{0,60}javascript"
)
# Kesilgandan keyin faqat menyu qolsa, bu ham tavsif emas.
NAVIGATION_RE = re.compile(
    r"(?i)"
    r"search articles for\s+advanced filters|"
    r"размер шрифта|яркий контраст|клавиатурная навигация|"
    r"версия для слабовидящих|"
    r"sayt xaritasi|virtual qabulxona|"
    r"asosiy kontentga o.tish|асосий контентга ўтиш"
)
BREADCRUMB_RE = re.compile(r"^\s*(home|bosh sahifa|главная|асосий саҳифа)\s*/?\s*", re.I)
# Bundan qisqa matn tavsif emas — odatda sarlavhaning o'zi.
MIN_PROSE_LENGTH = 60


def strip_boilerplate(value: str) -> str:
    match = BOILERPLATE_RE.search(value)
    if match:
        value = value[: match.start()]
    return BREADCRUMB_RE.sub("", value).strip()


def compact(value: str | None, limit: int = 4000) -> str | None:
    if not value:
        return None
    value = strip_boilerplate(clean_text(value))
    return value[:limit] if value else None


def prose(value: str | None, limit: int = 4000) -> str | None:
    """`compact`, lekin natija tavsif bo'lolmasa `None` qaytaradi."""
    text = compact(value, limit)
    if not text or len(text) < MIN_PROSE_LENGTH or NAVIGATION_RE.search(text):
        return None
    return text


def best_summary(page: ParsedPage | None) -> str | None:
    if not page:
        return None
    useful = [p for p in page.paragraphs if len(p) >= 80]
    if useful:
        return prose(max(useful, key=len), 1800)
    return prose(page.main_text, 1800)

