from __future__ import annotations
import os
import pytest
from flask import Flask

os.environ.setdefault("DB_PASSWORD", "test-password")


@pytest.fixture()
def app_instance() -> Flask:
    from tourist.web import create_app

    app = create_app()
    app.config.update(TESTING=True)
    return app


DEPENDENT_TABLES = (
    "image_based_similar_places",
    "similar_places",
    "page_references",
    "color_features",
    "place_images",
    "place_categories",
    "places_of_interest",
)


def reset_place_data() -> None:
    """Clear place data in foreign-key-safe order.

    Shared so every integration module tears down the same way; deleting
    places_of_interest first fails once any dependent row exists.
    """
    from tourist import config
    from tourist import db

    with db.cursor() as cur:
        for table in DEPENDENT_TABLES:
            cur.execute(f"DELETE FROM {config.SCHEMA_NAME}.{table}")
