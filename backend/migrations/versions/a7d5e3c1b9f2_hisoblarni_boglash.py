"""hisoblarni bog'lash

Revision ID: a7d5e3c1b9f2
Revises: f1c3b8d2a6e4
Create Date: 2026-09-11 16:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a7d5e3c1b9f2'
down_revision: Union[str, Sequence[str], None] = 'f1c3b8d2a6e4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Bir profilga bir nechta kirish usuli (ORCID + Google).

    Mavjud har bir foydalanuvchining joriy usuli `user_identities` ga
    ko'chiriladi, ya'ni kirish avvalgidek ishlayveradi.
    """
    op.create_table(
        "user_identities",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(length=20), nullable=False),
        sa.Column("subject", sa.String(length=200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider", "subject", name="user_identity_uq"),
    )
    op.create_index("ix_user_identities_user_id", "user_identities", ["user_id"])
    op.execute(
        "INSERT INTO user_identities (user_id, provider, subject, created_at, last_login_at) "
        "SELECT id, provider, provider_subject, created_at, last_login_at FROM users"
    )
    with op.batch_alter_table("oauth_states") as batch_op:
        batch_op.add_column(sa.Column("link_user_id", sa.Integer(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("oauth_states") as batch_op:
        batch_op.drop_column("link_user_id")
    op.drop_index("ix_user_identities_user_id", table_name="user_identities")
    op.drop_table("user_identities")
