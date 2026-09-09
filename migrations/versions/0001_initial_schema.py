"""initial schema

Revision ID: 0001
Revises:
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "categories",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
        schema="tourist_app",
    )
    op.create_table(
        "cities",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        schema="tourist_app",
    )
    op.create_table(
        "connection_graph_metrics",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("metric_name", sa.String(length=50), nullable=True),
        sa.Column("metric_value", sa.Float(), nullable=True),
        sa.Column(
            "calculated_at",
            sa.DateTime(),
            nullable=True,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.PrimaryKeyConstraint("id"),
        schema="tourist_app",
    )
    op.create_index(
        "ix_tourist_app_connection_graph_metrics_calculated_at",
        "connection_graph_metrics",
        ["calculated_at"],
        schema="tourist_app",
    )
    op.create_table(
        "places_of_interest",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "city_id",
            sa.Integer(),
            sa.ForeignKey("tourist_app.cities.id"),
            nullable=True,
        ),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("length", sa.Integer(), nullable=True),
        sa.Column("last_touched", sa.DateTime(), nullable=True),
        sa.Column("total_pageviews", sa.Integer(), nullable=True),
        sa.Column("pageviews_last_30_days", sa.Integer(), nullable=True),
        sa.Column("total_edit_count", sa.Integer(), nullable=True),
        sa.Column("last_edited", sa.DateTime(), nullable=True),
        sa.Column("page_age_days", sa.Integer(), nullable=True),
        sa.Column("full_url", sa.Text(), nullable=True),
        sa.Column("page_id", sa.Integer(), nullable=True),
        sa.Column("wiki_relevance_score", sa.Float(), nullable=True),
        sa.Column("pagerank_score", sa.Float(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("page_id"),
        schema="tourist_app",
    )
    op.execute(
        "CREATE INDEX ix_places_city_pagerank ON tourist_app.places_of_interest "
        "(city_id, pagerank_score DESC NULLS LAST)"
    )
    op.execute(
        "CREATE INDEX ix_places_city_pageviews ON tourist_app.places_of_interest "
        "(city_id, pageviews_last_30_days DESC NULLS LAST)"
    )
    op.execute(
        "CREATE INDEX ix_places_city_relevance ON tourist_app.places_of_interest "
        "(city_id, wiki_relevance_score DESC NULLS LAST)"
    )
    op.create_index(
        "ix_tourist_app_places_of_interest_city_id",
        "places_of_interest",
        ["city_id"],
        schema="tourist_app",
    )
    op.create_table(
        "color_features",
        sa.Column(
            "place_id",
            sa.Integer(),
            sa.ForeignKey("tourist_app.places_of_interest.id"),
            nullable=False,
        ),
        sa.Column("feature_vector", postgresql.ARRAY(sa.Float()), nullable=True),
        sa.Column("dominant_colors_json", postgresql.JSONB(), nullable=True),
        sa.Column(
            "processed_at",
            sa.DateTime(),
            nullable=True,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.PrimaryKeyConstraint("place_id"),
        schema="tourist_app",
    )
    op.create_table(
        "image_based_similar_places",
        sa.Column(
            "source_id",
            sa.Integer(),
            sa.ForeignKey("tourist_app.places_of_interest.id"),
            nullable=False,
        ),
        sa.Column(
            "target_id",
            sa.Integer(),
            sa.ForeignKey("tourist_app.places_of_interest.id"),
            nullable=False,
        ),
        sa.Column("similarity_score", sa.Float(), nullable=False),
        sa.Column("similarity_type", sa.String(length=50), nullable=False),
        sa.PrimaryKeyConstraint("source_id", "target_id", "similarity_type"),
        schema="tourist_app",
    )
    op.create_table(
        "page_references",
        sa.Column(
            "source_id",
            sa.Integer(),
            sa.ForeignKey("tourist_app.places_of_interest.id"),
            nullable=False,
        ),
        sa.Column(
            "target_id",
            sa.Integer(),
            sa.ForeignKey("tourist_app.places_of_interest.id"),
            nullable=False,
        ),
        sa.Column("reference_type", sa.String(length=50), nullable=True),
        sa.PrimaryKeyConstraint("source_id", "target_id"),
        schema="tourist_app",
    )
    op.create_index(
        "ix_tourist_app_page_references_target_id",
        "page_references",
        ["target_id"],
        schema="tourist_app",
    )
    op.create_table(
        "place_categories",
        sa.Column(
            "place_id",
            sa.Integer(),
            sa.ForeignKey("tourist_app.places_of_interest.id"),
            nullable=False,
        ),
        sa.Column(
            "category_id",
            sa.Integer(),
            sa.ForeignKey("tourist_app.categories.id"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("place_id", "category_id"),
        schema="tourist_app",
    )
    op.create_index(
        "ix_tourist_app_place_categories_category_id",
        "place_categories",
        ["category_id"],
        schema="tourist_app",
    )
    op.create_table(
        "place_images",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "place_id",
            sa.Integer(),
            sa.ForeignKey("tourist_app.places_of_interest.id"),
            nullable=True,
        ),
        sa.Column("image_filename", sa.String(length=255), nullable=False),
        sa.Column("original_title", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=True,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.PrimaryKeyConstraint("id"),
        schema="tourist_app",
    )
    op.create_index(
        "ix_tourist_app_place_images_place_id",
        "place_images",
        ["place_id"],
        schema="tourist_app",
    )
    op.create_table(
        "similar_places",
        sa.Column(
            "main_place_id",
            sa.Integer(),
            sa.ForeignKey("tourist_app.places_of_interest.id"),
            nullable=False,
        ),
        sa.Column(
            "similar_place_id",
            sa.Integer(),
            sa.ForeignKey("tourist_app.places_of_interest.id"),
            nullable=False,
        ),
        sa.Column("similarity_score", sa.Float(), nullable=False),
        sa.Column("similarity_type", sa.String(length=20), nullable=False),
        sa.PrimaryKeyConstraint("main_place_id", "similar_place_id", "similarity_type"),
        schema="tourist_app",
    )


def downgrade() -> None:
    op.drop_table("similar_places", schema="tourist_app")
    op.drop_table("place_images", schema="tourist_app")
    op.drop_table("place_categories", schema="tourist_app")
    op.drop_table("page_references", schema="tourist_app")
    op.drop_table("image_based_similar_places", schema="tourist_app")
    op.drop_table("color_features", schema="tourist_app")
    op.drop_table("places_of_interest", schema="tourist_app")
    op.drop_table("connection_graph_metrics", schema="tourist_app")
    op.drop_table("cities", schema="tourist_app")
    op.drop_table("categories", schema="tourist_app")
