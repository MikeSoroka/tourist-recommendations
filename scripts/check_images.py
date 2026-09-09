from __future__ import annotations
from tourist.web import create_app
from tourist.web.models import Place, PlaceImage
import os


def check_images() -> None:
    app = create_app()
    with app.app_context():
        try:

            images_dir = app.config["IMAGES_DIR"]
            print(f"Images directory: {images_dir}")
            print(f"Directory exists: {os.path.exists(images_dir)}")

            sample_place = Place.query.join(PlaceImage).first()
            if sample_place:
                print(f"\nChecking images for place: {sample_place.title}")
                for img in sample_place.images:
                    file_path = os.path.join(images_dir, img.image_filename)
                    exists = os.path.isfile(file_path)
                    print(
                        f"Image {img.image_filename}: {'Found' if exists else 'Not found'} at {file_path}"
                    )

            total_images = PlaceImage.query.count()
            existing_images = 0
            missing_images = []

            for img in PlaceImage.query.all():
                file_path = os.path.join(images_dir, img.image_filename)
                if os.path.isfile(file_path):
                    existing_images += 1
                else:
                    missing_images.append(img.image_filename)

            print(f"\nTotal images in database: {total_images}")
            print(f"Images found on disk: {existing_images}")
            print(f"Missing images: {len(missing_images)}")
            if missing_images:
                print("First few missing images:")
                for filename in missing_images[:5]:
                    print(f"- {filename}")

        except Exception as e:
            print(f"Error: {str(e)}")


if __name__ == "__main__":
    check_images()
