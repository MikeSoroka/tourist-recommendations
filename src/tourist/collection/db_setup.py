from __future__ import annotations
import logging

"""Create the database, apply migrations, and seed the city registry."""


from alembic import command
from alembic.config import Config
from psycopg2 import sql
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

from tourist import db
from tourist.logging_config import configure as configure_logging
from tourist.config import CITIES, DB_NAME, PROJECT_ROOT, SCHEMA_NAME

log = logging.getLogger(__name__)


def create_database() -> None:
    """Create the project database if it does not already exist."""
    conn = db.raw_connection(dbname="postgres")
    try:
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        cur = conn.cursor()
        cur.execute(
            "SELECT 1 FROM pg_catalog.pg_database WHERE datname = %s", (DB_NAME,)
        )
        if cur.fetchone():
            log.info(f"Database {DB_NAME} already exists")
        else:
            cur.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(DB_NAME)))
            log.info(f"Database {DB_NAME} created successfully")
        cur.close()
    finally:
        conn.close()


def run_migrations() -> None:
    """Bring the schema up to the latest revision."""
    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(PROJECT_ROOT / "migrations"))
    command.upgrade(config, "head")
    log.info(f"Schema {SCHEMA_NAME} is at the latest revision")


def seed_cities() -> None:
    """Insert the configured cities, leaving existing rows untouched."""
    with db.cursor() as cur:
        cur.executemany(
            f"INSERT INTO {SCHEMA_NAME}.cities (id, name) VALUES (%s, %s) "
            "ON CONFLICT (id) DO NOTHING",
            sorted(CITIES.items()),
        )
    log.info(f"Seeded {len(CITIES)} cities")


def main() -> None:
    create_database()
    run_migrations()
    seed_cities()
    log.info("Database setup completed successfully!")


if __name__ == "__main__":
    configure_logging()
    main()
