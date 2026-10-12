"""qo'llanmalar

Revision ID: b7d2f4a6c8e1
Revises: a9c4e2f8d1b6
Create Date: 2026-10-12 20:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b7d2f4a6c8e1'
down_revision: Union[str, Sequence[str], None] = 'a9c4e2f8d1b6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """`/yoriqnoma` qo'llanmalari — admin paneldan yoziladi."""
    op.create_table(
        "guides",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("slug", sa.String(120), nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("body", sa.Text(), nullable=False, server_default=""),
        sa.Column("is_published", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_guides_slug", "guides", ["slug"], unique=True)
    op.create_index("ix_guides_is_published", "guides", ["is_published"])


def downgrade() -> None:
    op.drop_index("ix_guides_is_published", table_name="guides")
    op.drop_index("ix_guides_slug", table_name="guides")
    op.drop_table("guides")
