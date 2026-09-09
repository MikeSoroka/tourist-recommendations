from __future__ import annotations
from tourist import config
from tourist.web.models import (
    Category,
    City,
    ImageBasedSimilarPlace,
    Place,
    PlaceCategory,
    PlaceImage,
    SimilarPlace,
)

ALL_MODELS = [
    City,
    Place,
    PlaceImage,
    Category,
    PlaceCategory,
    ImageBasedSimilarPlace,
    SimilarPlace,
]


def test_every_model_uses_the_configured_schema() -> None:
    for model in ALL_MODELS:
        assert model.__table__.schema == config.SCHEMA_NAME


def test_place_exposes_pagerank_score() -> None:
    assert "pagerank_score" in Place.__table__.columns


def test_place_exposes_the_columns_the_ui_sorts_on() -> None:
    for column in ("wiki_relevance_score", "pagerank_score", "pageviews_last_30_days"):
        assert column in Place.__table__.columns


def test_foreign_keys_target_the_configured_schema() -> None:
    for fk in Place.__table__.foreign_keys:
        assert fk.column.table.schema == config.SCHEMA_NAME
