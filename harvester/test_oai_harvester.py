import unittest
import xml.etree.ElementTree as ET

from harvester.oai_harvester import metadata_from_xml, OAIRecord, _parse_record, _root
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
        root = _root(b'<OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/"><responseDate>2026-01-01</responseDate><request>https://x.uz/oai?a=1&b=2</request></OAI-PMH>')
        self.assertTrue(root.tag.endswith("OAI-PMH"))

    def test_extracts_article_links_and_date(self) -> None:
        metadata = {
            "identifier": ["https://journal.uz/article/view/12", "https://journal.uz/article/download/12/8"],
            "date": ["2025-04-17"],
        }
        self.assertEqual(_landing_url(metadata), "https://journal.uz/article/view/12")
        self.assertEqual(_pdf_url(metadata), "https://journal.uz/article/download/12/8")
        self.assertEqual(_publication_date(metadata), "2025-04-17")

    def test_parses_oai_dc_record(self) -> None:
        record = _parse_record(ET.fromstring(SAMPLE))
        self.assertIsInstance(record, OAIRecord)
        self.assertEqual(record.identifier, "oai:example.uz:article/42")
        self.assertEqual(record.metadata["title"], ["Namuna maqola"])
        self.assertEqual(record.metadata["creator"], ["Ali Valiyev", "Malika Karimova"])
        self.assertFalse(record.deleted)
        self.assertEqual(record.set_specs, ["journal:demo"])
        self.assertEqual(len(record.metadata_hash or ""), 64)

    def test_parses_deleted_record(self) -> None:
        payload = """
        <record xmlns="http://www.openarchives.org/OAI/2.0/">
          <header status="deleted">
            <identifier>oai:example.uz:article/7</identifier>
            <datestamp>2026-08-20</datestamp>
          </header>
        </record>
        """
        record = _parse_record(ET.fromstring(payload))
        self.assertTrue(record.deleted)
        self.assertIsNone(record.metadata_hash)


    def test_metadata_survives_xml_round_trip(self) -> None:
        """`raw_xml` saqlangan yagona manba — metama'lumot undan aynan tiklanishi shart."""
        record = _parse_record(ET.fromstring(SAMPLE))
        self.assertEqual(metadata_from_xml(record.raw_xml), record.metadata)

    def test_deleted_record_round_trip_is_empty(self) -> None:
        payload = """
        <record xmlns="http://www.openarchives.org/OAI/2.0/">
          <header status="deleted">
            <identifier>oai:example.uz:article/7</identifier>
            <datestamp>2026-08-20</datestamp>
          </header>
        </record>
        """
        record = _parse_record(ET.fromstring(payload))
        self.assertEqual(metadata_from_xml(record.raw_xml), {})


if __name__ == "__main__":
    unittest.main()
