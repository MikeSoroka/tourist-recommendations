from __future__ import annotations

import pytest
from flask import Flask
from flask.testing import FlaskClient

from tourist.web.api import SORTABLE, ApiError, parse_pagination, parse_sort
from tourist.web.models import Place


@pytest.fixture()
def client(app_instance: Flask) -> FlaskClient:
    return app_instance.test_client()


def test_health_reports_ok(client: FlaskClient) -> None:
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.get_json() == {"status": "ok"}


@pytest.mark.parametrize("query", ["limit=0", "limit=-1", "offset=-1", "limit=abc"])
def test_invalid_pagination_is_rejected(client: FlaskClient, query: str) -> None:
    response = client.get(f"/api/v1/cities/1/places?{query}")
    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "invalid_pagination"


def test_limit_above_maximum_is_rejected(client: FlaskClient) -> None:
    response = client.get("/api/v1/cities/1/places?limit=100000")
    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "invalid_pagination"


def test_unknown_sort_is_rejected_and_lists_valid_options(client: FlaskClient) -> None:
    response = client.get("/api/v1/cities/1/places?sort=nonsense")
    body = response.get_json()
    assert response.status_code == 400
    assert body["error"]["code"] == "invalid_sort"
    for option in SORTABLE:
        assert option in body["error"]["message"]


def test_unknown_api_route_returns_json_error(client: FlaskClient) -> None:
    response = client.get("/api/v1/does-not-exist")
    assert response.status_code == 404
    assert response.get_json()["error"]["code"] == "not_found"


def test_html_routes_still_return_html(client: FlaskClient) -> None:
    response = client.get("/does-not-exist")
    assert response.status_code == 404
    assert b"<" in response.data


def test_pagerank_is_sortable_via_the_api() -> None:
    assert SORTABLE["pagerank"] is Place.pagerank_score


def test_sortable_columns_are_distinct() -> None:
    keys = [column.key for column in SORTABLE.values()]
    assert len(keys) == len(set(keys))


def test_parse_pagination_defaults(app_instance: Flask) -> None:
    with app_instance.test_request_context("/api/v1/cities/1/places"):
        from tourist import config

        assert parse_pagination() == (config.API_DEFAULT_PAGE_SIZE, 0)


def test_parse_sort_default(app_instance: Flask) -> None:
    with app_instance.test_request_context("/api/v1/cities/1/places"):
        assert parse_sort() == "wiki_relevance"


def test_parse_sort_rejects_unknown(app_instance: Flask) -> None:
    with app_instance.test_request_context("/api/v1/cities/1/places?sort=x"):
        with pytest.raises(ApiError) as excinfo:
            parse_sort()
        assert excinfo.value.status == 400
