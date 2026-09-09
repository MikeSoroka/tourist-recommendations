"""SQLAlchemy models for the tourist recommendations schema."""

from __future__ import annotations
from sqlalchemy.dialects.postgresql import ARRAY, JSONB

from tourist import config
from . import db

SCHEMA = config.SCHEMA_NAME


def _fk(table: str, column: str = "id") -> str:
    """Fully-qualified foreign key target within the project schema."""
    return f"{SCHEMA}.{table}.{column}"


class City(db.Model):
    __tablename__ = "cities"
    __table_args__ = {"schema": SCHEMA}

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    places = db.relationship("Place", backref="city", lazy=True)


class Place(db.Model):
    __tablename__ = "places_of_interest"

    id = db.Column(db.Integer, primary_key=True)
    city_id = db.Column(db.Integer, db.ForeignKey(_fk("cities")), index=True)
    title = db.Column(db.String(255), nullable=False)
    length = db.Column(db.Integer)
    last_touched = db.Column(db.DateTime)
    pageviews_last_30_days = db.Column(db.Integer)
    days_since_edit = db.Column(db.Integer)
    full_url = db.Column(db.Text)
    page_id = db.Column(db.Integer, unique=True)
    wiki_relevance_score = db.Column(db.Float)

    pagerank_score = db.Column(db.Float)
    description = db.Column(db.Text)
    last_revision_id = db.Column(db.BigInteger)
    stale_since = db.Column(db.DateTime, index=True)

    __table_args__ = (
        db.Index(
            "ix_places_city_pagerank",
            "city_id",
            db.text("pagerank_score DESC NULLS LAST"),
        ),
        db.Index(
            "ix_places_city_relevance",
            "city_id",
            db.text("wiki_relevance_score DESC NULLS LAST"),
        ),
        db.Index(
            "ix_places_city_pageviews",
            "city_id",
            db.text("pageviews_last_30_days DESC NULLS LAST"),
        ),
        {"schema": SCHEMA},
    )

    images = db.relationship("PlaceImage", backref="place", lazy=True)
    categories = db.relationship(
        "Category",
        secondary=f"{SCHEMA}.place_categories",
        backref=db.backref("places", lazy=True),
    )


class PlaceImage(db.Model):
    __tablename__ = "place_images"
    __table_args__ = {"schema": SCHEMA}

    id = db.Column(db.Integer, primary_key=True)
    place_id = db.Column(
        db.Integer, db.ForeignKey(_fk("places_of_interest")), index=True
    )
    image_filename = db.Column(db.String(255), nullable=False)
    original_title = db.Column(db.Text)
    is_lead = db.Column(db.Boolean, nullable=False, server_default=db.text("false"))
    created_at = db.Column(db.DateTime, server_default=db.func.current_timestamp())


class Category(db.Model):
    __tablename__ = "categories"
    __table_args__ = {"schema": SCHEMA}

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)


class PlaceCategory(db.Model):
    __tablename__ = "place_categories"
    __table_args__ = {"schema": SCHEMA}

    place_id = db.Column(
        db.Integer, db.ForeignKey(_fk("places_of_interest")), primary_key=True
    )
    category_id = db.Column(
        db.Integer, db.ForeignKey(_fk("categories")), primary_key=True, index=True
    )


class ImageBasedSimilarPlace(db.Model):
    __tablename__ = "image_based_similar_places"
    __table_args__ = {"schema": SCHEMA}

    source_id = db.Column(
        db.Integer, db.ForeignKey(_fk("places_of_interest")), primary_key=True
    )
    target_id = db.Column(
        db.Integer, db.ForeignKey(_fk("places_of_interest")), primary_key=True
    )
    similarity_score = db.Column(db.Float, nullable=False)
    similarity_type = db.Column(db.String(50), primary_key=True)

    source_place = db.relationship(
        "Place",
        foreign_keys=[source_id],
        backref=db.backref("similar_places_as_source", lazy=True),
    )
    target_place = db.relationship(
        "Place",
        foreign_keys=[target_id],
        backref=db.backref("similar_places_as_target", lazy=True),
    )


class SimilarPlace(db.Model):
    __tablename__ = "similar_places"
    __table_args__ = {"schema": SCHEMA}

    main_place_id = db.Column(
        db.Integer, db.ForeignKey(_fk("places_of_interest")), primary_key=True
    )
    similar_place_id = db.Column(
        db.Integer, db.ForeignKey(_fk("places_of_interest")), primary_key=True
    )
    similarity_score = db.Column(db.Float, nullable=False)
    similarity_type = db.Column(db.String(20), primary_key=True)

    main_place = db.relationship(
        "Place",
        foreign_keys=[main_place_id],
        backref=db.backref("structural_similar_places_as_main", lazy=True),
    )
    similar_place = db.relationship(
        "Place",
        foreign_keys=[similar_place_id],
        backref=db.backref("structural_similar_places_as_similar", lazy=True),
    )


class PageReference(db.Model):
    """Directed wiki link between two places, the PageRank input graph."""

    __tablename__ = "page_references"
    __table_args__ = {"schema": SCHEMA}

    source_id = db.Column(
        db.Integer, db.ForeignKey(_fk("places_of_interest")), primary_key=True
    )
    target_id = db.Column(
        db.Integer,
        db.ForeignKey(_fk("places_of_interest")),
        primary_key=True,
        index=True,
    )
    reference_type = db.Column(db.String(50), default="wiki_link")


class ConnectionGraphMetric(db.Model):
    """One measurement of the reference graph, recorded per analytics run."""

    __tablename__ = "connection_graph_metrics"
    __table_args__ = {"schema": SCHEMA}

    id = db.Column(db.Integer, primary_key=True)
    metric_name = db.Column(db.String(50))
    metric_value = db.Column(db.Float)
    calculated_at = db.Column(
        db.DateTime, server_default=db.func.current_timestamp(), index=True
    )


class ColorFeature(db.Model):
    """Colour feature vector extracted from a place's images."""

    __tablename__ = "color_features"
    __table_args__ = {"schema": SCHEMA}

    place_id = db.Column(
        db.Integer, db.ForeignKey(_fk("places_of_interest")), primary_key=True
    )
    feature_vector = db.Column(ARRAY(db.Float))
    dominant_colors_json = db.Column(JSONB)
    processed_at = db.Column(db.DateTime, server_default=db.func.current_timestamp())
