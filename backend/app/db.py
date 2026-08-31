from __future__ import annotations

import os
from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine, event, inspect
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

# SQLite standart holatda `delete` journal rejimida va drayver faqat 5 soniya
# lock kutadi. Bazamiz gigabaytlarcha bo‘lgani uchun harvest commitlari shu
# limitdan oshib ketardi va run `running` holatida osilib qolardi.
SQLITE_BUSY_TIMEOUT_MS = int(os.getenv("SQLITE_BUSY_TIMEOUT_MS", "30000"))


def _database_url() -> str:
    value = os.getenv("DATABASE_URL", "sqlite:///./ilmiz.db")
    if value.startswith("postgres://"):
        return value.replace("postgres://", "postgresql+psycopg://", 1)
    if value.startswith("postgresql://"):
        return value.replace("postgresql://", "postgresql+psycopg://", 1)
    return value


DATABASE_URL = _database_url()
CONNECT_ARGS = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

def _attach_sqlite_pragmas(target) -> None:
    """SQLite ulanishiga loyihaga kerakli sozlamalarni qo'yadi.

    Alohida funksiya, chunki migratsiyalar ham o'z dvigatelini yaratadi va
    xuddi shu sozlamalarga muhtoj — ayniqsa `busy_timeout` ga, gigabaytlik
    bazada indeks qurish uzoq davom etadi.
    """

    @event.listens_for(target, "connect")
    def _configure_sqlite(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        try:
            # WAL o'quvchi va yozuvchini bir-birini bloklashidan saqlaydi.
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute(f"PRAGMA busy_timeout={SQLITE_BUSY_TIMEOUT_MS}")
            cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.execute("PRAGMA foreign_keys=ON")
        finally:
            cursor.close()
        # SQLite'ning o'rnatilgan `lower()` faqat ASCII bilan ishlaydi:
        # lower('МОРФО') -> 'МОРФО'. Shu sabab `ilike` kirill matnda registrga
        # sezgir bo'lib qolardi va "морфофункциональная" hech nima topmasdi,
        # holbuki sarlavha "МОРФОФУНКЦИОНАЛЬНАЯ" bo'lib bazada bor edi.
        # PostgreSQL'da `ILIKE` o'zi Unicode bilan ishlaydi, bu faqat SQLite muammosi.
        dbapi_connection.create_function(
            "lower", 1, lambda value: value.lower() if isinstance(value, str) else value,
            deterministic=True,
        )
        dbapi_connection.create_function(
            "upper", 1, lambda value: value.upper() if isinstance(value, str) else value,
            deterministic=True,
        )


def make_engine(url: str):
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    created = create_engine(url, connect_args=connect_args, pool_pre_ping=True)
    if url.startswith("sqlite"):
        _attach_sqlite_pragmas(created)
    return created


engine = make_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


# Boshlang'ich migratsiya — mavjud bazani shu nuqtada belgilaymiz.
BASELINE_REVISION = "ec3312949a85"


def _alembic_config():
    from alembic.config import Config

    root = Path(__file__).resolve().parents[2]
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "backend" / "migrations"))
    return config


def init_db() -> None:
    """Sxemani migratsiyalar bilan joriy holatga keltiradi.

    Ilgari bu yerda `create_all` va qo'lda yozilgan `ALTER TABLE` lar turardi.
    Ular ustun qo'shardi, lekin indeks yaratmasdi: jonli bazada
    `ix_articles_publication_date` va `ix_users_is_admin` yo'q edi, garchi
    modelda `index=True` yozilgan bo'lsa ham. Bunday nomuvofiqlik sezilmay
    to'planardi, chunki sxemaning versiyasi hech qayerda yozilmasdi.

    Uch holat bor va uchalasi ham `head` bilan yakunlanadi:
      1. Baza bo'sh — migratsiyalar hammasini quradi.
      2. Baza to'la, lekin Alembic belgisi yo'q — mavjud o'rnatmalarni
         boshlang'ichda belgilab, keyingilarini qo'llaymiz.
      3. Baza allaqachon belgilangan — faqat yangilarini qo'llaymiz.
    """
    from alembic import command

    from . import models  # noqa: F401  (modellar ro'yxatga olinishi uchun)

    from alembic.runtime.migration import MigrationContext

    tables = set(inspect(engine).get_table_names())
    with engine.connect() as connection:
        current = MigrationContext.configure(connection).get_current_revision()

    config = _alembic_config()
    # Belgini `alembic_version` jadvalining borligiga qarab emas, undagi
    # versiya yozuviga qarab aniqlaymiz: Alembic bu jadvalni o'qish uchun
    # ham yaratib qo'yadi, ya'ni bo'sh jadval "belgilangan" degani emas.
    if current is None and "journals" in tables:
        # Mavjud baza: sxemasi boshlang'ich migratsiyaga teng deb qabul
        # qilinadi, shuning uchun DDL bajarilmaydi — faqat belgi qo'yiladi.
        command.stamp(config, BASELINE_REVISION)
    command.upgrade(config, "head")


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
