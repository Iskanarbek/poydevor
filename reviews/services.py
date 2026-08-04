from decimal import Decimal

from django.db import transaction
from django.db.models import Avg

from reviews.models import Review
from architects.models import ArchitectProfile


@transaction.atomic
def submit_review(offer, user, rating: int, comment: str) -> Review:
    review = Review.objects.create(
        offer=offer, user=user, architect=offer.architect, rating=rating, comment=comment,
    )
    locked_architect = ArchitectProfile.objects.select_for_update().get(pk=offer.architect.pk)
    avg = locked_architect.reviews.aggregate(avg=Avg("rating"))["avg"]
    locked_architect.rating = Decimal(str(round(avg, 2)))
    locked_architect.save(update_fields=["rating"])
    return review
