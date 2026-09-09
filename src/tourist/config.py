from __future__ import annotations
import os
import re
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()
PACKAGE_ROOT: Path = Path(__file__).resolve().parent


def _project_root() -> Path:
    """Locate the directory holding alembic.ini and the data directory.

    The package installs under src/, so the repository root is two levels up;
    PROJECT_ROOT env var overrides for deployments that lay things out
    differently.
    """
    override = os.getenv("PROJECT_ROOT")
    if override:
        return Path(override)
    candidate = PACKAGE_ROOT.parents[1]
    if (candidate / "alembic.ini").exists():
        return candidate
    return Path.cwd()


PROJECT_ROOT: Path = _project_root()
DB_NAME: str = os.getenv("DB_NAME", "tourist_recommendations")
DB_USER: str = os.getenv("DB_USER", "postgres")
DB_HOST: str = os.getenv("DB_HOST", "localhost")
DB_PORT: str = os.getenv("DB_PORT", "5432")
SCHEMA_NAME: str = os.getenv("DB_SCHEMA", "tourist_app")
IMAGES_DIR: Path = Path(os.getenv("IMAGES_DIR", PROJECT_ROOT / "data" / "images"))

REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
CACHE_TTL_SECONDS: int = int(os.getenv("CACHE_TTL_SECONDS", "300"))
CACHE_ENABLED: bool = os.getenv("CACHE_ENABLED", "1") == "1"

HTTP_MAX_WORKERS: int = int(os.getenv("HTTP_MAX_WORKERS", "4"))
HTTP_RATE_LIMIT_PER_SECOND: float = float(os.getenv("HTTP_RATE_LIMIT_PER_SECOND", "4"))
HTTP_TIMEOUT_SECONDS: float = float(os.getenv("HTTP_TIMEOUT_SECONDS", "15"))
HTTP_MAX_RETRIES: int = int(os.getenv("HTTP_MAX_RETRIES", "5"))
HTTP_USER_AGENT: str = os.getenv(
    "HTTP_USER_AGENT",
    "tourist-recommendations/1.0 (https://github.com/MikeSoroka/tourist-recommendations)",
)

STREAM_NAME: str = os.getenv("STREAM_NAME", "wiki:changes")
STREAM_GROUP: str = os.getenv("STREAM_GROUP", "refresh")
STREAM_CONSUMER: str = os.getenv("STREAM_CONSUMER", os.uname().nodename)
STREAM_MAX_LENGTH: int = int(os.getenv("STREAM_MAX_LENGTH", "100000"))
STREAM_BATCH_SIZE: int = int(os.getenv("STREAM_BATCH_SIZE", "100"))
STREAM_IDLE_RECLAIM_MS: int = int(os.getenv("STREAM_IDLE_RECLAIM_MS", "60000"))
STREAM_MAX_DELIVERIES: int = int(os.getenv("STREAM_MAX_DELIVERIES", "5"))

DETECT_INTERVAL_SECONDS: int = int(os.getenv("DETECT_INTERVAL_SECONDS", "3600"))
CONSUME_INTERVAL_SECONDS: int = int(os.getenv("CONSUME_INTERVAL_SECONDS", "60"))
WIKI_BATCH_SIZE: int = int(os.getenv("WIKI_BATCH_SIZE", "50"))

API_DEFAULT_PAGE_SIZE: int = int(os.getenv("API_DEFAULT_PAGE_SIZE", "50"))
API_MAX_PAGE_SIZE: int = int(os.getenv("API_MAX_PAGE_SIZE", "200"))
CITIES: dict[int, str] = {
    1: "Berlin",
    2: "Copenhagen",
    3: "Vilnius",
    4: "Sydney",
}
_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
if not _IDENTIFIER.fullmatch(SCHEMA_NAME):
    raise ValueError(f"DB_SCHEMA is not a valid SQL identifier: {SCHEMA_NAME!r}")


class ConfigError(RuntimeError):
    """Raised when required configuration is missing or invalid."""


def get_db_password() -> str:
    """Return the database password, or raise if it is not configured."""
    password = os.getenv("DB_PASSWORD")
    if not password:
        raise ConfigError(
            "DB_PASSWORD is not set. Copy .env.example to .env and set it, or "
            "export DB_PASSWORD in your shell. There is deliberately no default."
        )
    return password


def city_name(city_id: int) -> str:
    """Return the name registered for a city id."""
    try:
        return CITIES[city_id]
    except KeyError:
        known = ", ".join(f"{i}={n}" for i, n in sorted(CITIES.items()))
        raise ConfigError(f"Unknown city id {city_id}. Known cities: {known}") from None


def city_id(name: str) -> int:
    """Return the id registered for a city name, matched case-insensitively."""
    for identifier, registered in CITIES.items():
        if registered.lower() == name.lower():
            return identifier
    known = ", ".join(sorted(CITIES.values()))
    raise ConfigError(f"Unknown city {name!r}. Known cities: {known}")


def database_url() -> str:
    """Return the SQLAlchemy connection URL for the Flask application."""
    return f"postgresql://{DB_USER}:{get_db_password()}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
