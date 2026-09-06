#!/usr/bin/env python3
"""Small dependency-free OAI-PMH 2.0 discovery/harvesting CLI for the MVP.

Examples:
  python harvester/oai_harvester.py identify https://example.uz/index.php/journal/oai
  python harvester/oai_harvester.py harvest https://example.uz/oai --from-date 2026-08-01 --output data.jsonl
"""

from __future__ import annotations

import argparse
import hashlib
import http.client
import json
import re
import sys
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Iterator

OAI = "http://www.openarchives.org/OAI/2.0/"
DC = "http://purl.org/dc/elements/1.1/"
NS = {"oai": OAI, "dc": DC}
USER_AGENT = "IlmIz-OAI-Harvester/0.1 (+https://ilmiz.uz/about)"


# Qayta urinishga arziydigan HTTP kodlari.
RETRYABLE_HTTP = frozenset({429, 500, 502, 503, 504})
# Tarmoq darajasidagi vaqtinchalik xatolar. `URLError` va `ssl.SSLError`
# `OSError` ning, `IncompleteRead`/`RemoteDisconnected` esa
# `http.client.HTTPException` ning avlodi.
TRANSIENT_ERRORS = (OSError, TimeoutError, http.client.HTTPException)
# `badResumptionToken` dan keyin oxirgi datestamp'dan necha marta qayta
# boshlashga ruxsat beriladi.
MAX_TOKEN_RESTARTS = 2


class OAIError(RuntimeError):
    pass


@dataclass(slots=True)
class OAIRecord:
    identifier: str
    datestamp: str | None
    set_specs: list[str]
    deleted: bool
    metadata: dict[str, list[str]]
    metadata_hash: str | None
    raw_xml: str


def _text(element: ET.Element | None) -> str | None:
    if element is None or element.text is None:
        return None
    value = " ".join(element.text.split())
    return value or None


def _insecure_context() -> ssl.SSLContext:
    """Sertifikat tekshiruvisiz kontekst.

    O‘zbekistondagi bir qancha universitet saytlarida sertifikat muddati o‘tgan
    yoki zanjiri to‘liq emas. Bu ochiq metama’lumot bo‘lgani uchun tekshiruvni
    o‘chirish faqat aniq so‘ralganda (`verify_ssl=False`) qilinadi.
    """
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    return context


def _request(
    base_url: str,
    params: dict[str, str],
    *,
    timeout: int,
    retries: int = 3,
    verify_ssl: bool = True,
) -> bytes:
    separator = "&" if "?" in base_url else "?"
    url = f"{base_url}{separator}{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(
        url,
        headers={"Accept": "application/xml,text/xml", "Accept-Encoding": "identity", "User-Agent": USER_AGENT},
    )
    context = None if verify_ssl else _insecure_context()
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(request, timeout=timeout, context=context) as response:
                return response.read()
        except urllib.error.HTTPError as error:
            last_error = error
            retry_after = error.headers.get("Retry-After")
            # 500 ham ro‘yxatda: OJS'da u ko‘pincha vaqtinchalik (PHP xotira
            # limiti, baza ulanishi) va keyingi urinishda o‘tib ketadi.
            if error.code not in RETRYABLE_HTTP or attempt == retries - 1:
                break
            wait_seconds = int(retry_after) if retry_after and retry_after.isdigit() else 2 ** attempt
            time.sleep(min(wait_seconds, 30))
        except TRANSIENT_ERRORS as error:
            # `IncompleteRead` va `RemoteDisconnected` `URLError` emas — ular
            # ilgari ushlanmay 1 400 yozuvdan keyin butun run'ni yiqitgan.
            last_error = error
            if attempt == retries - 1:
                break
            time.sleep(2 ** attempt)
    raise OAIError(f"OAI request failed for {base_url}: {last_error}")


