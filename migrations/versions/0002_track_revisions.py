"""track wikipedia revisions and staleness

Revision ID: 0002
Revises: 0001
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

SCHEMA = "tourist_app"


def upgrade() -> None:
    op.add_column(
        "places_of_interest",
        sa.Column("last_revision_id", sa.BigInteger(), nullable=True),
        schema=SCHEMA,
    )
    op.add_column(
        "places_of_interest",
        sa.Column("stale_since", sa.DateTime(), nullable=True),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_tourist_app_places_of_interest_stale_since",
        "places_of_interest",
        ["stale_since"],
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_tourist_app_places_of_interest_stale_since",
        table_name="places_of_interest",
        schema=SCHEMA,
    )
    op.drop_column("places_of_interest", "stale_since", schema=SCHEMA)
    op.drop_column("places_of_interest", "last_revision_id", schema=SCHEMA)
