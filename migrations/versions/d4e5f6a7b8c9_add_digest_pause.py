"""Add scheduled digest pause flag to users.

Revision ID: d4e5f6a7b8c9
Revises: c1a2b3d4e567
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, None] = "c1a2b3d4e567"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "digest_paused",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.alter_column("users", "digest_paused", server_default=None)


def downgrade() -> None:
    op.drop_column("users", "digest_paused")
