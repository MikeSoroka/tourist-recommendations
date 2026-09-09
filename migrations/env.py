"""Alembic environment.

The database URL and schema come from config.py rather than alembic.ini, so
migrations use exactly the same settings as the application and no credential
is ever written into a checked-in file.
"""

from __future__ import annotations

from alembic import context
from sqlalchemy import create_engine, text

from tourist import config
from tourist.web.models import db

target_metadata = db.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=config.database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        include_schemas=True,
        version_table_schema=config.SCHEMA_NAME,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(config.database_url())
    with engine.connect() as connection:
        connection.execute(text(f"CREATE SCHEMA IF NOT EXISTS {config.SCHEMA_NAME}"))
        connection.commit()

        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_schemas=True,
            version_table_schema=config.SCHEMA_NAME,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
