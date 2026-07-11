"""multi-user: add users table; add fetched_till to sources

Revision ID: a3f1c2d8e945
Revises: 5a7a206bb668
Create Date: 2026-07-10 14:33:00.000000+00:00

Changes:
  - CREATE TABLE users
      (email, interests_md, digest_time, last_digest_at, source_ids, is_active)
  - ALTER TABLE sources ADD COLUMN fetched_till
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'a3f1c2d8e945'
down_revision: Union[str, None] = '5a7a206bb668'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── users ──────────────────────────────────────────────────────────────
    op.create_table(
        'users',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('interests_md', sa.Text(), nullable=False, server_default=''),
        # Daily delivery time in UTC (stored as TIME WITHOUT TIME ZONE)
        sa.Column('digest_time', sa.Time(timezone=False), nullable=False,
                  server_default='06:00:00'),
        # When we last sent a digest — used to compute the next window
        sa.Column('last_digest_at', sa.DateTime(timezone=True), nullable=True),
        # Array of source IDs this user follows
        sa.Column('source_ids', postgresql.ARRAY(postgresql.UUID(as_uuid=True)), nullable=False, server_default='{}'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('email', name='uq_users_email'),
    )

    # ── sources.fetched_till ───────────────────────────────────────────────
    # High-water mark: articles published before this timestamp are already
    # in the DB. The runner only fetches articles published after this point.
    op.add_column(
        'sources',
        sa.Column('fetched_till', sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('sources', 'fetched_till')
    op.drop_table('users')
