"""Add user_source_aliases table and drop Source.name

Revision ID: c1a2b3d4e567
Revises: b7d1c2e8e946
Create Date: 2026-07-17 12:58:00.000000+00:00

Changes:
  1. CREATE TABLE user_source_aliases (user_id, source_id, display_name)
  2. Add UNIQUE constraint on sources.url to enforce deduplication at the DB level
  3. Backfill existing subscriptions by copying each user's current Source.name
     into user_source_aliases.display_name before dropping the column.
  4. ALTER TABLE sources DROP COLUMN name
  5. ALTER TABLE users DROP COLUMN source_ids (eliminating duplicated state)
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'c1a2b3d4e567'
down_revision: Union[str, None] = 'b7d1c2e8e946'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── Step 1: Create user_source_aliases ────────────────────────────────────
    op.create_table(
        'user_source_aliases',
        sa.Column('user_id',      postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('source_id',    postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('display_name', sa.String(length=255),         nullable=False),
        sa.PrimaryKeyConstraint('user_id', 'source_id', name='pk_user_source_aliases'),
        sa.ForeignKeyConstraint(['user_id'],   ['users.id'],   name='fk_usa_user_id'),
        sa.ForeignKeyConstraint(['source_id'], ['sources.id'], name='fk_usa_source_id'),
    )

    # ── Step 2: Enforce URL uniqueness at the DB level ───────────────────────
    # Prevents duplicate Source rows for the same URL even under concurrent inserts.
    op.create_unique_constraint('uq_sources_url', 'sources', ['url'])

    # ── Step 3: Backfill ───────────────────────────────────────────────────────
    # Copy each user's existing Source.name into the new alias table before
    # the column is dropped, so no display names are lost during migration.
    op.execute("""
        INSERT INTO user_source_aliases (user_id, source_id, display_name)
        SELECT
            u.id         AS user_id,
            sub.source_id AS source_id,
            s.name       AS display_name
        FROM users u
        -- Unnest the UUID array into rows with an explicit column alias
        CROSS JOIN LATERAL unnest(u.source_ids) AS sub(source_id)
        JOIN sources s ON s.id = sub.source_id
        ON CONFLICT (user_id, source_id) DO NOTHING;
    """)

    # ── Step 4: Drop sources.name ──────────────────────────────────────────────
    op.drop_column('sources', 'name')

    # ── Step 5: Drop users.source_ids ──────────────────────────────────────────
    op.drop_column('users', 'source_ids')


def downgrade() -> None:
    # ── Step 1: Restore users.source_ids ──────────────────────────────────────
    op.add_column(
        'users',
        sa.Column('source_ids', postgresql.ARRAY(postgresql.UUID(as_uuid=True)), nullable=True)
    )
    # Populate users.source_ids by aggregating from user_source_aliases
    op.execute("""
        UPDATE users u
        SET source_ids = COALESCE(
            (
                SELECT array_agg(source_id)
                FROM user_source_aliases a
                WHERE a.user_id = u.id
            ),
            '{}'::uuid[]
        );
    """)
    op.alter_column('users', 'source_ids', nullable=False)

    # ── Step 2: Restore sources.name ──────────────────────────────────────────
    # Restore sources.name with a placeholder value (original names are lost)
    op.add_column(
        'sources',
        sa.Column('name', sa.String(length=255), nullable=True),
    )
    # Best-effort restore: use the first alias found for each source
    op.execute("""
        UPDATE sources s
        SET name = (
            SELECT display_name
            FROM user_source_aliases a
            WHERE a.source_id = s.id
            LIMIT 1
        )
    """)
    # Make non-nullable by filling any remaining NULLs with the URL
    op.execute("UPDATE sources SET name = url WHERE name IS NULL")
    op.alter_column('sources', 'name', nullable=False)

    op.drop_constraint('uq_sources_url', 'sources', type_='unique')
    op.drop_table('user_source_aliases')
