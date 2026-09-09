from __future__ import annotations
from tourist.web import create_app
from tourist.web.models import Place, SimilarPlace, ImageBasedSimilarPlace


def check_similarities() -> None:
    app = create_app()
    with app.app_context():
        try:

            total_structural = SimilarPlace.query.count()
            print(f"Total structural similarities: {total_structural}")

            total_image_based = ImageBasedSimilarPlace.query.count()
            print(f"Total image-based similarities: {total_image_based}")

            sample_place = Place.query.first()
            if sample_place:
                print(
                    f"\nChecking similarities for place: {sample_place.title} (ID: {sample_place.id})"
                )

                structural = SimilarPlace.query.filter_by(
                    main_place_id=sample_place.id
                ).all()
                print(f"\nStructural similarities: {len(structural)}")
                for sim in structural[:5]:
                    print(
                        f"- {sim.similar_place.title} (Score: {sim.similarity_score:.2f})"
                    )

                intra_city = ImageBasedSimilarPlace.query.filter_by(
                    source_id=sample_place.id, similarity_type="intra_city"
                ).all()
                print(f"\nImage-based similarities (same city): {len(intra_city)}")
                for sim in intra_city[:5]:
                    print(
                        f"- {sim.target_place.title} (Score: {sim.similarity_score:.2f})"
                    )

                inter_city = ImageBasedSimilarPlace.query.filter_by(
                    source_id=sample_place.id, similarity_type="inter_city"
                ).all()
                print(f"\nImage-based similarities (other cities): {len(inter_city)}")
                for sim in inter_city[:5]:
                    print(
                        f"- {sim.target_place.title} (Score: {sim.similarity_score:.2f})"
                    )

        except Exception as e:
            print(f"Error: {str(e)}")


if __name__ == "__main__":
    check_similarities()
