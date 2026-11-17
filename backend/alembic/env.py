"""Alembic environment: wires Alembic to our SQLModel metadata.

The DB URL comes from app.config.Settings, not alembic.ini — one source of
truth. Autogenerate uses SQLModel.metadata so `alembic revision --autogenerate`
picks up model changes.
"""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool
from sqlmodel import SQLModel

# Import the models so their tables register on SQLModel.metadata.
from app import models  # noqa: F401
from app.config import get_settings


config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Override alembic.ini's placeholder URL with the live app URL.
config.set_main_option("sqlalchemy.url", get_settings().database_url)

target_metadata = SQLModel.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,  # SQLite needs batch mode for ALTER TABLE
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
