"""drop columns that were never collected

total_edit_count was always 0 and total_pageviews duplicated
pageviews_last_30_days; last_edited duplicated last_touched. page_age_days
was computed from the last-edit timestamp, so it is renamed to say what it is.

Revision ID: 0004
Revises: 0003
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

SCHEMA = "tourist_app"
TABLE = "places_of_interest"


def upgrade() -> None:
    op.drop_column(TABLE, "total_edit_count", schema=SCHEMA)
    op.drop_column(TABLE, "total_pageviews", schema=SCHEMA)
    op.drop_column(TABLE, "last_edited", schema=SCHEMA)
    op.alter_column(
        TABLE, "page_age_days", new_column_name="days_since_edit", schema=SCHEMA
    )


def downgrade() -> None:
    op.alter_column(
        TABLE, "days_since_edit", new_column_name="page_age_days", schema=SCHEMA
    )
    op.add_column(TABLE, sa.Column("last_edited", sa.DateTime()), schema=SCHEMA)
    op.add_column(TABLE, sa.Column("total_pageviews", sa.Integer()), schema=SCHEMA)
    op.add_column(TABLE, sa.Column("total_edit_count", sa.Integer()), schema=SCHEMA)
