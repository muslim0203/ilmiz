"""Alembic muhiti — sxema manbai loyihaning o'z modellari.

Ulanish manzili odatda `backend.app.db` dagi `DATABASE_URL` dan olinadi,
shunda serverdagi sozlama takrorlanmaydi. Testlar `alembic.ini` orqali
boshqa manzil bera oladi.

Dvigatel shu yerda yaratiladi va oxirida yopiladi — ilova dvigatelini
ushlab qolsak, Windows'da vaqtinchalik baza fayli band bo'lib qolardi.
"""
from __future__ import annotations

import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context

# `alembic` ildizdan ishga tushirilganda ham `backend` paketi topilsin.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.app import models  # noqa: E402,F401  (modellar ro'yxatga olinishi uchun)
from backend.app.db import DATABASE_URL, Base, make_engine  # noqa: E402

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata
database_url = config.get_main_option("sqlalchemy.url") or DATABASE_URL


def _configure(**kwargs) -> None:
    context.configure(
        target_metadata=target_metadata,
        # SQLite `ALTER TABLE` ni deyarli qo'llab-quvvatlamaydi. Batch rejimi
        # o'zgarishni vaqtinchalik jadval orqali bajaradi.
        render_as_batch=True,
        compare_type=True,
        **kwargs,
    )


def run_migrations_offline() -> None:
    _configure(url=database_url, literal_binds=True, dialect_opts={"paramstyle": "named"})
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = make_engine(database_url)
    try:
        with connectable.connect() as connection:
            _configure(connection=connection)
            with context.begin_transaction():
                context.run_migrations()
    finally:
        connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
