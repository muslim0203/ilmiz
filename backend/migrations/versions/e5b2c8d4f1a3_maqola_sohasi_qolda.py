"""maqola sohasi qo'lda

Revision ID: e5b2c8d4f1a3
Revises: c3e9a1f7d2b4
Create Date: 2026-10-12 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e5b2c8d4f1a3'
down_revision: Union[str, Sequence[str], None] = 'c3e9a1f7d2b4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """`articles.fields_manual` — admin qo'ygan soha avtomatik tasnifdan himoyalanadi.

    Oddiy `ADD COLUMN` (batch emas): batch rejimi jadvalni qayta yaratib,
    FTS triggerlari va ifoda indekslarini yo'qotishi mumkin edi. Doimiy
    `server_default` bilan SQLite mavjud qatorlarni qayta yozmaydi —
    migratsiya bir zumda tugaydi.
    """
    op.add_column("articles", sa.Column("fields_manual", sa.Boolean(), nullable=False, server_default=sa.text("0")))


def downgrade() -> None:
    op.drop_column("articles", "fields_manual")
