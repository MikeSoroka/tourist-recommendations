from __future__ import annotations
from tourist.web import create_app
from tourist.web.models import Place, PlaceImage


def check_database() -> None:
    app = create_app()
    with app.app_context():
        try:
            total_places = Place.query.count()
            total_images = PlaceImage.query.count()
            print(f"Total places: {total_places}")
            print(f"Total images: {total_images}")

            sample_place = Place.query.join(PlaceImage).first()
            if sample_place:
                print("\nSample place with images:")
                print(f"Title: {sample_place.title}")
                print(f"Number of images: {len(sample_place.images)}")
                for img in sample_place.images:
                    print(f"Image filename: {img.image_filename}")
            else:
                print("\nNo places with images found!")

            places_without_images = Place.query.filter(~Place.images.any()).count()
            print(f"\nPlaces without images: {places_without_images}")

        except Exception as e:
            print(f"Error: {str(e)}")


if __name__ == "__main__":
    check_database()
