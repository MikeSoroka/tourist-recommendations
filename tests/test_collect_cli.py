from __future__ import annotations
import pytest
from tourist import config
from tourist.collection import collect


def test_all_cities_resolves_every_configured_city() -> None:
    args = collect.build_parser().parse_args(["places", "--all-cities"])
    assert collect._resolve_cities(args) == sorted(config.CITIES.items())


def test_single_city_resolves_to_its_id() -> None:
    args = collect.build_parser().parse_args(["images", "--city", "Vilnius"])
    assert collect._resolve_cities(args) == [(3, "Vilnius")]


def test_city_argument_is_case_insensitive() -> None:
    args = collect.build_parser().parse_args(["all", "--city", "sydney"])
    assert collect._resolve_cities(args) == [(4, "Sydney")]


def test_unknown_city_is_rejected() -> None:
    args = collect.build_parser().parse_args(["places", "--city", "Paris"])
    with pytest.raises(config.ConfigError):
        collect._resolve_cities(args)


def test_city_and_all_cities_are_mutually_exclusive() -> None:
    with pytest.raises(SystemExit):
        collect.build_parser().parse_args(
            ["places", "--city", "Berlin", "--all-cities"]
        )


def test_a_city_selection_is_required() -> None:
    with pytest.raises(SystemExit):
        collect.build_parser().parse_args(["places"])


def test_invalid_stage_is_rejected() -> None:
    with pytest.raises(SystemExit):
        collect.build_parser().parse_args(["nonsense", "--all-cities"])


@pytest.mark.parametrize("stage", ["places", "images", "all"])
def test_valid_stages_are_accepted(stage: str) -> None:
    args = collect.build_parser().parse_args([stage, "--all-cities"])
    assert args.stage == stage
