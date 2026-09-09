"""record which image is a page's lead image

Revision ID: 0003
Revises: 0002
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

SCHEMA = "tourist_app"


def upgrade() -> None:
    op.add_column(
        "place_images",
        sa.Column(
            "is_lead", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_place_images_original_title",
        "place_images",
        ["original_title"],
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_place_images_original_title", table_name="place_images", schema=SCHEMA
    )
    op.drop_column("place_images", "is_lead", schema=SCHEMA)
