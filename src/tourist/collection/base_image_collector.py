from __future__ import annotations
import logging
import os
from PIL import Image, UnidentifiedImageError
from io import BytesIO

import urllib.parse

from tourist.config import SCHEMA_NAME
import requests

from tourist import config
from tourist import db
from tourist import http_client
from tourist.text_utils import is_photo_title
from tourist.concurrency import map_concurrent

log = logging.getLogger(__name__)


class BaseImageCollector:

    MAX_IMAGES_PER_PLACE = 5
    MIN_WIDTH = 400
    MIN_HEIGHT = 300

    def __init__(self, city_id: int, city_name: str) -> None:
        self.city_id = city_id
        self.city_name = city_name
        self.base_url = "https://en.wikipedia.org/w/api.php"
        self.image_dir = "data/images"
        os.makedirs(self.image_dir, exist_ok=True)

        self.db_conn = db.raw_connection()
        with self.db_conn.cursor() as cur:
            cur.execute(f"SET search_path TO {SCHEMA_NAME}")

    def close(self) -> None:
        """Release the connection held for the duration of a run."""
        self.db_conn.close()

    def __enter__(self) -> "BaseImageCollector":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def get_page_images(self, page_title: str) -> list[dict]:
        """Get candidate photographs for a page, lead image first.

        The page's designated lead image is the best single photograph of the
        place, so it is requested explicitly and placed ahead of the rest.
        """
        params = {
            "action": "query",
            "format": "json",
            "titles": page_title,
            "prop": "images|pageimages",
            "imlimit": "50",
            "piprop": "name",
        }

        response = http_client.get_json(self.base_url, params=params)
        if "query" not in response or "pages" not in response["query"]:
            return []

        page = next(iter(response["query"]["pages"].values()))
        candidates = [
            img
            for img in page.get("images", [])
            if is_photo_title(img.get("title", ""))
        ]

        lead = page.get("pageimage")
        if lead:
            lead_title = f"File:{lead}"
            candidates = [img for img in candidates if img.get("title") != lead_title]
            candidates.insert(0, {"title": lead_title, "is_lead": True})

        return candidates

    def get_image_url(
        self, image_title: str
    ) -> tuple[str | None, str | None, tuple[int, int]]:
        """Get the URL, mime type and pixel size for an image."""
        params = {
            "action": "query",
            "format": "json",
            "titles": image_title,
            "prop": "imageinfo",
            "iiprop": "url|mime|size",
        }

        response = http_client.get_json(self.base_url, params=params)
        if "query" in response and "pages" in response["query"]:
            page = next(iter(response["query"]["pages"].values()))
            if "imageinfo" in page and page["imageinfo"]:
                info = page["imageinfo"][0]
                size = (int(info.get("width", 0)), int(info.get("height", 0)))
                return info.get("url"), info.get("mime"), size
        return None, None, (0, 0)

    def is_valid_image(
        self, url: str | None, mime_type: str | None, size: tuple[int, int]
    ) -> bool:
        """Whether the file is a photograph worth downloading.

        Icons and badges are small; anything narrower than MIN_WIDTH or shorter
        than MIN_HEIGHT is rejected, as are vector and animated formats.
        """
        if not url or not mime_type:
            return False

        if mime_type not in {"image/jpeg", "image/png"}:
            return False

        parsed_url = urllib.parse.urlparse(url)
        ext = os.path.splitext(parsed_url.path)[1].lower()
        if ext not in {".jpg", ".jpeg", ".png"}:
            return False

        width, height = size
        return width >= self.MIN_WIDTH and height >= self.MIN_HEIGHT

    def download_image(self, url: str, place_id: int, image_number: int) -> str | None:
        """Download and save an image"""
        try:

            response = http_client.get(url)
            response.raise_for_status()

            try:
                img = Image.open(BytesIO(response.content))
            except UnidentifiedImageError:
                log.warning(f"Error: Could not identify image format for URL: {url}")
                return None
            except Exception as e:
                log.warning(f"Error opening image from URL {url}: {str(e)}")
                return None

            if not hasattr(img, "format") or not img.format:
                log.warning(f"Error: Invalid image format for URL: {url}")
                return None

            if img.mode in ("RGBA", "P"):
                try:
                    img = img.convert("RGB")
                except Exception as e:
                    log.warning(f"Error converting image to RGB: {str(e)}")
                    return None

            try:
                max_size = 800
                if max(img.size) > max_size:
                    ratio = max_size / max(img.size)
                    new_size = tuple(int(dim * ratio) for dim in img.size)
                    img = img.resize(new_size, Image.Resampling.LANCZOS)
            except Exception as e:
                log.warning(f"Error resizing image: {str(e)}")
                return None

            try:
                filename = f"{place_id}_{image_number}.jpg"
                filepath = os.path.join(self.image_dir, filename)
                img.save(filepath, "JPEG", quality=85)
                return filename
            except Exception as e:
                log.warning(f"Error saving image: {str(e)}")
                return None

        except requests.RequestException as e:
            log.warning(f"Error downloading image from URL {url}: {str(e)}")
            return None
        except Exception as e:
            log.warning(f"Unexpected error processing image from URL {url}: {str(e)}")
            return None

    def collect_for_place(self, place: tuple[int, str]) -> list[tuple[str, str, bool]]:
        """Download this place's images, returning (filename, original title).

        Runs on a worker thread, so it performs no database work; the caller
        writes the rows from a single thread on the shared connection.
        """
        place_id, title = place
        saved: list[tuple[str, str, bool]] = []

        for img in self.get_page_images(title):
            if len(saved) >= self.MAX_IMAGES_PER_PLACE:
                break

            image_url, mime_type, size = self.get_image_url(img["title"])
            if not self.is_valid_image(image_url, mime_type, size):
                continue

            filename = self.download_image(image_url, place_id, len(saved))
            if filename:
                saved.append((filename, img["title"], bool(img.get("is_lead"))))

        return saved

    def collect_images(self) -> None:
        """Collect images for the city's places.

        A place's rows are replaced, not appended to, so re-running the
        collector refreshes the gallery instead of duplicating it. The replace
        happens only once new images have actually been downloaded; a place
        whose fetch failed keeps what it had.
        """
        cur = self.db_conn.cursor()

        cur.execute(
            f"""
            SELECT id, title
            FROM {SCHEMA_NAME}.places_of_interest
            WHERE city_id = %s
        """,
            (self.city_id,),
        )
        places = cur.fetchall()

        log.info(
            f"Found {len(places)} places to collect images for in {self.city_name}"
        )
        outcomes = map_concurrent(
            self.collect_for_place, places, config.HTTP_MAX_WORKERS
        )

        for (place_id, title), outcome in zip(places, outcomes):
            if not outcome.ok:
                log.warning("Error collecting images for %s: %s", title, outcome.error)
                continue
            saved = outcome.value or []
            if not saved:
                continue
            try:
                cur.execute(
                    f"DELETE FROM {SCHEMA_NAME}.place_images WHERE place_id = %s",
                    (place_id,),
                )
                cur.executemany(
                    f"""
                    INSERT INTO {SCHEMA_NAME}.place_images
                        (place_id, image_filename, original_title, is_lead)
                    VALUES (%s, %s, %s, %s)
                    """,
                    [(place_id, f, t, lead) for f, t, lead in saved],
                )
                self.db_conn.commit()
            except Exception as e:
                self.db_conn.rollback()
                log.warning("Error storing images for %s: %s", title, e)

        cur.close()
        log.info(f"Image collection completed for {self.city_name}")