def _root(payload: bytes) -> ET.Element:
    try:
        root = ET.fromstring(payload)
    except ET.ParseError as error:
        # Ayrim eski OJS instanslari Dublin Core qiymatlarida nazorat belgisi
        # yoki escape qilinmagan '&' qaytaradi. Metadata yo‘qolmasligi uchun
        # faqat XML 1.0 da noqonuniy qismlarni yumshoq tuzatib qayta o‘qiymiz.
        repaired = payload.decode("utf-8", errors="replace")
        repaired = re.sub(r"[\x00-\x08\x0B\x0C\x0E-\x1F]", "", repaired)
        repaired = re.sub(r"&(?!#\d+;|#x[0-9a-fA-F]+;|[A-Za-z][A-Za-z0-9]+;)", "&amp;", repaired)
        try:
            root = ET.fromstring(repaired)
        except ET.ParseError:
            raise OAIError(f"Invalid XML response: {error}") from error
    errors = root.findall("oai:error", NS)
    if errors:
        rendered = "; ".join(f"{item.get('code')}: {_text(item)}" for item in errors)
        raise OAIError(rendered)
    return root


def identify(base_url: str, *, timeout: int = 30, verify_ssl: bool = True) -> dict[str, object]:
    root = _root(_request(base_url, {"verb": "Identify"}, timeout=timeout, verify_ssl=verify_ssl))
    node = root.find("oai:Identify", NS)
    if node is None:
        raise OAIError("Identify element is missing")
    return {
        "base_url": base_url,
        "repository_name": _text(node.find("oai:repositoryName", NS)),
        "protocol_version": _text(node.find("oai:protocolVersion", NS)),
        "admin_emails": [_text(item) for item in node.findall("oai:adminEmail", NS) if _text(item)],
        "earliest_datestamp": _text(node.find("oai:earliestDatestamp", NS)),
        "deleted_record": _text(node.find("oai:deletedRecord", NS)),
        "granularity": _text(node.find("oai:granularity", NS)),
        "compression": [_text(item) for item in node.findall("oai:compression", NS) if _text(item)],
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }


def list_metadata_formats(base_url: str, *, timeout: int = 30, verify_ssl: bool = True) -> list[dict[str, str | None]]:
    root = _root(_request(base_url, {"verb": "ListMetadataFormats"}, timeout=timeout, verify_ssl=verify_ssl))
    return [
        {
            "prefix": _text(node.find("oai:metadataPrefix", NS)),
            "schema": _text(node.find("oai:schema", NS)),
            "namespace": _text(node.find("oai:metadataNamespace", NS)),
        }
        for node in root.findall("oai:ListMetadataFormats/oai:metadataFormat", NS)
    ]


def _parse_record(record: ET.Element) -> OAIRecord:
    header = record.find("oai:header", NS)
    if header is None:
        raise OAIError("Record has no header")
    identifier = _text(header.find("oai:identifier", NS))
    if not identifier:
        raise OAIError("Record has no OAI identifier")
    deleted = header.get("status") == "deleted"
    metadata: dict[str, list[str]] = {}
    metadata_node = record.find("oai:metadata", NS)
    if metadata_node is not None:
        dc_node = metadata_node.find("oai_dc:dc", {"oai_dc": "http://www.openarchives.org/OAI/2.0/oai_dc/"})
        if dc_node is not None:
            for child in list(dc_node):
                key = child.tag.rsplit("}", 1)[-1]
                value = _text(child)
                if value:
                    metadata.setdefault(key, []).append(value)
    raw_xml = ET.tostring(record, encoding="unicode")
    digest = hashlib.sha256(raw_xml.encode("utf-8")).hexdigest() if not deleted else None
    return OAIRecord(
        identifier=identifier,
        datestamp=_text(header.find("oai:datestamp", NS)),
        set_specs=[value for item in header.findall("oai:setSpec", NS) if (value := _text(item))],
        deleted=deleted,
        metadata=metadata,
        metadata_hash=digest,
        raw_xml=raw_xml,
    )


def metadata_from_xml(raw_xml: str) -> dict[str, list[str]]:
    """Saqlangan record XML'idan oai_dc metama'lumotini qayta tiklaydi.

    `raw_xml` — `ET.tostring(record)` natijasi, ya'ni to'liq record elementi,
    shuning uchun `_parse_record` aynan o'sha dictni qaytaradi. Shu sabab
    `source_records.raw_metadata` ni alohida saqlash shart emas.
    """
    return _parse_record(ET.fromstring(raw_xml)).metadata


