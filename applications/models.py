import math
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone

from architects.models import ObjectType, ServiceType, Style


HOUSE_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}


class ApplicationQuerySet(models.QuerySet):
    def visible(self):
        """Orders their owner has not deleted."""
        return self.filter(deleted_at__isnull=True)


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
    # Used when the client's style is not in the list.
    custom_style = models.CharField(max_length=60, blank=True)
    object_type = models.CharField(max_length=20, choices=ObjectType.choices, blank=True)
    service_type = models.CharField(max_length=20, choices=ServiceType.choices, blank=True)
    # The market estimate (US dollars) the client saw and agreed to when posting.
    estimate_min = models.PositiveIntegerField(null=True, blank=True)
    estimate_max = models.PositiveIntegerField(null=True, blank=True)
    budget = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    # What the client wants done; architects read this to decide whether the
    # project is right for them before spending coins on it.
    description = models.TextField(blank=True)
    # max_length raised from Django's 100-char default to fit full Vercel
    # Blob CDN URLs when that storage backend is active (see
    # poydevor/storage_backends.py).
    plan_pdf = models.FileField(upload_to="plans/", null=True, blank=True, max_length=500)
    class Publication(models.TextChoices):
        DRAFT = "draft", "Hali yuborilmagan"
        PUBLIC = "public", "Hammaga ochiq"
        DIRECT = "direct", "Bitta arxitektorga yuborilgan"

    # A new order is saved as a DRAFT nobody can see; its owner then makes it PUBLIC (every architect
    # can apply) or sends it to ONE architect/studio (DIRECT). Never both.
    publication = models.CharField(max_length=10, choices=Publication.choices, default=Publication.PUBLIC)
    sent_to = models.ForeignKey(
        "architects.ArchitectProfile", null=True, blank=True, on_delete=models.SET_NULL, related_name="direct_orders",
    )
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
    def style_label(self):
        return self.interior_style.name if self.interior_style_id else self.custom_style

    @property
    def can_change_audience(self):
        """The owner may take back the choice (public / one architect) until someone has applied or the
        chosen architect has accepted. After that it is too late."""
        if self.status != self.Status.OPEN or self.deleted_at is not None:
            return False
        if self.publication == self.Publication.DRAFT:
            return False
        from offers.models import Offer
        if self.publication == self.Publication.PUBLIC:
            return not self.offers.filter(status__in=[Offer.Status.PENDING, Offer.Status.ACCEPTED, Offer.Status.COMPLETED]).exists()
        return not self.offers.filter(status__in=[Offer.Status.ACCEPTED, Offer.Status.COMPLETED]).exists()

    @property
    def attachments(self):
        """Everything the client attached: the new multi-file uploads, then the old single file."""
        items = [(f.file, f.is_image, f.name) for f in self.files.all()]
        if self.plan_pdf:
            import os
            items.append((self.plan_pdf, self.plan_is_image, os.path.basename(self.plan_pdf.name)))
        return items

    @property
    def plan_is_image(self):
        """The uploaded "house picture" is a photo (as opposed to a PDF)."""
        import os
        return bool(self.plan_pdf) and os.path.splitext(self.plan_pdf.name)[1].lower() in HOUSE_IMAGE_EXTENSIONS


class ApplicationFile(models.Model):
    """One of the photos/files (house pictures, cadastre, plans) the client attached to an order."""

    application = models.ForeignKey(Application, on_delete=models.CASCADE, related_name="files")
    file = models.FileField(upload_to="plans/", max_length=500)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]

    @property
    def is_image(self):
        import os
        return os.path.splitext(self.file.name)[1].lower() in HOUSE_IMAGE_EXTENSIONS

    @property
    def name(self):
        import os
        return os.path.basename(self.file.name)
