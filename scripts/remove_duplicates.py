from __future__ import annotations

from tourist.config import SCHEMA_NAME
from tourist import db
from tourist.text_utils import title_similarity


def find_and_remove_duplicates() -> None:
    """Find and remove duplicate places from Copenhagen"""
    try:

        conn = db.raw_connection()
        cur = conn.cursor()

        cur.execute(f"SET search_path TO {SCHEMA_NAME}")

        cur.execute("SELECT id FROM cities WHERE name = 'Copenhagen'")
        copenhagen_id = cur.fetchone()[0]

        cur.execute(
            """
            SELECT id, title, wiki_relevance_score, pageviews_last_30_days,
                   (SELECT COUNT(*) FROM place_images WHERE place_id = p.id) as image_count
            FROM places_of_interest p
            WHERE city_id = %s
            ORDER BY wiki_relevance_score DESC, pageviews_last_30_days DESC
        """,
            (copenhagen_id,),
        )

        places = cur.fetchall()
        print(f"Found {len(places)} places in Copenhagen")

        duplicates = []
        for i in range(len(places)):
            for j in range(i + 1, len(places)):
                similarity = title_similarity(places[i][1], places[j][1])
                if similarity > 0.85:

                    place1_score = (
                        places[i][2] * 0.4 + places[i][3] * 0.3 + places[i][4] * 0.3
                    )
                    place2_score = (
                        places[j][2] * 0.4 + places[j][3] * 0.3 + places[j][4] * 0.3
                    )

                    keep_id = (
                        places[i][0] if place1_score >= place2_score else places[j][0]
                    )
                    remove_id = (
                        places[j][0] if place1_score >= place2_score else places[i][0]
                    )

                    duplicates.append(
                        {
                            "keep_id": keep_id,
                            "remove_id": remove_id,
                            "similarity": similarity,
                            "title1": places[i][1],
                            "title2": places[j][1],
                        }
                    )

        if not duplicates:
            print("No duplicates found!")
            return

        print(f"\nFound {len(duplicates)} duplicate pairs:")
        for dup in duplicates:
            print(f"\nSimilarity: {dup['similarity']:.2f}")
            print(f"Title 1: {dup['title1']}")
            print(f"Title 2: {dup['title2']}")
            print(f"Keeping ID: {dup['keep_id']}, Removing ID: {dup['remove_id']}")

        for dup in duplicates:
            try:

                cur.execute(
                    """
                    SELECT COUNT(*)
                    FROM color_features
                    WHERE place_id IN (%s, %s)
                """,
                    (dup["keep_id"], dup["remove_id"]),
                )

                color_features_count = cur.fetchone()[0]

                if color_features_count > 1:

                    cur.execute(
                        """
                        DELETE FROM color_features
                        WHERE place_id = %s
                    """,
                        (dup["remove_id"],),
                    )
                else:

                    cur.execute(
                        """
                        UPDATE color_features
                        SET place_id = %s,
                            processed_at = CURRENT_TIMESTAMP
                        WHERE place_id = %s
                    """,
                        (dup["keep_id"], dup["remove_id"]),
                    )

                cur.execute(
                    """
                    UPDATE place_images
                    SET place_id = %s
                    WHERE place_id = %s
                """,
                    (dup["keep_id"], dup["remove_id"]),
                )

                cur.execute(
                    """
                    SELECT source_id, target_id
                    FROM page_references
                    WHERE source_id = %s OR target_id = %s
                """,
                    (dup["remove_id"], dup["remove_id"]),
                )

                references = cur.fetchall()

                for ref in references:
                    source_id, target_id = ref
                    new_source_id = (
                        dup["keep_id"] if source_id == dup["remove_id"] else source_id
                    )
                    new_target_id = (
                        dup["keep_id"] if target_id == dup["remove_id"] else target_id
                    )

                    cur.execute(
                        """
                        SELECT 1
                        FROM page_references
                        WHERE source_id = %s AND target_id = %s
                    """,
                        (new_source_id, new_target_id),
                    )

                    exists = cur.fetchone() is not None

                    if exists:

                        cur.execute(
                            """
                            DELETE FROM page_references
                            WHERE source_id = %s AND target_id = %s
                        """,
                            (source_id, target_id),
                        )
                    else:

                        cur.execute(
                            """
                            UPDATE page_references
                            SET source_id = %s,
                                target_id = %s
                            WHERE source_id = %s AND target_id = %s
                        """,
                            (new_source_id, new_target_id, source_id, target_id),
                        )

                cur.execute(
                    """
                    DELETE FROM similar_places
                    WHERE main_place_id = %s OR similar_place_id = %s
                """,
                    (dup["remove_id"], dup["remove_id"]),
                )

                cur.execute(
                    """
                    DELETE FROM image_based_similar_places
                    WHERE source_id = %s OR target_id = %s
                """,
                    (dup["remove_id"], dup["remove_id"]),
                )

                cur.execute(
                    """
                    DELETE FROM place_categories
                    WHERE place_id = %s
                """,
                    (dup["remove_id"],),
                )

                cur.execute(
                    """
                    DELETE FROM places_of_interest
                    WHERE id = %s
                """,
                    (dup["remove_id"],),
                )

                conn.commit()
                print(f"Successfully removed duplicate place {dup['remove_id']}")
            except Exception as e:
                print(f"Error removing place {dup['remove_id']}: {str(e)}")
                conn.rollback()
                continue

        print("\nFinished processing duplicate places")

    except Exception as e:
        conn.rollback()
        print(f"Error: {str(e)}")
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    find_and_remove_duplicates()