def harvest(
    base_url: str,
    *,
    metadata_prefix: str = "oai_dc",
    from_date: str | None = None,
    until_date: str | None = None,
    set_spec: str | None = None,
    timeout: int = 30,
    page_limit: int | None = None,
    verify_ssl: bool = True,
) -> Iterator[OAIRecord]:
    base_params = {"verb": "ListRecords", "metadataPrefix": metadata_prefix}
    if from_date:
        base_params["from"] = from_date
    if until_date:
        base_params["until"] = until_date
    if set_spec:
        base_params["set"] = set_spec
    params = dict(base_params)

    page = 0
    restarts = 0
    last_datestamp: str | None = None
    while True:
        try:
            root = _root(_request(base_url, params, timeout=timeout, verify_ssl=verify_ssl))
        except OAIError as error:
            if str(error).startswith("noRecordsMatch:"):
                return
            # Token muddati tugagan (sekin harvest, server qayta ishga
            # tushgan). Oqimni boshidan emas, oxirgi ko‘rilgan kundan davom
            # ettiramiz — takror yozuvlar `metadata_hash` bilan filtrlanadi.
            if (
                str(error).startswith("badResumptionToken")
                and "resumptionToken" in params
                and last_datestamp
                and restarts < MAX_TOKEN_RESTARTS
            ):
                restarts += 1
                params = dict(base_params)
                params["from"] = _restart_from(last_datestamp, base_params.get("from"))
                continue
            raise
        list_records = root.find("oai:ListRecords", NS)
        if list_records is None:
            raise OAIError("ListRecords element is missing")
        for record in list_records.findall("oai:record", NS):
            parsed = _parse_record(record)
            if parsed.datestamp:
                last_datestamp = parsed.datestamp
            yield parsed
        page += 1
        token = _text(list_records.find("oai:resumptionToken", NS))
        if not token or (page_limit is not None and page >= page_limit):
            break
        params = {"verb": "ListRecords", "resumptionToken": token}


def _restart_from(last_datestamp: str, original_from: str | None) -> str:
    """Qayta boshlash uchun `from` qiymati.

    Kun aniqligida (`YYYY-MM-DD`) beriladi, chunki har ikki granularity'dagi
    repozitoriy ham uni qabul qiladi. Asl `from` dan orqaga ketmaydi.
    """
    day = last_datestamp[:10]
    if original_from and original_from[:10] > day:
        return original_from
    return day


def write_jsonl(records: Iterable[OAIRecord], output: Path | None) -> int:
    target = output.open("w", encoding="utf-8") if output else sys.stdout
    count = 0
    try:
        for record in records:
            target.write(json.dumps(asdict(record), ensure_ascii=False) + "\n")
            count += 1
    finally:
        if output:
            target.close()
    return count


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="IlmIz OAI-PMH 2.0 harvester")
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name in ("identify", "formats"):
        command = subparsers.add_parser(name)
        command.add_argument("base_url")
        command.add_argument("--timeout", type=int, default=30)
    harvest_parser = subparsers.add_parser("harvest")
    harvest_parser.add_argument("base_url")
    harvest_parser.add_argument("--metadata-prefix", default="oai_dc")
    harvest_parser.add_argument("--from-date")
    harvest_parser.add_argument("--until-date")
    harvest_parser.add_argument("--set-spec")
    harvest_parser.add_argument("--page-limit", type=int)
    harvest_parser.add_argument("--timeout", type=int, default=30)
    harvest_parser.add_argument("--output", type=Path)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        if args.command == "identify":
            print(json.dumps(identify(args.base_url, timeout=args.timeout), ensure_ascii=False, indent=2))
        elif args.command == "formats":
            print(json.dumps(list_metadata_formats(args.base_url, timeout=args.timeout), ensure_ascii=False, indent=2))
        else:
            records = harvest(
                args.base_url,
                metadata_prefix=args.metadata_prefix,
                from_date=args.from_date,
                until_date=args.until_date,
                set_spec=args.set_spec,
                timeout=args.timeout,
                page_limit=args.page_limit,
            )
            count = write_jsonl(records, args.output)
            print(f"Harvest complete: {count} records", file=sys.stderr)
        return 0
    except OAIError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
