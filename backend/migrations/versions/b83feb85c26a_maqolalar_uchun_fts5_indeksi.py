"""maqolalar uchun fts5 indeksi

Revision ID: b83feb85c26a
Revises: 6b31a7083731
Create Date: 2026-08-31 22:36:55.303628

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b83feb85c26a'
down_revision: Union[str, Sequence[str], None] = '6b31a7083731'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Maqolalar qidiruvi uchun FTS5 indeksi.

    Qidiruv `search_text LIKE '%so'z%'` bilan ishlardi: boshida joker belgi
    bo'lgani uchun hech qanday indeks yordam bermasdi va har so'rov 104 000
    qatorni to'liq skanerlardi (~0.25-0.34s). Natijalar esa faqat sanaga
    qarab tartiblanardi, ya'ni "pedagogika" 1149 ta natija berib, qaysi biri
    mosroq ekanini ko'rsatmasdi.

    Tokenizator ataylab `trigram`: `unicode61` prefiksdan qidiradi va
    "artpedagogika", "xalqpedagogikasi" kabi qo'shma so'zlarni topmasdi —
    "pedagogika" so'rovida 1149 dan 61 tasi tushib qolardi. Trigram esa
    qism-so'z bo'yicha topadi va hozirgi `LIKE` bilan **aynan bir xil**
    natija beradi, faqat 60-90 baravar tez.

    Narxi: indeks ~0.24 GB joy egallaydi.

    `content='articles'` — matn takrorlanmaydi, FTS asosiy jadvaldan o'qiydi.
    Shuning uchun sinxronlik triggerlar bilan ushlab turiladi.
    """
    bind = op.get_bind()
    if bind.dialect.name != "sqlite":
        # FTS5 faqat SQLite'da. PostgreSQL'da qidiruv eski `LIKE` yo'lidan
        # ketaveradi (`services/search_index.py` shuni tekshiradi).
        return

    op.execute(
        "CREATE VIRTUAL TABLE articles_fts USING fts5("
        "search_text, content='articles', content_rowid='id', tokenize='trigram')"
    )
    op.execute("INSERT INTO articles_fts(articles_fts) VALUES('rebuild')")

    op.execute("""
        CREATE TRIGGER articles_fts_insert AFTER INSERT ON articles BEGIN
            INSERT INTO articles_fts(rowid, search_text) VALUES (new.id, new.search_text);
        END""")
    op.execute("""
        CREATE TRIGGER articles_fts_delete AFTER DELETE ON articles BEGIN
            INSERT INTO articles_fts(articles_fts, rowid, search_text)
            VALUES ('delete', old.id, old.search_text);
        END""")
    op.execute("""
        CREATE TRIGGER articles_fts_update AFTER UPDATE ON articles BEGIN
            INSERT INTO articles_fts(articles_fts, rowid, search_text)
            VALUES ('delete', old.id, old.search_text);
            INSERT INTO articles_fts(rowid, search_text) VALUES (new.id, new.search_text);
        END""")


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "sqlite":
        return
    for trigger in ("articles_fts_update", "articles_fts_delete", "articles_fts_insert"):
        op.execute(f"DROP TRIGGER IF EXISTS {trigger}")
    op.execute("DROP TABLE IF EXISTS articles_fts")
