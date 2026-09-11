"""ORCID yozuvidan joriy ish joyini olish.

ORCID bilan kirganda token `/authenticate` scope'ida keladi va u public API'dan
o'qishga ham yaraydi (`/read-public` shu scope ichida). Shuning uchun qo'shimcha
ruxsat so'ralmaydi — faqat foydalanuvchi ORCID'da ochiq qilgan ish joylari
o'qiladi.

Tanlash qoidasi: faqat tugamagan (`end-date` yo'q) ish joylari; ular ichida eng
keyin boshlangani, teng bo'lsa ROR bilan bog'langani. ROR ID bo'lsa nom
registrdan olinadi — profil oynasida qo'lda tanlangani bilan bir xil qoida.
Hech bir xato kirishni to'xtatmaydi: ish joyi shunchaki to'ldirilmaydi.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

import httpx

from . import ror as ror_service

logger = logging.getLogger(__name__)

TIMEOUT = 10


@dataclass(frozen=True)
class Affiliation:
    name: str
    ror_id: str | None = None


def public_api_base() -> str:
    """`orcid.org` -> `pub.orcid.org`, `sandbox.orcid.org` -> `pub.sandbox.orcid.org`."""
    base = urlsplit(os.getenv("ORCID_BASE_URL", "").strip() or "https://orcid.org")
    return f"{base.scheme or 'https'}://pub.{base.netloc}/v3.0"


def _date_key(value: dict[str, Any] | None) -> tuple[int, int, int]:
    def part(name: str) -> int:
        try:
            return int(((value or {}).get(name) or {}).get("value") or 0)
        except (TypeError, ValueError, AttributeError):
            return 0

    return part("year"), part("month"), part("day")


def current_employment(payload: dict[str, Any]) -> Affiliation | None:
    """`/employments` javobidan joriy ish joyini tanlaydi."""
    candidates: list[tuple[tuple[int, int, int], bool, Affiliation]] = []
    for group in payload.get("affiliation-group") or []:
        for summary in group.get("summaries") or []:
            item = summary.get("employment-summary") or {}
            if item.get("end-date"):
                continue
            organization = item.get("organization") or {}
            name = " ".join(str(organization.get("name") or "").split())
            if not name:
                continue
            disambiguated = organization.get("disambiguated-organization") or {}
            ror_id = None
            if str(disambiguated.get("disambiguation-source") or "").upper() == "ROR":
                ror_id = ror_service.normalise_id(
                    str(disambiguated.get("disambiguated-organization-identifier") or "")
                )
            candidates.append((_date_key(item.get("start-date")), ror_id is not None, Affiliation(name[:300], ror_id)))
    if not candidates:
        return None
    return max(candidates, key=lambda entry: (entry[0], entry[1]))[2]


def fetch_current(client: httpx.Client, orcid: str, access_token: str) -> Affiliation | None:
    """Kirish paytida chaqiriladi; hech qachon xato ko'tarmaydi."""
    headers = {"Accept": "application/json"}
    if access_token:
        headers["Authorization"] = f"Bearer {access_token}"
    try:
        response = client.get(f"{public_api_base()}/{orcid}/employments", headers=headers, timeout=TIMEOUT)
        if response.status_code != 200:
            logger.warning("ORCID ish joylari olinmadi: HTTP %s", response.status_code)
            return None
        found = current_employment(response.json())
    except Exception as error:  # noqa: BLE001 - ish joyi uchun kirish yiqilmasin
        logger.warning("ORCID ish joylari olinmadi: %s", error)
        return None
    if found is None or found.ror_id is None:
        return found
    try:
        organization = ror_service.lookup(found.ror_id)
    except ror_service.RorUnavailable:
        organization = None
    if organization is None:
        # Registr tasdiqlamaguncha bog'lamaymiz; nom ORCID'dagicha qoladi.
        return Affiliation(found.name)
    return Affiliation(organization["name"][:300], found.ror_id)
