"""yetishmayotgan indekslar

Revision ID: 6b31a7083731
Revises: ec3312949a85
Create Date: 2026-08-31 21:35:59.129001

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6b31a7083731'
down_revision: Union[str, Sequence[str], None] = 'ec3312949a85'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Qo'lda `ALTER TABLE` qoldirgan indekslarni tiklaydi.

    `publication_date` va `is_admin` ustunlari `init_db()` ichidagi qo'lda
    yozilgan `ALTER TABLE` bilan qo'shilgan edi. Modelda ikkalasi ham
    `index=True`, lekin `ALTER TABLE ADD COLUMN` indeks yaratmaydi —
    shuning uchun jonli bazada ular yo'q edi. Aynan shu turdagi
    nomuvofiqlik uchun Alembic kerak.

    `IF NOT EXISTS` — bo'sh bazadan qurilgan o'rnatmalarda bu indekslar
    boshlang'ich migratsiyada allaqachon yaratilgan.
    """
    op.execute("CREATE INDEX IF NOT EXISTS ix_articles_publication_date ON articles (publication_date)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_users_is_admin ON users (is_admin)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_users_is_admin")
    op.execute("DROP INDEX IF EXISTS ix_articles_publication_date")
