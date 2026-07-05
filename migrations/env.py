"""
migrations/env.py — Alembic environment configuration.

Wires Alembic to:
  - The SQLAlchemy engine (via app.config.settings)
  - The declarative Base metadata (via app.models.Base)

This enables `alembic revision --autogenerate` to detect model changes
and produce migration files automatically.
"""

from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context

# ── Alembic config object (alembic.ini) ────────────────────────────────────
config = context.config

# Set up loggers from alembic.ini
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# ── Import models so Alembic can see all table metadata ────────────────────
# We must import Base AND all model modules so their tables are registered
# on Base.metadata before autogenerate runs.
from app.models.base import Base
import app.models.source   # noqa: F401
import app.models.article  # noqa: F401
import app.models.digest   # noqa: F401

target_metadata = Base.metadata

# ── Inject DATABASE_URL from app.config (overrides alembic.ini) ────────────
from app.config import settings

config.set_main_option("sqlalchemy.url", settings.sqlalchemy_database_url)


# ── Offline migrations (alembic upgrade head --sql) ─────────────────────────
def run_migrations_offline() -> None:
    """
    Run migrations in 'offline' mode — generates raw SQL without a live DB.
    Useful for reviewing or applying migrations in restricted environments.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


# ── Online migrations (alembic upgrade head) ────────────────────────────────
def run_migrations_online() -> None:
    """
    Run migrations in 'online' mode — connects to a live DB and applies changes.
    This is the standard path used in development and production.
    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
