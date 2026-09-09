from __future__ import annotations
import logging
from typing import Any, Sequence
from flask import (
    Blueprint,
    Response,
    abort,
    current_app,
    render_template,
    request,
    send_from_directory,
)
from werkzeug.exceptions import NotFound
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from . import db
from .models import City, ImageBasedSimilarPlace, Place, PlaceImage, SimilarPlace

log = logging.getLogger(__name__)
main = Blueprint("main", __name__)
SORT_COLUMNS: dict[str, Any] = {
    "wiki_relevance": Place.wiki_relevance_score,
    "pagerank": Place.pagerank_score,
    "pageviews": Place.pageviews_last_30_days,
}
DEFAULT_SORT: str = "wiki_relevance"
SIMILAR_LIMIT: int = 5


@main.route("/")
def index() -> str:
    """Render the home page: every city with its place count and a cover image.

    One aggregate query and one image lookup instead of loading every place
    in every city to count them.
    """
    counts = dict(
        db.session.execute(
            select(Place.city_id, func.count(Place.id)).group_by(Place.city_id)
        ).all()
    )
    cover_rows = db.session.execute(
        select(Place.city_id, PlaceImage.image_filename)
        .join(PlaceImage, PlaceImage.place_id == Place.id)
        .order_by(Place.city_id, Place.pagerank_score.desc().nullslast(), PlaceImage.id)
        .distinct(Place.city_id)
    ).all()
    covers = {city_id: filename for city_id, filename in cover_rows}

    cities = City.query.order_by(City.name).all()
    cards = [
        {"city": c, "count": counts.get(c.id, 0), "cover": covers.get(c.id)}
        for c in cities
    ]
    return render_template("index.html", cards=cards)


@main.route("/city/<int:city_id>")
def city_view(city_id: int) -> str:
    """Render one city's places, ordered by the requested sort key."""
    city = db.get_or_404(City, city_id)
    sort = request.args.get("sort", DEFAULT_SORT)
    column = SORT_COLUMNS.get(sort)
    if column is None:
        sort, column = DEFAULT_SORT, SORT_COLUMNS[DEFAULT_SORT]
    places = (
        Place.query.filter_by(city_id=city_id)
        .options(selectinload(Place.images))
        .order_by(column.desc().nullslast())
        .all()
    )
    return render_template("city.html", city=city, places=places, current_sort=sort)


def _similar(
    model: Any,
    id_column: Any,
    place_id: int,
    target: Any,
    similarity_type: str | None = None,
) -> Sequence[Any]:
    """Return the highest scoring related places, optionally of one type.

    The related place and its images are loaded eagerly; the place page shows
    a thumbnail for each neighbour, and lazy loading made that one query per
    neighbour.
    """
    query = model.query.filter(id_column == place_id).options(
        selectinload(target).selectinload(Place.images)
    )
    if similarity_type is not None:
        query = query.filter(model.similarity_type == similarity_type)
    return query.order_by(model.similarity_score.desc()).limit(SIMILAR_LIMIT).all()


@main.route("/place/<int:place_id>")
def place_view(place_id: int) -> str:
    """Render one place with its structural and image-based neighbours."""
    place = db.get_or_404(
        Place,
        place_id,
        options=[selectinload(Place.images), selectinload(Place.categories)],
    )
    return render_template(
        "place.html",
        place=place,
        structural_similar=_similar(
            SimilarPlace,
            SimilarPlace.main_place_id,
            place_id,
            SimilarPlace.similar_place,
        ),
        image_similar_same_city=_similar(
            ImageBasedSimilarPlace,
            ImageBasedSimilarPlace.source_id,
            place_id,
            ImageBasedSimilarPlace.target_place,
            "intra_city",
        ),
        image_similar_other_cities=_similar(
            ImageBasedSimilarPlace,
            ImageBasedSimilarPlace.source_id,
            place_id,
            ImageBasedSimilarPlace.target_place,
            "inter_city",
        ),
    )


@main.route("/images/<path:filename>")
def serve_image(filename: str) -> Response:
    """Serve one collected image from the configured images directory."""
    try:
        return send_from_directory(current_app.config["IMAGES_DIR"], filename)
    except NotFound:
        raise
    except Exception:
        log.exception("Failed to serve image %s", filename)
        abort(404)
