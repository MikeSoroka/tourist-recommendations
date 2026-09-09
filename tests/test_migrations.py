from __future__ import annotations

import pathlib
import re

from tourist import config
from tourist.web.models import db

MIGRATIONS = pathlib.Path(__file__).resolve().parent.parent / "migrations" / "versions"


def _migration_source() -> str:
    return "\n".join(p.read_text() for p in MIGRATIONS.glob("*.py"))


def test_every_model_table_has_a_migration() -> None:
    source = _migration_source()
    created = set(re.findall(r'op\.create_table\(\s*"(\w+)"', source))
    expected = {table.name for table in db.metadata.sorted_tables}
    assert expected <= created, f"missing migrations for: {sorted(expected - created)}"


def test_every_declared_index_has_a_migration() -> None:
    source = _migration_source()
    created = set(re.findall(r'op\.create_index\(\s*"(\w+)"', source))
    created |= set(re.findall(r"CREATE INDEX (\w+) ON", source))
    expected = {
        index.name for table in db.metadata.sorted_tables for index in table.indexes
    }
    assert expected <= created, f"missing indexes: {sorted(expected - created)}"


def test_migrations_target_the_configured_schema() -> None:
    assert f'schema="{config.SCHEMA_NAME}"' in _migration_source()


def test_places_are_indexed_for_each_sort_option() -> None:
    from tourist.web.api import SORTABLE

    source = _migration_source()
    for key, column in SORTABLE.items():
        if key == "title":
            continue
        assert (
            f"{column.key} DESC NULLS LAST" in source
        ), f"{key} sort has no index matching its ORDER BY"


def test_each_migration_defines_a_downgrade() -> None:
    for path in MIGRATIONS.glob("*.py"):
        assert "def downgrade()" in path.read_text()


def test_place_images_records_lead_flag() -> None:
    from tourist.web.models import PlaceImage

    assert "is_lead" in PlaceImage.__table__.columns


def test_image_ownership_prefers_lead_then_earliest() -> None:
    source = (
        pathlib.Path(__file__).resolve().parent.parent
        / "src/tourist/analysis/image_similarities.py"
    ).read_text()
    assert "ORDER BY original_title, is_lead DESC, id" in source
    assert "DISTINCT ON (original_title)" in source


def test_image_collection_replaces_rather_than_appends() -> None:
    source = (
        pathlib.Path(__file__).resolve().parent.parent
        / "src/tourist/collection/base_image_collector.py"
    ).read_text()
    delete_at = source.index("DELETE FROM {SCHEMA_NAME}.place_images WHERE place_id")
    insert_at = source.index("INSERT INTO {SCHEMA_NAME}.place_images")
    assert delete_at < insert_at
