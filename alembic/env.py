from __future__ import annotations

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

db_endpoint = os.getenv("EZRULES_DB_ENDPOINT")
if db_endpoint:
    config.set_main_option("sqlalchemy.url", db_endpoint)


def _load_target_metadata():
    # Database settings are required when importing ezrules model metadata.
    os.environ.setdefault("EZRULES_APP_SECRET", "alembic-placeholder-secret")
    os.environ.setdefault("EZRULES_ORG_ID", "1")
    from ezrules.models import backend_core  # noqa: F401
    from ezrules.models.database import Base

    return Base.metadata


target_metadata = _load_target_metadata()


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
        dialect_opts={"paramstyle": "named"},
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
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
