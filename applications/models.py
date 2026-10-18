import math
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone

from architects.models import Style


HOUSE_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}


class ApplicationQuerySet(models.QuerySet):
    def visible(self):
        """Orders their owner has not deleted."""
        return self.filter(deleted_at__isnull=True)

    def stale(self):
        """Open orders whose owner hasn't confirmed they are still searching in time."""
        cutoff = timezone.now() - timedelta(days=settings.ORDER_LIFETIME_DAYS)
        return self.filter(status="open", deleted_at__isnull=True, last_confirmed_at__lt=cutoff)


class Application(models.Model):
    class Status(models.TextChoices):
        OPEN = "open", "Ochiq"
        IN_PROGRESS = "in_progress", "Jarayonda"
        CLOSED = "closed", "Yakunlangan"
        CANCELLED = "cancelled", "Bekor qilingan"

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="applications")
    size_m2 = models.PositiveIntegerField(null=True, blank=True)
    rooms_count = models.PositiveSmallIntegerField()
    location = models.CharField(max_length=100)
    interior_style = models.ForeignKey(Style, on_delete=models.SET_NULL, null=True, blank=True, related_name="applications")
    budget = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    # What the client wants done; architects read this to decide whether the
    # project is right for them before spending coins on it.
    description = models.TextField(blank=True)
    # max_length raised from Django's 100-char default to fit full Vercel
    # Blob CDN URLs when that storage backend is active (see
    # poydevor/storage_backends.py).
    plan_pdf = models.FileField(upload_to="plans/", null=True, blank=True, max_length=500)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN)
    created_at = models.DateTimeField(auto_now_add=True)
    # Set when the owner deletes the order. The row is kept so architects'
    # records of finished work stay intact; it just disappears for the owner.
    deleted_at = models.DateTimeField(null=True, blank=True)
    # An open order expires ORDER_LIFETIME_DAYS after this moment (its posting, or the
    # last time the owner confirmed they are still searching for an architect).
    last_confirmed_at = models.DateTimeField(default=timezone.now)
    # True when the order was removed by the expiry rule rather than by its owner.
    auto_deleted = models.BooleanField(default=False)

    objects = ApplicationQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.location} — {self.rooms_count} xona"

    @property
    def plan_is_image(self):
        """The uploaded "house picture" is a photo (as opposed to a PDF)."""
        import os
        return bool(self.plan_pdf) and os.path.splitext(self.plan_pdf.name)[1].lower() in HOUSE_IMAGE_EXTENSIONS

    @property
    def expires_at(self):
        return self.last_confirmed_at + timedelta(days=settings.ORDER_LIFETIME_DAYS)

    @property
    def days_left(self):
        """Whole days until an open order is deleted automatically (0 = today)."""
        return max(0, math.ceil((self.expires_at - timezone.now()).total_seconds() / 86400))

    @property
    def renewable_from(self):
        """The moment the owner may confirm they are still searching."""
        return self.last_confirmed_at + timedelta(days=settings.ORDER_RENEW_AFTER_DAYS)

    @property
    def can_renew(self):
        return self.status == self.Status.OPEN and timezone.now() >= self.renewable_from

    @property
    def days_until_renew(self):
        """Whole days before the confirm button unlocks (0 once it is available)."""
        return max(0, math.ceil((self.renewable_from - timezone.now()).total_seconds() / 86400))

    @property
    def expiring_soon(self):
        return self.status == self.Status.OPEN and self.days_left <= settings.ORDER_WARNING_DAYS
