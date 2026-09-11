"""ish joyi uchun ROR ID

Revision ID: d4e1a7c9b2f0
Revises: b83feb85c26a
Create Date: 2026-09-11 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd4e1a7c9b2f0'
down_revision: Union[str, Sequence[str], None] = 'b83feb85c26a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """`users.affiliation_ror` — ish joyining ROR identifikatori.

    `affiliation` matni o'z joyida qoladi: ROR'da yo'q muassasalar uchun
    foydalanuvchi nomni qo'lda yozadi va bu ustun bo'sh turadi.
    """
    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(sa.Column("affiliation_ror", sa.String(length=9), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_column("affiliation_ror")
