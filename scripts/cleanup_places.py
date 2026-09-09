from __future__ import annotations
from tourist.config import SCHEMA_NAME
from tourist import db


def cleanup_places() -> None:
    """Delete places that don't have any associated images"""
    try:

        conn = db.raw_connection()
        cur = conn.cursor()

        cur.execute(f"SET search_path TO {SCHEMA_NAME}")

        cur.execute(
            """
            SELECT COUNT(*)
            FROM places_of_interest p
            WHERE NOT EXISTS (
                SELECT 1
                FROM place_images i
                WHERE i.place_id = p.id
            )
        """
        )
        count = cur.fetchone()[0]
        print(f"Found {count} places without images")

        if count > 0:

            cur.execute(
                """
                DELETE FROM place_categories
                WHERE place_id IN (
                    SELECT id
                    FROM places_of_interest p
                    WHERE NOT EXISTS (
                        SELECT 1
                        FROM place_images i
                        WHERE i.place_id = p.id
                    )
                )
            """
            )

            cur.execute(
                """
                DELETE FROM similar_places
                WHERE main_place_id IN (
                    SELECT id
                    FROM places_of_interest p
                    WHERE NOT EXISTS (
                        SELECT 1
                        FROM place_images i
                        WHERE i.place_id = p.id
                    )
                ) OR similar_place_id IN (
                    SELECT id
                    FROM places_of_interest p
                    WHERE NOT EXISTS (
                        SELECT 1
                        FROM place_images i
                        WHERE i.place_id = p.id
                    )
                )
            """
            )

            cur.execute(
                """
                DELETE FROM places_of_interest p
                WHERE NOT EXISTS (
                    SELECT 1
                    FROM place_images i
                    WHERE i.place_id = p.id
                )
            """
            )

            conn.commit()
            print(
                f"Successfully deleted {count} places without images and their related data"
            )

        cur.execute(
            """
            DELETE FROM categories c
            WHERE NOT EXISTS (
                SELECT 1
                FROM place_categories pc
                WHERE pc.category_id = c.id
            )
        """
        )
        conn.commit()

        cur.close()
        conn.close()
        print("Cleanup completed successfully!")

    except Exception as e:
        print(f"Error during cleanup: {str(e)}")
        if "conn" in locals():
            conn.rollback()
            conn.close()


if __name__ == "__main__":
    cleanup_places()
