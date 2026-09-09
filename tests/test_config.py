from __future__ import annotations
import importlib
import pytest
from tourist import config


def test_city_id_and_name_round_trip() -> None:
    for identifier, name in config.CITIES.items():
        assert config.city_id(name) == identifier
        assert config.city_name(identifier) == name


def test_city_id_is_case_insensitive() -> None:
    assert config.city_id("berlin") == config.city_id("BERLIN") == 1


def test_unknown_city_name_raises_with_known_names() -> None:
    with pytest.raises(config.ConfigError) as excinfo:
        config.city_id("Paris")
    assert "Berlin" in str(excinfo.value)


def test_unknown_city_id_raises() -> None:
    with pytest.raises(config.ConfigError):
        config.city_name(999)


def test_get_db_password_raises_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DB_PASSWORD", raising=False)
    with pytest.raises(config.ConfigError) as excinfo:
        config.get_db_password()
    assert "DB_PASSWORD" in str(excinfo.value)


def test_get_db_password_rejects_empty_string(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DB_PASSWORD", "")
    with pytest.raises(config.ConfigError):
        config.get_db_password()


def test_no_hardcoded_password_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DB_PASSWORD", raising=False)
    with pytest.raises(config.ConfigError):
        config.database_url()


def test_database_url_contains_configured_parts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DB_PASSWORD", "s3cret")
    url = config.database_url()
    assert url.startswith("postgresql://")
    assert "s3cret" in url
    assert config.DB_NAME in url
    assert config.DB_HOST in url


def test_invalid_schema_name_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DB_SCHEMA", "bad-schema; DROP TABLE x")
    with pytest.raises(ValueError):
        importlib.reload(config)
    monkeypatch.delenv("DB_SCHEMA", raising=False)
    importlib.reload(config)


def test_project_root_locates_alembic_config() -> None:
    assert (config.PROJECT_ROOT / "alembic.ini").exists()


def test_project_root_is_overridable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PROJECT_ROOT", "/tmp/elsewhere")
    importlib.reload(config)
    assert str(config.PROJECT_ROOT) == "/tmp/elsewhere"
    monkeypatch.delenv("PROJECT_ROOT", raising=False)
    importlib.reload(config)
