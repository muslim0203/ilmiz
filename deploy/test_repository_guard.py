import unittest
from unittest.mock import patch

from deploy.check_repository import check, content_reasons, path_reason


class RepositoryGuardTests(unittest.TestCase):
    def test_blocks_database_variants(self):
        for path in ("ilmiz.db", "data/test.db-wal", "backup.sqlite3", "test.sqlite-shm"):
            self.assertIsNotNone(path_reason(path), path)

    def test_blocks_private_files(self):
        for path in ("backend/.env", ".env.production", ".ssh/authorized_keys", "deploy/key.pem", ".deploy-artifacts/runtime.tar.gz"):
            self.assertIsNotNone(path_reason(path), path)

    def test_allows_source_and_examples(self):
        for path in ("backend/.env.example", "database/schema.sql", "src/App.tsx", ".github/workflows/ci.yml"):
            self.assertIsNone(path_reason(path), path)

    def test_server_operations_notes_stay_local(self):
        for path in ("deploy/README.md", "deploy/staging.env.example", "deploy/install_staging.sh"):
            self.assertEqual(path_reason(path), "local-only server operations file")

    def test_detects_private_key_without_printing_value(self):
        value = b"-----BEGIN " + b"OPENSSH PRIVATE KEY-----\nexample"
        self.assertEqual(content_reasons(value), ["private key"])

    def test_detects_disguised_database(self):
        self.assertIn("SQLite database content", content_reasons(b"SQLite format 3\x00example"))

    def test_detects_known_token_pattern(self):
        self.assertEqual(content_reasons(b"ghp_" + b"a" * 36), ["GitHub credential"])

    def test_regular_source_not_a_secret(self):
        self.assertEqual(content_reasons(b'os.environ.get("ILMIZ_ADMIN_TOKEN")'), [])

    def test_index_scan_reads_blob_by_oid(self):
        def fake_git(*args):
            responses = {
                ("ls-files", "--stage", "-z"): b"100644 abc123 0\tsrc/example.py\0",
                ("cat-file", "-t", "abc123"): b"blob\n",
                ("cat-file", "-s", "abc123"): b"5\n",
                ("cat-file", "blob", "abc123"): b"hello",
            }
            return responses[args]
        with patch("deploy.check_repository.git", side_effect=fake_git):
            self.assertEqual(check(), [])


if __name__ == "__main__":
    unittest.main()
