from __future__ import annotations
from flask import Flask
from tourist.web.models import Place
from tourist.web.views import DEFAULT_SORT, SIMILAR_LIMIT, SORT_COLUMNS


def test_each_sort_option_maps_to_a_distinct_column() -> None:
    names = [column.key for column in SORT_COLUMNS.values()]
    assert len(names) == len(set(names))


def test_pagerank_sort_uses_the_pagerank_column() -> None:
    assert SORT_COLUMNS["pagerank"] is Place.pagerank_score


def test_wiki_relevance_sort_uses_the_relevance_column() -> None:
    assert SORT_COLUMNS["wiki_relevance"] is Place.wiki_relevance_score


def test_pageviews_sort_uses_the_pageviews_column() -> None:
    assert SORT_COLUMNS["pageviews"] is Place.pageviews_last_30_days


def test_default_sort_is_a_known_option() -> None:
    assert DEFAULT_SORT in SORT_COLUMNS


def test_similar_limit_is_positive() -> None:
    assert SIMILAR_LIMIT > 0


def test_template_sort_options_are_all_supported(app_instance: Flask) -> None:
    template = app_instance.jinja_env.get_or_select_template("city.html").filename
    with open(template, encoding="utf-8") as handle:
        markup = handle.read()
    for option in SORT_COLUMNS:
        assert f"sort='{option}'" in markup or f'sort="{option}"' in markup


def test_registered_routes(app_instance: Flask) -> None:
    rules = {rule.rule for rule in app_instance.url_map.iter_rules()}
    assert {"/", "/city/<int:city_id>", "/place/<int:place_id>"} <= rules


def test_engine_recovers_stale_connections(app_instance: Flask) -> None:
    options = app_instance.config["SQLALCHEMY_ENGINE_OPTIONS"]
    assert options["pool_pre_ping"] is True
