"""
app/models/user_source_alias.py — Per-user display names for subscribed sources.

Maps a user's chosen label for a given source. One row per (user, source) pair.

This is the join table that replaces the removed Source.name field:
  - Source records are global and identified only by (type, url).
  - UserSourceAlias stores the user-visible name for each subscription.
  - The pipeline never reads this table; it derives labels from the article URL.
"""

import uuid

from sqlalchemy import String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class UserSourceAlias(Base):
    __tablename__ = "user_source_aliases"

    # Composite primary key: one alias per user per source
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, nullable=False
    )
    source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, nullable=False
    )

    # The user's chosen display name for this source.
    # Set when the user adds the source; updatable by re-adding with a new name.
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)

    def __repr__(self) -> str:
        return (
            f"<UserSourceAlias user={self.user_id} "
            f"source={self.source_id} name={self.display_name!r}>"
        )
