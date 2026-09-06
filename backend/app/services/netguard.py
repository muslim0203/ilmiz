"""Tashqi URL'larni olishdan oldin SSRF tekshiruvi.

Jurnal sayti va OAI manzili tashqi ma'lumot: OAK reestri importidan yoki
admin PATCH orqali keladi. Ilgari ular filtrsiz olinardi — `http://127.0.0.1:8000/...`
yoki bulut metadata manzili (`169.254.169.254`) ko'rsatilsa, ilova o'zi
ichki xizmatga murojaat qilib javobni profil maydonlariga yozib qo'yardi.

Qoida: faqat `http`/`https`, host nomi bo'lishi shart, DNS orqali yechilgan
HAR BIR manzil ommaviy (`is_global`) bo'lishi kerak. Redirect'lar ham har
sakrashda shu tekshiruvdan o'tadi (`check_redirect`).

DNS rebinding (tekshiruvdan keyin javob o'zgarishi) bu yerda yopilmaydi —
ilova ichki tarmoqqa ega emas, xavf faqat loopback/metadata manzillari.
"""
from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlsplit

ALLOWED_SCHEMES = frozenset({"http", "https"})
# `localhost` DNS'siz ham loopback'ka yechiladi; `.local`/`.internal` ichki nomlar.
BLOCKED_HOST_SUFFIXES = (".localhost", ".local", ".internal", ".lan", ".home", ".corp")
BLOCKED_HOSTS = frozenset({"localhost", "metadata", "metadata.google.internal"})


class UnsafeURL(ValueError):
    """URL ichki yoki yopiq manzilga ishora qiladi."""


def _resolve(host: str, port: int | None) -> list[ipaddress.IPv4Address | ipaddress.IPv6Address]:
    try:
        infos = socket.getaddrinfo(host, port or 80, proto=socket.IPPROTO_TCP)
    except socket.gaierror as error:
        raise UnsafeURL(f"Host topilmadi: {host} ({error})") from error
    addresses = []
    for info in infos:
        raw = info[4][0]
        # IPv6 uchun `%scope` qo'shimchasi bo'lishi mumkin.
        addresses.append(ipaddress.ip_address(raw.split("%", 1)[0]))
    if not addresses:
        raise UnsafeURL(f"Host manzilga yechilmadi: {host}")
    return addresses


def assert_public_url(url: str, *, resolve: bool = True) -> str:
    """URL ommaviy internet manzili bo'lsa uni qaytaradi, aks holda `UnsafeURL`.

    `resolve=False` faqat sintaksis va aniq yopiq nomlarni tekshiradi (DNS'siz).
    """
    try:
        parsed = urlsplit(url.strip())
    except ValueError as error:
        raise UnsafeURL(f"URL o'qilmadi: {url!r}") from error
    if parsed.scheme.lower() not in ALLOWED_SCHEMES:
        raise UnsafeURL("Faqat http:// yoki https:// manzil qabul qilinadi")
    host = (parsed.hostname or "").strip().rstrip(".").lower()
    if not host:
        raise UnsafeURL("URL'da host yo'q")
    if parsed.username or parsed.password:
        raise UnsafeURL("URL'da foydalanuvchi nomi/parol bo'lmasin")
    if host in BLOCKED_HOSTS or host.endswith(BLOCKED_HOST_SUFFIXES):
        raise UnsafeURL(f"Ichki host nomi: {host}")
    try:
        port = parsed.port
    except ValueError as error:
        raise UnsafeURL("Port noto'g'ri") from error

    literal: ipaddress.IPv4Address | ipaddress.IPv6Address | None = None
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        literal = None
    if literal is not None:
        _assert_global(literal, host)
        return url.strip()
    if resolve:
        for address in _resolve(host, port):
            _assert_global(address, host)
    return url.strip()


def _assert_global(address: ipaddress.IPv4Address | ipaddress.IPv6Address, host: str) -> None:
    # IPv4-mapped IPv6 (`::ffff:127.0.0.1`) ni ichidagi IPv4 bo'yicha baholaymiz.
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
        address = address.ipv4_mapped
    if not address.is_global:
        raise UnsafeURL(f"{host} ichki/yopiq manzilga yechiladi ({address})")


def check_redirect(location: str) -> str:
    """Redirect manzili uchun ham xuddi shu qoida (httpx/urllib hook'lari uchun)."""
    return assert_public_url(location)
