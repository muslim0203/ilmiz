import http.client
import io
import unittest
import urllib.error
import xml.etree.ElementTree as ET
from unittest import mock

from harvester.oai_harvester import (
    OAIError,
    OAIRecord,
    _parse_record,
    _request,
    _restart_from,
    _root,
    harvest,
    metadata_from_xml,
)
from backend.app.services.ingest import _landing_url, _pdf_url, _publication_date


SAMPLE = """
<record xmlns="http://www.openarchives.org/OAI/2.0/"
        xmlns:oai_dc="http://www.openarchives.org/OAI/2.0/oai_dc/"
        xmlns:dc="http://purl.org/dc/elements/1.1/">
  <header>
    <identifier>oai:example.uz:article/42</identifier>
    <datestamp>2026-08-26</datestamp>
    <setSpec>journal:demo</setSpec>
  </header>
  <metadata>
    <oai_dc:dc>
      <dc:title>Namuna maqola</dc:title>
      <dc:creator>Ali Valiyev</dc:creator>
      <dc:creator>Malika Karimova</dc:creator>
      <dc:identifier>https://example.uz/article/42</dc:identifier>
    </oai_dc:dc>
  </metadata>
</record>
"""


class RecordParsingTest(unittest.TestCase):
    def test_repairs_unescaped_ampersand(self) -> None:
        root = _root(b'<OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/"><x>A &amp; B & C</x></OAI-PMH>')
        self.assertEqual(root[0].text, "A & B & C")

    def test_extracts_article_links_and_date(self) -> None:
        metadata = {
            "identifier": ["https://example.uz/article/42", "https://example.uz/article/download/42/7"],
            "date": ["2026-05-01"],
        }
        self.assertEqual(_landing_url(metadata), "https://example.uz/article/42")
        self.assertEqual(_pdf_url(metadata), "https://example.uz/article/download/42/7")
        self.assertEqual(_publication_date(metadata), "2026-05-01")

    def test_parses_oai_dc_record(self) -> None:
        record = _parse_record(ET.fromstring(SAMPLE))
        self.assertIsInstance(record, OAIRecord)
        self.assertEqual(record.identifier, "oai:example.uz:article/42")
        self.assertEqual(record.datestamp, "2026-08-26")
        self.assertEqual(record.set_specs, ["journal:demo"])
        self.assertFalse(record.deleted)
        self.assertEqual(record.metadata["title"], ["Namuna maqola"])
        self.assertEqual(record.metadata["creator"], ["Ali Valiyev", "Malika Karimova"])

    def test_parses_deleted_record(self) -> None:
        deleted = SAMPLE.replace("<header>", '<header status="deleted">').split("<metadata>")[0] + "</record>"
        record = _parse_record(ET.fromstring(deleted))
        self.assertTrue(record.deleted)
        self.assertEqual(record.metadata, {})
        self.assertIsNone(record.metadata_hash)


class RoundTripTest(unittest.TestCase):
    """`source_records.raw_xml` dan oai_dc metama'lumoti aynan tiklanishi kerak —
    aks holda `raw_metadata` ustunini tashlab bo'lmaydi."""

    def test_metadata_survives_xml_round_trip(self) -> None:
        record = _parse_record(ET.fromstring(SAMPLE))
        self.assertEqual(metadata_from_xml(record.raw_xml), record.metadata)

    def test_deleted_record_round_trip_is_empty(self) -> None:
        deleted = SAMPLE.replace("<header>", '<header status="deleted">').split("<metadata>")[0] + "</record>"
        record = _parse_record(ET.fromstring(deleted))
        self.assertEqual(metadata_from_xml(record.raw_xml), {})


def _response(payload: bytes):
    """`urlopen` context manager'iga o'xshash obyekt."""
    response = mock.MagicMock()
    response.read.return_value = payload
    response.__enter__.return_value = response
    return response


def _http_error(code: int) -> urllib.error.HTTPError:
    return urllib.error.HTTPError("https://x.test/oai", code, "err", {}, io.BytesIO(b""))


