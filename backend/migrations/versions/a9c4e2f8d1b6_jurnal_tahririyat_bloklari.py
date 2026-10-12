"""jurnal tahririyat bloklari

Revision ID: a9c4e2f8d1b6
Revises: f7a3d9e1b5c2
Create Date: 2026-10-12 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a9c4e2f8d1b6'
down_revision: Union[str, Sequence[str], None] = 'f7a3d9e1b5c2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TEXT_COLUMNS = ("about", "chief_editor", "submission_info", "deadlines", "fees")


def upgrade() -> None:
    """Jurnal sahifasi uchun qo'lda yoziladigan bloklar (`journal_profiles`)."""
    for name in TEXT_COLUMNS:
        op.add_column("journal_profiles", sa.Column(name, sa.Text(), nullable=True))
    op.add_column("journal_profiles", sa.Column("indexing", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("journal_profiles", "indexing")
    for name in reversed(TEXT_COLUMNS):
        op.drop_column("journal_profiles", name)
