import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from deploy.ci_deploy import payload


class DeployPayloadTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.archive = Path(self.directory.name) / "runtime.tar.gz"
        self.archive.write_bytes(b"archive")
        digest = hashlib.sha256(b"archive").hexdigest()
        (self.archive.parent / "SHA256SUMS").write_text(f"{digest}  runtime.tar.gz\n")
        self.release = "a" * 40 + "-123-1"

    def test_header_matches_archive(self):
        header, content = payload(self.archive, self.release).split(b"\n", 1)
        data = json.loads(header)
        self.assertEqual(data["release"], self.release)
        self.assertEqual(data["size"], len(content))
        self.assertEqual(data["sha256"], hashlib.sha256(content).hexdigest())

    def test_rejects_path_or_command_injection(self):
        for value in ("../release", self.release + ";id", "not-a-commit", "a" * 40 + "-0-1"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                payload(self.archive, value)

    def test_rejects_checksum_mismatch(self):
        self.archive.write_bytes(b"tampered")
        with self.assertRaises(ValueError):
            payload(self.archive, self.release)

    def test_rejects_empty_archive(self):
        self.archive.write_bytes(b"")
        with self.assertRaises(ValueError):
            payload(self.archive, self.release)


if __name__ == "__main__":
    unittest.main()
