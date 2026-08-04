from django.db import transaction
from django.db.models import Avg

from reviews.models import Review


@transaction.atomic
def submit_review(offer, user, rating: int, comment: str) -> Review:
    review = Review.objects.create(
        offer=offer, user=user, architect=offer.architect, rating=rating, comment=comment,
    )
    architect = offer.architect
    avg = architect.reviews.aggregate(avg=Avg("rating"))["avg"]
    architect.rating = round(avg, 2)
    architect.save(update_fields=["rating"])
    return review
