from __future__ import annotations
from psycopg2.extensions import connection as Connection
from pathlib import Path

from tourist.config import SCHEMA_NAME
from tourist import db

IMAGE_DIR = Path("data/images")


def get_db_connection() -> Connection:
    """Create a database connection (see db.py for the shared factory)."""
    return db.raw_connection()


def cleanup_missing_images() -> None:
    """Remove database entries for missing images"""
    conn = get_db_connection()
    cur = conn.cursor()

    try:

        cur.execute(f"SET search_path TO {SCHEMA_NAME}")

        cur.execute("SELECT id, image_filename, place_id FROM place_images")
        images = cur.fetchall()

        missing_images = []
        for img_id, filename, place_id in images:
            if not (IMAGE_DIR / filename).exists():
                missing_images.append((img_id, filename, place_id))

        if not missing_images:
            print("No missing images found.")
            return

        print(f"Found {len(missing_images)} missing images.")

        missing_image_ids = [img[0] for img in missing_images]
        affected_place_ids = [img[2] for img in missing_images]

        img_placeholders = ",".join(["%s"] * len(missing_image_ids))

        cur.execute(
            f"""
            DELETE FROM color_features
            WHERE place_id IN (
                SELECT DISTINCT place_id
                FROM place_images
                WHERE id IN ({img_placeholders})
            )
        """,
            missing_image_ids,
        )
        print("Deleted related color features.")

        cur.execute(
            f"""
            DELETE FROM image_based_similar_places
            WHERE source_id IN (
                SELECT DISTINCT place_id
                FROM place_images
                WHERE id IN ({img_placeholders})
            ) OR target_id IN (
                SELECT DISTINCT place_id
                FROM place_images
                WHERE id IN ({img_placeholders})
            )
        """,
            missing_image_ids * 2,
        )
        print("Deleted related image-based similarities.")

        cur.execute(
            f"""
            DELETE FROM place_images
            WHERE id IN ({img_placeholders})
        """,
            missing_image_ids,
        )
        print("Deleted missing image records.")

        place_placeholders = ",".join(["%s"] * len(affected_place_ids))
        cur.execute(
            f"""
            SELECT p.id, p.title
            FROM places_of_interest p
            WHERE p.id IN ({place_placeholders})
            AND NOT EXISTS (
                SELECT 1
                FROM place_images pi
                WHERE pi.place_id = p.id
            )
        """,
            affected_place_ids,
        )

        empty_places = cur.fetchall()
        if empty_places:
            print(f"\nFound {len(empty_places)} places with no remaining images:")
            for place_id, title in empty_places:
                print(f"- {title} (ID: {place_id})")

            response = input("\nDo you want to delete these places? (yes/no): ")
            if response.lower() == "yes":
                empty_place_ids = [p[0] for p in empty_places]
                place_placeholders = ",".join(["%s"] * len(empty_place_ids))

                cur.execute(
                    f"""
                    DELETE FROM place_categories
                    WHERE place_id IN ({place_placeholders})
                """,
                    empty_place_ids,
                )

                cur.execute(
                    f"""
                    DELETE FROM similar_places
                    WHERE main_place_id IN ({place_placeholders})
                    OR similar_place_id IN ({place_placeholders})
                """,
                    empty_place_ids * 2,
                )

                cur.execute(
                    f"""
                    DELETE FROM page_references
                    WHERE source_id IN ({place_placeholders})
                    OR target_id IN ({place_placeholders})
                """,
                    empty_place_ids * 2,
                )

                cur.execute(
                    f"""
                    DELETE FROM places_of_interest
                    WHERE id IN ({place_placeholders})
                """,
                    empty_place_ids,
                )
                print("Deleted places with no remaining images.")

        conn.commit()
        print("\nCleanup completed successfully!")

    except Exception as e:
        conn.rollback()
        print(f"Error during cleanup: {str(e)}")
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    cleanup_missing_images()
