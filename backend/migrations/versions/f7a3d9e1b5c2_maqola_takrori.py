"""maqola takrori

Revision ID: f7a3d9e1b5c2
Revises: e5b2c8d4f1a3
Create Date: 2026-10-12 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f7a3d9e1b5c2'
down_revision: Union[str, Sequence[str], None] = 'e5b2c8d4f1a3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """`articles.duplicate_of` — takror maqolaning kanonik nusxasi.

    Oddiy `ADD COLUMN` (batch emas — FTS triggerlari saqlansin); NULL
    standart qiymat bilan SQLite mavjud qatorlarni qayta yozmaydi.
    """
    op.add_column("articles", sa.Column("duplicate_of", sa.Integer(), nullable=True))
    op.create_index("ix_articles_duplicate_of", "articles", ["duplicate_of"])


def downgrade() -> None:
    op.drop_index("ix_articles_duplicate_of", table_name="articles")
    op.drop_column("articles", "duplicate_of")
