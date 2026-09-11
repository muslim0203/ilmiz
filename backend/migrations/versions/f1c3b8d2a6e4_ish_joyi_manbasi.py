"""ish joyi manbasi

Revision ID: f1c3b8d2a6e4
Revises: d4e1a7c9b2f0
Create Date: 2026-09-11 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f1c3b8d2a6e4'
down_revision: Union[str, Sequence[str], None] = 'd4e1a7c9b2f0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """`users.affiliation_source` — ish joyi ORCID'dan (`orcid`) yoki qo'lda (`manual`).

    Mavjud qatorlarda bo'sh qoladi: allaqachon kiritilgan ish joyi
    foydalanuvchiniki deb hisoblanadi va ORCID bilan kirganda ustidan
    yozilmaydi.
    """
    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(sa.Column("affiliation_source", sa.String(length=10), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_column("affiliation_source")
