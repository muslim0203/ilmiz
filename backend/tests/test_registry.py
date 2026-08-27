import json
import unittest

from backend.app.services.audit_queue import endpoint_candidates
from backend.app.services.oak_registry import decode_registry_rows, extract_publication_count, extract_registry_payload, slugify


class RegistryParserTest(unittest.TestCase):
    def test_extracts_and_decodes_next_payload(self) -> None:
        payload = {
            "total": 2,
            "columns": ["name", "kind", "area", "link"],
            "dicts": {
                "name": ["Birinchi jurnal", "Ikkinchi jurnal"],
                "kind": ["Миллий нашрлар"],
                "area": ["Техника фанлари", "Тарих фанлари"],
                "link": ["https://example.uz/index.php/journal"],
            },
            "data": [[0, 0, 0, 0], [1, 0, 1, None]],
        }
        rsc_chunk = f'4:["$","component",null,{{"payload":{json.dumps(payload, ensure_ascii=False)}}}]'
        document = f"<script>self.__next_f.push([1,{json.dumps(rsc_chunk, ensure_ascii=False)}])</script>"
        extracted = extract_registry_payload(document)
        records = decode_registry_rows(extracted)
        self.assertEqual(len(records), 2)
        self.assertEqual(records[0]["name"], "Birinchi jurnal")
        self.assertEqual(records[1]["area"], "Тарих фанлари")

    def test_slugifies_cyrillic_title(self) -> None:
        self.assertEqual(slugify("ҚарДУ хабарлари"), "qardu-xabarlari")

    def test_extracts_visible_publication_count(self) -> None:
        self.assertEqual(extract_publication_count("<strong>1\u00a0709 ta jurnal</strong>"), 1709)

    def test_ojs_endpoint_candidate(self) -> None:
        candidates = endpoint_candidates("https://example.uz/index.php/journal/about")
        self.assertEqual(candidates[0], "https://example.uz/index.php/journal/oai")
        self.assertLessEqual(len(candidates), 3)


if __name__ == "__main__":
    unittest.main()
