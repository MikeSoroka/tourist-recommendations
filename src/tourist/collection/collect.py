from __future__ import annotations
import argparse
import logging
from typing import Sequence
from tourist import config
from tourist.logging_config import configure as configure_logging

log = logging.getLogger(__name__)


def _resolve_cities(args: argparse.Namespace) -> list[tuple[int, str]]:
    """Return the (id, name) pairs the run should cover."""
    if args.all_cities:
        return sorted(config.CITIES.items())
    identifier = config.city_id(args.city)
    return [(identifier, config.city_name(identifier))]


def build_parser() -> argparse.ArgumentParser:
    """Return the argument parser for the collection CLI."""
    parser = argparse.ArgumentParser(
        description="Collect places and images from Wikipedia."
    )
    parser.add_argument(
        "stage",
        choices=("places", "images", "all"),
        help="which collection stage to run",
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--city", help=f"city name ({', '.join(sorted(config.CITIES.values()))})"
    )
    group.add_argument(
        "--all-cities", action="store_true", help="run for every configured city"
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="debug logging")
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    """Run the requested collection stage for the requested cities."""
    from tourist.collection.base_collector import BaseCollector
    from tourist.collection.base_image_collector import BaseImageCollector

    args = build_parser().parse_args(argv)
    configure_logging(args.verbose)
    for identifier, name in _resolve_cities(args):
        if args.stage in ("places", "all"):
            log.info("Collecting places for %s (id=%s)", name, identifier)
            with BaseCollector(city_id=identifier, city_name=name) as collector:
                collector.process_places()
        if args.stage in ("images", "all"):
            log.info("Collecting images for %s (id=%s)", name, identifier)
            with BaseImageCollector(city_id=identifier, city_name=name) as collector:
                collector.collect_images()


if __name__ == "__main__":
    main()
