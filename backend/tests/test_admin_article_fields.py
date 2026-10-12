import os
import tempfile
import unittest

database_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
database_file.close()
os.environ.setdefault("DATABASE_URL", f"sqlite:///{database_file.name}")

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from backend.app.db import Base, get_db  # noqa: E402
from backend.app.main import app  # noqa: E402
from backend.app.models import Article, Journal  # noqa: E402

TOKEN = "test-admin-token"
HEADERS = {"X-Admin-Token": TOKEN}


class AdminArticleFieldsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        journal = Journal(
            slug="multi", name="Ko'p sohali", short_name="M", publisher="P", city="Toshkent",
            fields=["Filologiya", "Pedagogika", "Tarix"],
        )
        self.db.add(journal)
        self.db.flush()
        self.article = Article(
            journal_id=journal.id, title="Tilshunoslikda frazeologik birliklar", normalized_title="x",
            keywords=["frazeologiya"], fields=[],
        )
        self.db.add(self.article)
        self.db.commit()

        def override():
            yield self.db

        app.dependency_overrides[get_db] = override
        os.environ["ILMIZ_ADMIN_TOKEN"] = TOKEN
        self.client = TestClient(app)

    def tearDown(self) -> None:
        app.dependency_overrides.clear()
        os.environ.pop("ILMIZ_ADMIN_TOKEN", None)
        self.db.close()
        self.engine.dispose()

    def test_unclassified_list_and_manual_fields(self) -> None:
        listed = self.client.get("/api/admin/articles/unclassified", headers=HEADERS).json()
        self.assertEqual(listed["total"], 1)
        self.assertEqual(listed["articles"][0]["journalFields"], ["Filologiya", "Pedagogika", "Tarix"])

        saved = self.client.put(
            f"/api/admin/articles/{self.article.id}/fields", json={"fields": ["Pedagogika"]}, headers=HEADERS
        ).json()
        self.assertEqual(saved["fields"], ["Pedagogika"])
        self.assertTrue(saved["fieldsManual"])
        self.assertEqual(self.client.get("/api/admin/articles/unclassified", headers=HEADERS).json()["total"], 0)

    def test_unknown_field_is_rejected(self) -> None:
        response = self.client.put(
            f"/api/admin/articles/{self.article.id}/fields", json={"fields": ["Astrologiya"]}, headers=HEADERS
        )
        self.assertEqual(response.status_code, 422)

    def test_reset_returns_to_automatic_classification(self) -> None:
        self.client.put(f"/api/admin/articles/{self.article.id}/fields", json={"fields": ["Tarix"]}, headers=HEADERS)
        reset = self.client.put(f"/api/admin/articles/{self.article.id}/fields", json={"fields": None}, headers=HEADERS).json()
        self.assertFalse(reset["fieldsManual"])
        self.assertEqual(reset["fields"], ["Filologiya"])

    def test_requires_admin(self) -> None:
        self.assertIn(self.client.get(f"/api/admin/articles/{self.article.id}").status_code, (401, 403))


if __name__ == "__main__":
    unittest.main()
