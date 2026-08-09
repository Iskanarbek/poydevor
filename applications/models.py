from django.conf import settings
from django.db import models

from architects.models import Style


class Application(models.Model):
    class Status(models.TextChoices):
        OPEN = "open", "Ochiq"
        IN_PROGRESS = "in_progress", "Jarayonda"
        CLOSED = "closed", "Yakunlangan"

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="applications")
    size_m2 = models.PositiveIntegerField(null=True, blank=True)
    rooms_count = models.PositiveSmallIntegerField()
    location = models.CharField(max_length=100)
    interior_style = models.ForeignKey(Style, on_delete=models.SET_NULL, null=True, blank=True, related_name="applications")
    budget = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    # max_length raised from Django's 100-char default to fit full Vercel
    # Blob CDN URLs when that storage backend is active (see
    # poydevor/storage_backends.py).
    plan_pdf = models.FileField(upload_to="plans/", null=True, blank=True, max_length=500)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.location} — {self.rooms_count} xona"
