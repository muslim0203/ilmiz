import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from deploy.prepare_staging import snapshot


class SnapshotTests(unittest.TestCase):
    def test_copies_committed_wal_data_without_changing_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, target = root / "source.db", root / "backup.db"
            with closing(sqlite3.connect(source)) as db:
                db.execute("PRAGMA journal_mode=WAL")
                db.execute("CREATE TABLE sample(value TEXT)")
                db.execute("INSERT INTO sample VALUES ('committed in WAL')")
                db.commit()
                snapshot(source, target)
                self.assertEqual(db.execute("PRAGMA journal_mode").fetchone()[0], "wal")
            with closing(sqlite3.connect(target)) as backup:
                self.assertEqual(backup.execute("SELECT value FROM sample").fetchone()[0], "committed in WAL")

    def test_refuses_existing_destination(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, target = root / "source.db", root / "backup.db"
            with closing(sqlite3.connect(source)) as db:
                db.execute("CREATE TABLE sample(value TEXT)")
            target.write_bytes(b"preserve existing file")
            with self.assertRaises(FileExistsError):
                snapshot(source, target)
            self.assertEqual(target.read_bytes(), b"preserve existing file")


if __name__ == "__main__":
    unittest.main()