class RequestRetryTest(unittest.TestCase):
    """Vaqtinchalik xatolar butun harvest'ni yiqitmasin.

    Jonli logda manba 1 400 yozuvdan keyin `IncompleteRead(0 bytes read)`
    bilan yiqilgan va `failed` bo'lib qolgan edi — bu xato `URLError`
    emasligi uchun qayta urinilmagan."""

    @mock.patch("harvester.oai_harvester.time.sleep")
    @mock.patch("harvester.oai_harvester.urllib.request.urlopen")
    def test_incomplete_read_is_retried(self, urlopen, _sleep) -> None:
        urlopen.side_effect = [http.client.IncompleteRead(b""), _response(b"<ok/>")]
        self.assertEqual(_request("https://x.test/oai", {"verb": "Identify"}, timeout=1), b"<ok/>")
        self.assertEqual(urlopen.call_count, 2)

    @mock.patch("harvester.oai_harvester.time.sleep")
    @mock.patch("harvester.oai_harvester.urllib.request.urlopen")
    def test_remote_disconnected_and_reset_are_retried(self, urlopen, _sleep) -> None:
        urlopen.side_effect = [http.client.RemoteDisconnected(), ConnectionResetError(), _response(b"<ok/>")]
        self.assertEqual(_request("https://x.test/oai", {"verb": "Identify"}, timeout=1), b"<ok/>")
        self.assertEqual(urlopen.call_count, 3)

    @mock.patch("harvester.oai_harvester.time.sleep")
    @mock.patch("harvester.oai_harvester.urllib.request.urlopen")
    def test_http_500_is_retried_but_404_is_not(self, urlopen, _sleep) -> None:
        urlopen.side_effect = [_http_error(500), _response(b"<ok/>")]
        self.assertEqual(_request("https://x.test/oai", {"verb": "Identify"}, timeout=1), b"<ok/>")
        urlopen.reset_mock()
        urlopen.side_effect = [_http_error(404), _response(b"<ok/>")]
        with self.assertRaises(OAIError):
            _request("https://x.test/oai", {"verb": "Identify"}, timeout=1)
        self.assertEqual(urlopen.call_count, 1)

    @mock.patch("harvester.oai_harvester.time.sleep")
    @mock.patch("harvester.oai_harvester.urllib.request.urlopen")
    def test_gives_up_after_retries(self, urlopen, _sleep) -> None:
        urlopen.side_effect = http.client.IncompleteRead(b"")
        with self.assertRaises(OAIError) as caught:
            _request("https://x.test/oai", {"verb": "Identify"}, timeout=1, retries=3)
        self.assertIn("IncompleteRead", str(caught.exception))
        self.assertEqual(urlopen.call_count, 3)


def _list_records(*identifiers: str, token: str | None = None, datestamp: str = "2026-09-01") -> bytes:
    records = "".join(
        f'<record><header><identifier>{item}</identifier><datestamp>{datestamp}</datestamp></header>'
        f'<metadata><oai_dc:dc><dc:title>T {item}</dc:title></oai_dc:dc></metadata></record>'
        for item in identifiers
    )
    token_xml = f"<resumptionToken>{token}</resumptionToken>" if token else ""
    return (
        '<OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/" '
        'xmlns:oai_dc="http://www.openarchives.org/OAI/2.0/oai_dc/" '
        'xmlns:dc="http://purl.org/dc/elements/1.1/">'
        f"<ListRecords>{records}{token_xml}</ListRecords></OAI-PMH>"
    ).encode()


BAD_TOKEN = (
    b'<OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/">'
    b'<error code="badResumptionToken">expired</error></OAI-PMH>'
)


class ResumptionTokenRestartTest(unittest.TestCase):
    def test_restart_from_never_goes_before_original_from(self) -> None:
        self.assertEqual(_restart_from("2026-09-01T10:00:00Z", None), "2026-09-01")
        self.assertEqual(_restart_from("2026-09-01T10:00:00Z", "2026-08-20"), "2026-09-01")
        self.assertEqual(_restart_from("2026-08-10", "2026-08-20"), "2026-08-20")

    @mock.patch("harvester.oai_harvester._request")
    def test_expired_token_restarts_from_last_datestamp(self, request) -> None:
        request.side_effect = [
            _list_records("a", "b", token="t1", datestamp="2026-09-01"),
            BAD_TOKEN,
            _list_records("b", "c"),
        ]
        records = list(harvest("https://x.test/oai", from_date="2026-08-20"))
        self.assertEqual([item.identifier for item in records], ["a", "b", "b", "c"])
        restart_params = request.call_args_list[2].args[1]
        self.assertEqual(restart_params["verb"], "ListRecords")
        self.assertEqual(restart_params["from"], "2026-09-01")
        self.assertNotIn("resumptionToken", restart_params)

    @mock.patch("harvester.oai_harvester._request")
    def test_bad_token_without_progress_is_raised(self, request) -> None:
        request.side_effect = [_list_records(token="t1"), BAD_TOKEN]
        with self.assertRaises(OAIError):
            list(harvest("https://x.test/oai"))


if __name__ == "__main__":
    unittest.main()
