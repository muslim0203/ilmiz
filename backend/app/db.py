from __future__ import annotations

import os
from collections.abc import Generator

from sqlalchemy import create_engine, event, inspect, text
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

engine = create_engine(DATABASE_URL, connect_args=CONNECT_ARGS, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


if DATABASE_URL.startswith("sqlite"):

    @event.listens_for(engine, "connect")
    def _configure_sqlite(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        try:
            # WAL o‘quvchi va yozuvchini bir-birini bloklashidan saqlaydi.
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute(f"PRAGMA busy_timeout={SQLITE_BUSY_TIMEOUT_MS}")
            cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.execute("PRAGMA foreign_keys=ON")
        finally:
            cursor.close()


class Base(DeclarativeBase):
    pass


def init_db() -> None:
    from . import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    # create_all existing jadvallarga yangi ustun qo‘shmaydi. MVP uchun kichik,
    # ikki bazada ham ishlaydigan forward migrationni shu yerda saqlaymiz.
    columns = {column["name"] for column in inspect(engine).get_columns("articles")}
    if "publication_date" not in columns:
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE articles ADD COLUMN publication_date VARCHAR(80)"))
    source_columns = {column["name"] for column in inspect(engine).get_columns("harvest_sources")}
    if "insecure_ssl" not in source_columns:
        with engine.begin() as connection:
            connection.execute(
                text("ALTER TABLE harvest_sources ADD COLUMN insecure_ssl BOOLEAN DEFAULT 0 NOT NULL")
            )


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
