"""ROR (Research Organization Registry) — ish joyini tashkilot identifikatoriga bog'lash.

Nega kerak: "Ish joyi" erkin matn bo'lsa, bitta universitet o'nlab xil
yoziladi ("TDU", "Toshkent davlat universiteti", "NUUz"...). ROR ID esa
barqaror va Crossref/ORCID/OpenAlex bilan bir xil identifikator.

So'rovlar brauzerdan emas, server orqali ketadi:

- ROR 2026-yil 3-choragidan client ID'siz so'rovlarga 5 daqiqada 50 ta
  limit qo'yadi. `ROR_CLIENT_ID` shu yerda saqlanadi va natijalar
  keshlanadi, ya'ni bir xil qidiruv qayta yuborilmaydi.
- Saqlashda ROR ID server tomonida qayta tekshiriladi va tashkilot nomi
  ROR'dan olinadi — "tasdiqlangan" belgisi foydalanuvchi yuborgan matnga
  emas, registrga tayanadi.
"""
from __future__ import annotations

import os
import re
import threading
import time
from typing import Any

import httpx

API = "https://api.ror.org/v2/organizations"
USER_AGENT = "IlmIz/0.4 (https://github.com/muslim0203/ilmiz; mailto:journalmaturidi@gmail.com)"
TIMEOUT = 8
MIN_QUERY_LENGTH = 3
MAX_QUERY_LENGTH = 120
MAX_RESULTS = 8
CACHE_TTL = 24 * 3600
CACHE_SIZE = 500

# ROR ID: `0` + 6 ta belgi (Crockford base32, `i l o u` yo'q) + 2 raqamli nazorat.
ROR_ID_RE = re.compile(r"^0[a-hj-km-np-tv-z0-9]{6}[0-9]{2}$")

_cache: dict[str, tuple[float, Any]] = {}
_cache_lock = threading.Lock()


class RorUnavailable(RuntimeError):
    """ROR javob bermadi yoki limitga yetildi."""


def normalise_id(value: str | None) -> str | None:
    """`https://ror.org/05a28rw58` yoki `05a28rw58` -> `05a28rw58`; yaroqsizi `None`."""
    value = (value or "").strip().lower()
    for prefix in ("https://ror.org/", "http://ror.org/", "ror.org/"):
        if value.startswith(prefix):
            value = value[len(prefix):]
            break
    return value if ROR_ID_RE.match(value) else None


def _cached(key: str) -> Any | None:
    with _cache_lock:
        entry = _cache.get(key)
        if entry is None:
            return None
        if entry[0] < time.monotonic():
            _cache.pop(key, None)
            return None
        return entry[1]


def _remember(key: str, value: Any) -> None:
    with _cache_lock:
        if len(_cache) >= CACHE_SIZE:
            # Eng eskisini chiqaramiz — dict qo'shilish tartibini saqlaydi.
            _cache.pop(next(iter(_cache)))
        _cache[key] = (time.monotonic() + CACHE_TTL, value)


def clear_cache() -> None:
    with _cache_lock:
        _cache.clear()


def _headers() -> dict[str, str]:
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    client_id = os.getenv("ROR_CLIENT_ID", "").strip()
    if client_id:
        headers["Client-Id"] = client_id
    return headers


def _get(url: str, params: dict[str, str] | None = None) -> httpx.Response:
    try:
        with httpx.Client(timeout=TIMEOUT, headers=_headers()) as client:
            response = client.get(url, params=params)
    except httpx.HTTPError as error:
        raise RorUnavailable(str(error)) from error
    if response.status_code == 429 or response.status_code >= 500:
        raise RorUnavailable(f"ROR {response.status_code}")
    return response


def organization(record: dict[str, Any]) -> dict[str, Any] | None:
    """ROR v2 yozuvini frontend uchun ixcham ko'rinishga keltiradi."""
    ror_id = normalise_id(str(record.get("id") or ""))
    names = record.get("names") or []
    display = next((n.get("value") for n in names if "ror_display" in (n.get("types") or [])), None)
    if not ror_id or not display:
        return None
    # O'zbekcha nom bo'lsa ro'yxatda qo'shimcha ko'rsatiladi — foydalanuvchi
    # universitetini ko'pincha o'zbekcha nomi bilan taniydi.
    local = next(
        (
            n.get("value")
            for n in names
            if n.get("lang") == "uz" and "label" in (n.get("types") or []) and n.get("value") != display
        ),
        None,
    )
    acronym = next((n.get("value") for n in names if "acronym" in (n.get("types") or [])), None)
    location = ((record.get("locations") or [{}])[0] or {}).get("geonames_details") or {}
    return {
        "id": ror_id,
        "name": display,
        "localName": local,
        "acronym": acronym,
        "city": location.get("name"),
        "country": location.get("country_name"),
        "countryCode": location.get("country_code"),
    }


def search(query: str) -> list[dict[str, Any]]:
    """Nom bo'yicha faol tashkilotlarni qidiradi (ROR `query` parametri)."""
    query = " ".join((query or "").split())[:MAX_QUERY_LENGTH]
    if len(query) < MIN_QUERY_LENGTH:
        return []
    key = f"search:{query.casefold()}"
    cached = _cached(key)
    if cached is not None:
        return cached
    response = _get(API, params={"query": query})
    if response.status_code != 200:
        raise RorUnavailable(f"ROR {response.status_code}")
    results = [
        item
        for item in map(organization, response.json().get("items") or [])
        if item is not None
    ][:MAX_RESULTS]
    _remember(key, results)
    for item in results:
        # Tanlangan tashkilot saqlanganda qayta so'rov ketmasin.
        _remember(f"org:{item['id']}", item)
    return results


def lookup(ror_id: str) -> dict[str, Any] | None:
    """ROR ID bo'yicha tashkilot; registrda yo'q bo'lsa `None`."""
    ror_id = normalise_id(ror_id) or ""
    if not ror_id:
        return None
    key = f"org:{ror_id}"
    cached = _cached(key)
    if cached is not None:
        return cached
    response = _get(f"{API}/{ror_id}")
    if response.status_code in (400, 404):
        return None
    if response.status_code != 200:
        raise RorUnavailable(f"ROR {response.status_code}")
    result = organization(response.json())
    if result is not None:
        _remember(key, result)
    return result
