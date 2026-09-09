"""Integration tests against a real PostgreSQL instance.

Skipped unless RUN_INTEGRATION_TESTS=1; CI sets it and provides the services.
"""

from __future__ import annotations

import os

import pytest
from flask import Flask
from flask.testing import FlaskClient

from tourist import config

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_INTEGRATION_TESTS") != "1",
    reason="set RUN_INTEGRATION_TESTS=1 and provide PostgreSQL to run these",
)


@pytest.fixture(scope="module")
def seeded_app() -> Flask:
    if not config.DB_NAME.endswith("_test"):
        pytest.fail(
            f"refusing to run destructive fixtures against {config.DB_NAME!r}: "
            "point DB_NAME at a database whose name ends with _test"
        )

    from tourist.collection import db_setup

    db_setup.create_database()
    db_setup.run_migrations()
    db_setup.seed_cities()

    from tourist import db as database

    from tests.conftest import reset_place_data

    reset_place_data()

    with database.cursor() as cur:
        cur.execute(
            """
            INSERT INTO places_of_interest
                (id, city_id, title, page_id, wiki_relevance_score,
                 pageviews_last_30_days, pagerank_score)
            VALUES
                (1, 1, 'Ranked High', 101, 0.5, 100, 0.9),
                (2, 1, 'Ranked Low',  102, 0.9, 900, 0.1),
                (3, 1, 'Unranked',    103, 0.7, 500, NULL)
            """
        )
        cur.execute(
            """
            INSERT INTO similar_places
                (main_place_id, similar_place_id, similarity_score, similarity_type)
            VALUES (1, 2, 0.88, 'intra_city')
            """
        )

    from tourist.web import create_app

    app = create_app()
    app.config.update(TESTING=True)
    return app


@pytest.fixture()
def client(seeded_app: Flask) -> FlaskClient:
    return seeded_app.test_client()


def test_ready_reports_database_up(client: FlaskClient) -> None:
    response = client.get("/api/v1/ready")
    assert response.status_code == 200
    assert response.get_json()["checks"]["database"] is True


def test_cities_are_seeded_from_config(client: FlaskClient) -> None:
    names = {c["name"] for c in client.get("/api/v1/cities").get_json()["data"]}
    assert names == set(config.CITIES.values())


def test_places_are_paginated(client: FlaskClient) -> None:
    body = client.get("/api/v1/cities/1/places?limit=2&offset=0").get_json()
    assert len(body["data"]) == 2
    assert body["pagination"] == {"total": 3, "limit": 2, "offset": 0}


def test_pagerank_sort_orders_by_pagerank_with_nulls_last(client: FlaskClient) -> None:
    body = client.get("/api/v1/cities/1/places?sort=pagerank").get_json()
    titles = [p["title"] for p in body["data"]]
    assert titles == ["Ranked High", "Ranked Low", "Unranked"]


def test_pageviews_sort_differs_from_pagerank_sort(client: FlaskClient) -> None:
    by_rank = client.get("/api/v1/cities/1/places?sort=pagerank").get_json()
    by_views = client.get("/api/v1/cities/1/places?sort=pageviews").get_json()
    assert [p["id"] for p in by_rank["data"]] != [p["id"] for p in by_views["data"]]


def test_place_detail_includes_scores(client: FlaskClient) -> None:
    body = client.get("/api/v1/places/1").get_json()["data"]
    assert body["title"] == "Ranked High"
    assert body["scores"]["pagerank"] == pytest.approx(0.9)
    assert "total_edit_count" not in body
    assert "days_since_edit" in body


def test_missing_place_returns_json_404(client: FlaskClient) -> None:
    response = client.get("/api/v1/places/99999")
    assert response.status_code == 404
    assert response.get_json()["error"]["code"] == "place_not_found"


def test_structural_similarity_is_returned(client: FlaskClient) -> None:
    body = client.get("/api/v1/places/1/similar").get_json()["data"]
    assert len(body["structural"]) == 1
    assert body["structural"][0]["place"]["title"] == "Ranked Low"


def test_missing_city_returns_json_404(client: FlaskClient) -> None:
    response = client.get("/api/v1/cities/9999/places")
    assert response.status_code == 404
    assert response.get_json()["error"]["code"] == "city_not_found"


def _query_count(app: Flask, path: str) -> int:
    from sqlalchemy import event

    from tourist.web import db

    count = 0

    def bump(*args: object) -> None:
        nonlocal count
        count += 1

    with app.app_context():
        event.listen(db.engine, "before_cursor_execute", bump)
        try:
            response = app.test_client().get(path)
            assert response.status_code == 200, (path, response.status_code)
        finally:
            event.remove(db.engine, "before_cursor_execute", bump)
    return count


def test_city_page_query_count_does_not_grow_with_places(seeded_app: Flask) -> None:
    from tourist import db as database

    with database.cursor() as cur:
        cur.execute(
            """
            INSERT INTO places_of_interest (id, city_id, title, page_id, pagerank_score)
            SELECT 1000 + i, 1, 'Bulk ' || i, 100000 + i, random()
            FROM generate_series(1, 40) AS i
            """
        )
        cur.execute(
            """
            INSERT INTO place_images (place_id, image_filename)
            SELECT 1000 + i, 'bulk_' || i || '.jpg' FROM generate_series(1, 40) AS i
            """
        )

    assert _query_count(seeded_app, "/city/1") <= 4


def test_place_page_query_count_is_bounded(seeded_app: Flask) -> None:
    assert _query_count(seeded_app, "/place/1") <= 16


def test_index_page_is_three_queries(seeded_app: Flask) -> None:
    assert _query_count(seeded_app, "/") <= 3
