from django.conf import settings
from django.db import models

from architects.models import ArchitectProfile
from offers.models import Offer


class Review(models.Model):
    offer = models.OneToOneField(Offer, on_delete=models.CASCADE, related_name="review")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="reviews_written")
    architect = models.ForeignKey(ArchitectProfile, on_delete=models.CASCADE, related_name="reviews")
    rating = models.PositiveSmallIntegerField()
    comment = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
