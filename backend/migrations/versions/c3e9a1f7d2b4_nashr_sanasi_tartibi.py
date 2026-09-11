"""nashr sanasi tartibi

Revision ID: c3e9a1f7d2b4
Revises: a7d5e3c1b9f2
Create Date: 2026-09-11 17:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c3e9a1f7d2b4'
down_revision: Union[str, Sequence[str], None] = 'a7d5e3c1b9f2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Ro'yxatlarni nashr sanasi bo'yicha saralash uchun ifoda indekslari.

    Ustun qo'shilmaydi va maqolalar qayta yozilmaydi (FTS triggerlari
    qo'zg'almaydi): 99.99% sana `YYYY-MM-DD` ko'rinishida, `substr` kifoya.
    """
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_articles_published "
        "ON articles (is_deleted, substr(publication_date, 1, 10) DESC, id DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_articles_journal_published "
        "ON articles (journal_id, is_deleted, substr(publication_date, 1, 10) DESC, id DESC)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_articles_journal_published")
    op.execute("DROP INDEX IF EXISTS ix_articles_published")
