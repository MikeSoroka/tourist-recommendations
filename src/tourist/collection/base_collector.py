from __future__ import annotations
import logging
from datetime import datetime, timezone

from tourist.config import SCHEMA_NAME
from tourist import config
from tourist import db
from tourist import http_client
from tourist.concurrency import map_concurrent
from tourist.text_utils import is_place_title, normalize_category
from tourist.wikipedia import parse_wiki_timestamp

log = logging.getLogger(__name__)


class BaseCollector:
    def __init__(self, city_id: int, city_name: str) -> None:
        self.city_id = city_id
        self.city_name = city_name
        self.base_url = "https://en.wikipedia.org/w/api.php"
        self.max_places = 100

        self.db_conn = db.raw_connection()
        with self.db_conn.cursor() as cur:
            cur.execute(f"SET search_path TO {SCHEMA_NAME}")

    def close(self) -> None:
        """Release the connection held for the duration of a run."""
        self.db_conn.close()

    def __enter__(self) -> "BaseCollector":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def get_category_members(self, category: str) -> list[dict]:
        """Get all pages in a category"""
        params = {
            "action": "query",
            "format": "json",
            "list": "categorymembers",
            "cmtitle": f"Category:{category}",
            "cmlimit": "500",
            "cmtype": "page",
        }

        pages = []
        while True:
            response = http_client.get_json(self.base_url, params=params)
            if "query" in response:
                pages.extend(response["query"]["categorymembers"])

            if len(pages) >= self.max_places:
                pages = pages[: self.max_places]
                break

            if "continue" in response:
                params["cmcontinue"] = response["continue"]["cmcontinue"]
            else:
                break

        return pages

    def get_page_info(self, page_id: int) -> dict | None:
        """Get detailed information about a page"""
        params = {
            "action": "query",
            "format": "json",
            "pageids": page_id,
            "prop": "info|pageviews|extracts",
            "inprop": "url|length",
            "pvipdays": 30,
            "exintro": True,
            "explaintext": True,
        }

        response = http_client.get_json(self.base_url, params=params)
        if "query" in response and "pages" in response["query"]:
            return response["query"]["pages"][str(page_id)]
        return None

    def normalize_category(self, category_name: str, city_name: str) -> str:
        """Strip the city from a category name and fold it onto an alias."""
        return normalize_category(category_name, city_name)

    def store_category(self, category_name: str) -> int | None:
        """Store category and return its ID"""
        cur = self.db_conn.cursor()
        cur.execute(
            f"""
            INSERT INTO {SCHEMA_NAME}.categories (name)
            VALUES (%s)
            ON CONFLICT (name) DO UPDATE SET name = EXCLUDED.name
            RETURNING id
            """,
            (category_name,),
        )
        category_id = cur.fetchone()[0]
        self.db_conn.commit()
        cur.close()
        return category_id

    def store_place_category(self, place_id: int, category_name: str) -> None:
        """Store place-category relationship with normalized category name"""
        normalized_category = self.normalize_category(category_name, self.city_name)
        category_id = self.store_category(normalized_category)
        cur = self.db_conn.cursor()
        cur.execute(
            f"""
            INSERT INTO {SCHEMA_NAME}.place_categories (place_id, category_id)
            VALUES (%s, %s) ON CONFLICT DO NOTHING
            """,
            (place_id, category_id),
        )
        self.db_conn.commit()
        cur.close()

    def collect_city_places(self) -> list[dict]:
        """Collect places for the city"""
        categories = [
            f"Tourist attractions in {self.city_name}",
            f"Buildings and structures in {self.city_name}",
            f"Museums in {self.city_name}",
            f"Parks in {self.city_name}",
            f"Landmarks in {self.city_name}",
        ]

        all_places = []
        for category in categories:
            try:
                places = [
                    place
                    for place in self.get_category_members(category)
                    if is_place_title(place.get("title", ""))
                ]
                for place in places:
                    place["source_category"] = category
                all_places.extend(places)

                if len(all_places) >= self.max_places:
                    all_places = all_places[: self.max_places]
                    break
            except Exception as e:
                log.warning(f"Error collecting {category}: {str(e)}")
        return all_places

    def process_places(self) -> None:
        """Process and collect data for the city"""
        cur = self.db_conn.cursor()
        places = self.collect_city_places()
        processed_count = 0

        log.info(f"Found {len(places)} places for {self.city_name}")
        outcomes = map_concurrent(
            lambda place: self.get_page_info(place["pageid"]),
            places,
            config.HTTP_MAX_WORKERS,
        )

        for place, outcome in zip(places, outcomes):
            try:
                if not outcome.ok:
                    log.warning(f"Error fetching {place['title']}: {outcome.error}")
                    continue
                page_info = outcome.value
                if not page_info:
                    continue

                pageviews = page_info.get("pageviews") or {}
                views_30 = sum(v for v in pageviews.values() if v is not None)
                length = page_info.get("length") or 0
                wiki_relevance_score = (length / 1000) * 0.3 + (views_30 / 100) * 0.7

                touched = parse_wiki_timestamp(page_info.get("touched"))
                days_since_edit = (
                    (datetime.now(timezone.utc) - touched).days if touched else None
                )

                cur.execute(
                    f"""
                    INSERT INTO {SCHEMA_NAME}.places_of_interest (
                        city_id, title, length, last_touched,
                        pageviews_last_30_days, days_since_edit, full_url,
                        page_id, wiki_relevance_score, description
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (page_id) DO UPDATE SET
                        title = EXCLUDED.title,
                        length = EXCLUDED.length,
                        last_touched = EXCLUDED.last_touched,
                        pageviews_last_30_days = EXCLUDED.pageviews_last_30_days,
                        days_since_edit = EXCLUDED.days_since_edit,
                        full_url = EXCLUDED.full_url,
                        wiki_relevance_score = EXCLUDED.wiki_relevance_score,
                        description = EXCLUDED.description,
                        stale_since = NULL
                    RETURNING id
                """,
                    (
                        self.city_id,
                        place["title"],
                        length,
                        touched,
                        views_30,
                        days_since_edit,
                        page_info.get("fullurl", ""),
                        place["pageid"],
                        wiki_relevance_score,
                        page_info.get("extract", ""),
                    ),
                )

                place_id = cur.fetchone()[0]
                self.store_place_category(place_id, place["source_category"])

                self.db_conn.commit()
                processed_count += 1
                log.info(
                    "Processed %s/%s places for %s",
                    processed_count,
                    len(places),
                    self.city_name,
                )

            except Exception as e:
                self.db_conn.rollback()
                log.warning(f"Error processing place {place['title']}: {str(e)}")
                continue

        cur.close()
        log.info(f"Completed processing {processed_count} places for {self.city_name}")
