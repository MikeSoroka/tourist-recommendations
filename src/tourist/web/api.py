"""JSON API for the tourist recommendations dataset."""

from __future__ import annotations

from typing import Any

from flask import Blueprint, jsonify, request
from sqlalchemy import text
from sqlalchemy.orm import selectinload
from werkzeug.exceptions import HTTPException

from tourist import cache
from tourist import config
from . import db
from .models import (
    Category,
    City,
    ImageBasedSimilarPlace,
    Place,
    PlaceImage,
    SimilarPlace,
)

api = Blueprint("api", __name__, url_prefix="/api/v1")

SORTABLE = {
    "wiki_relevance": Place.wiki_relevance_score,
    "pagerank": Place.pagerank_score,
    "pageviews": Place.pageviews_last_30_days,
    "title": Place.title,
}


class ApiError(Exception):
    """An error that should reach the client as a JSON envelope."""

    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


@api.errorhandler(ApiError)
def _handle_api_error(exc: ApiError) -> tuple[Any, int]:
    return jsonify({"error": {"code": exc.code, "message": exc.message}}), exc.status


def _error_response(exc: HTTPException) -> tuple[Any, int]:
    code = (exc.name or "error").lower().replace(" ", "_")
    return (
        jsonify({"error": {"code": code, "message": exc.description}}),
        exc.code or 500,
    )


@api.errorhandler(HTTPException)
def _handle_http_error(exc: HTTPException) -> tuple[Any, int]:
    return _error_response(exc)


def register_error_handlers(app: Any) -> None:
    """Serve JSON errors for API paths while leaving HTML pages untouched."""

    @app.errorhandler(HTTPException)
    def _dispatch(exc: HTTPException) -> Any:
        if request.path.startswith(api.url_prefix or "/api"):
            return _error_response(exc)
        return exc

    @app.errorhandler(ApiError)
    def _dispatch_api_error(exc: ApiError) -> Any:
        return (
            jsonify({"error": {"code": exc.code, "message": exc.message}}),
            exc.status,
        )


def parse_pagination() -> tuple[int, int]:
    """Read and validate limit/offset from the query string."""
    try:
        limit = int(request.args.get("limit", config.API_DEFAULT_PAGE_SIZE))
        offset = int(request.args.get("offset", 0))
    except ValueError:
        raise ApiError(400, "invalid_pagination", "limit and offset must be integers")
    if limit < 1 or offset < 0:
        raise ApiError(400, "invalid_pagination", "limit must be >= 1 and offset >= 0")
    if limit > config.API_MAX_PAGE_SIZE:
        raise ApiError(
            400,
            "invalid_pagination",
            f"limit must not exceed {config.API_MAX_PAGE_SIZE}",
        )
    return limit, offset


def parse_sort() -> str:
    """Read and validate the sort key from the query string."""
    sort = request.args.get("sort", "wiki_relevance")
    if sort not in SORTABLE:
        raise ApiError(
            400, "invalid_sort", f"sort must be one of: {', '.join(sorted(SORTABLE))}"
        )
    return sort


def serialize_city(city: City) -> dict[str, Any]:
    return {"id": city.id, "name": city.name}


def serialize_image(image: PlaceImage) -> dict[str, Any]:
    return {"filename": image.image_filename, "original_title": image.original_title}


def serialize_place(place: Place, detail: bool = False) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": place.id,
        "city_id": place.city_id,
        "title": place.title,
        "url": place.full_url,
        "scores": {
            "wiki_relevance": place.wiki_relevance_score,
            "pagerank": place.pagerank_score,
            "pageviews_last_30_days": place.pageviews_last_30_days,
        },
    }
    if detail:
        payload["description"] = place.description
        payload["last_touched"] = (
            place.last_touched.isoformat() if place.last_touched else None
        )
        payload["days_since_edit"] = place.days_since_edit
        payload["images"] = [serialize_image(i) for i in place.images]
        payload["categories"] = [c.name for c in place.categories]
    return payload


def serialize_similarity(row: Any, place_attr: str) -> dict[str, Any]:
    place = getattr(row, place_attr)
    return {
        "place": serialize_place(place),
        "score": row.similarity_score,
        "type": row.similarity_type,
    }


@api.get("/cities")
@cache.cached("cities")
def list_cities() -> dict[str, Any]:
    cities = City.query.order_by(City.name).all()
    return {"data": [serialize_city(c) for c in cities]}


@api.get("/cities/<int:city_id>/places")
def list_city_places(city_id: int) -> dict[str, Any]:
    limit, offset = parse_pagination()
    sort = parse_sort()
    return _city_places(city_id, sort, limit, offset)


@cache.cached("city_places")
def _city_places(city_id: int, sort: str, limit: int, offset: int) -> dict[str, Any]:
    if db.session.get(City, city_id) is None:
        raise ApiError(404, "city_not_found", f"No city with id {city_id}")

    base = Place.query.filter_by(city_id=city_id)
    total = base.count()
    places = (
        base.order_by(SORTABLE[sort].desc().nullslast())
        .limit(limit)
        .offset(offset)
        .all()
    )
    return {
        "data": [serialize_place(p) for p in places],
        "pagination": {"total": total, "limit": limit, "offset": offset},
        "sort": sort,
    }


@api.get("/places/<int:place_id>")
def get_place(place_id: int) -> dict[str, Any]:
    place = db.session.get(
        Place,
        place_id,
        options=[selectinload(Place.images), selectinload(Place.categories)],
    )
    if place is None:
        raise ApiError(404, "place_not_found", f"No place with id {place_id}")
    return {"data": serialize_place(place, detail=True)}


@api.get("/places/<int:place_id>/similar")
def get_similar(place_id: int) -> dict[str, Any]:
    limit, _ = parse_pagination()
    if db.session.get(Place, place_id) is None:
        raise ApiError(404, "place_not_found", f"No place with id {place_id}")

    structural = (
        SimilarPlace.query.filter(SimilarPlace.main_place_id == place_id)
        .options(selectinload(SimilarPlace.similar_place))
        .order_by(SimilarPlace.similarity_score.desc())
        .limit(limit)
        .all()
    )
    image_based = (
        ImageBasedSimilarPlace.query.filter(
            ImageBasedSimilarPlace.source_id == place_id
        )
        .options(selectinload(ImageBasedSimilarPlace.target_place))
        .order_by(ImageBasedSimilarPlace.similarity_score.desc())
        .limit(limit)
        .all()
    )
    return {
        "data": {
            "structural": [
                serialize_similarity(r, "similar_place") for r in structural
            ],
            "image_based": [
                serialize_similarity(r, "target_place") for r in image_based
            ],
        }
    }


@api.get("/categories")
@cache.cached("categories")
def list_categories() -> dict[str, Any]:
    categories = Category.query.order_by(Category.name).all()
    return {"data": [{"id": c.id, "name": c.name} for c in categories]}


@api.get("/health")
def health() -> dict[str, Any]:
    return {"status": "ok"}


@api.get("/ready")
def ready() -> tuple[Any, int]:
    checks = {"database": False, "cache": cache.ping()}
    try:
        db.session.execute(text("SELECT 1"))
        checks["database"] = True
    except Exception:
        checks["database"] = False

    status = 200 if checks["database"] else 503
    return (
        jsonify({"status": "ok" if status == 200 else "degraded", "checks": checks}),
        status,
    )
