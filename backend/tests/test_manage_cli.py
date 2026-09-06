"""`manage.py` ning serverda ishga tushish tuzoqlari.

`DATABASE_URL` eksport qilinmasa u joriy katalogda yangi bo'sh baza yaratar,
kod katalogi faqat o'qiladigan bo'lsa `logs/` ni yaratolmay boshlanmasdan
yiqilar edi.
"""
import importlib.util
import logging
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]


def _load_manage():
    spec = importlib.util.spec_from_file_location("ilmiz_manage_under_test", ROOT / "backend" / "manage.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class EnvFileTest(unittest.TestCase):
    def setUp(self) -> None:
        self.manage = _load_manage()

    def test_loads_values_without_overriding_existing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            env_file = Path(directory) / "staging.env"
            env_file.write_text(
                "# izoh\n"
                "ILMIZ_TEST_A=birinchi\n"
                "export ILMIZ_TEST_B=\"qo'shtirnoqli qiymat\"\n"
                "ILMIZ_TEST_C='bitta'\n"
                "ILMIZ_TEST_EXISTING=yangi\n"
                "bo'sh qator emas, lekin tenglik yo'q\n",
                encoding="utf-8",
            )
            with mock.patch.dict(os.environ, {"ILMIZ_TEST_EXISTING": "eski"}, clear=False):
                for key in ("ILMIZ_TEST_A", "ILMIZ_TEST_B", "ILMIZ_TEST_C"):
                    os.environ.pop(key, None)
                loaded = self.manage.load_env_file(env_file)
                self.assertEqual(loaded, 3)
                self.assertEqual(os.environ["ILMIZ_TEST_A"], "birinchi")
                self.assertEqual(os.environ["ILMIZ_TEST_B"], "qo'shtirnoqli qiymat")
                self.assertEqual(os.environ["ILMIZ_TEST_C"], "bitta")
                self.assertEqual(os.environ["ILMIZ_TEST_EXISTING"], "eski")
            for key in ("ILMIZ_TEST_A", "ILMIZ_TEST_B", "ILMIZ_TEST_C"):
                os.environ.pop(key, None)


def _reset_logging() -> None:
    """Fayl handler'larini yopib bo'shatadi — Windows ochiq faylni o'chirmaydi."""
    root = logging.getLogger()
    for handler in list(root.handlers):
        handler.close()
        root.removeHandler(handler)
    logging.basicConfig(force=True, handlers=[logging.NullHandler()])


class LoggingFallbackTest(unittest.TestCase):
    def setUp(self) -> None:
        self.manage = _load_manage()
        self.addCleanup(_reset_logging)

    def test_uses_ilmiz_log_dir(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "nested" / "logs"
            with mock.patch.dict(os.environ, {"ILMIZ_LOG_DIR": str(target)}):
                log_path = self.manage.configure_logging()
            self.assertEqual(log_path, target / "ilmiz.log")
            self.assertTrue(target.is_dir())
            _reset_logging()

    def test_migrations_do_not_silence_cli_logging(self) -> None:
        """`init_db()` (alembic) `manage.py` sozlagan log faylini buzmasin.

        Alembic'ning `fileConfig` chaqiruvi root handler'larni almashtirib,
        mavjud nomli logger'larni o'chirardi — harvest xatolari 31-avgustdan
        beri log fayliga tushmay qolgan edi."""
        from backend.app.db import init_db
        from backend.app.services import ingest

        # Boshqa test modullari `init_db()` ni root handler'siz chaqirgan bo'lishi
        # mumkin — o'sha paytda alembic logger'ni o'chirgan. Bu yerda faqat
        # `manage.py` oqimi tekshiriladi: avval log, keyin migratsiya.
        ingest.logger.disabled = False
        with tempfile.TemporaryDirectory() as directory:
            try:
                with mock.patch.dict(os.environ, {"ILMIZ_LOG_DIR": directory}):
                    log_path = self.manage.configure_logging()
                init_db()
                root = logging.getLogger()
                self.assertTrue(any(isinstance(item, logging.FileHandler) for item in root.handlers))
                self.assertFalse(ingest.logger.disabled)
                ingest.logger.warning("sinov xabari")
            finally:
                _reset_logging()
            self.assertIn("sinov xabari", Path(log_path).read_text(encoding="utf-8"))

    def test_unwritable_log_dir_falls_back_to_console(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            blocker = Path(directory) / "logs"
            blocker.write_text("bu fayl, katalog emas", encoding="utf-8")
            with mock.patch.dict(os.environ, {"ILMIZ_LOG_DIR": str(blocker)}), mock.patch.object(sys, "stderr"):
                log_path = self.manage.configure_logging()
            self.assertIsNone(log_path)
            self.assertTrue(logging.getLogger().handlers)


if __name__ == "__main__":
    unittest.main()
