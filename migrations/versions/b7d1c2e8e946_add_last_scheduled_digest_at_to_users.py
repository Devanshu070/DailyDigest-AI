"""Add last_scheduled_digest_at to users

Revision ID: b7d1c2e8e946
Revises: a3f1c2d8e945
Create Date: 2026-07-17 01:10:00.000000+00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b7d1c2e8e946'
down_revision: Union[str, None] = 'a3f1c2d8e945'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'users',
        sa.Column('last_scheduled_digest_at', sa.DateTime(timezone=True), nullable=True),
    )
    
    # Backfill: assume the last sent digest was a scheduled digest so we don't accidentally
    # send an extra one immediately after deployment.
    op.execute("""
        UPDATE users
        SET last_scheduled_digest_at = last_digest_at
        WHERE last_digest_at IS NOT NULL;
    """)


def downgrade() -> None:
    op.drop_column('users', 'last_scheduled_digest_at')
