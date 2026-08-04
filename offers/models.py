from django.db import models

from applications.models import Application
from architects.models import ArchitectProfile


class Offer(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Kutilmoqda"
        ACCEPTED = "accepted", "Qabul qilindi"
        REJECTED = "rejected", "Rad etildi"
        COMPLETED = "completed", "Yakunlandi"

    class Source(models.TextChoices):
        ARCHITECT_APPLIED = "architect_applied", "Arxitektor o'zi qatnashdi"
        USER_INVITED = "user_invited", "Foydalanuvchi taklif qildi"

    application = models.ForeignKey(Application, on_delete=models.CASCADE, related_name="offers")
    architect = models.ForeignKey(ArchitectProfile, on_delete=models.CASCADE, related_name="offers")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    source = models.CharField(max_length=20, choices=Source.choices)
    created_at = models.DateTimeField(auto_now_add=True)
    decided_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["application", "architect"],
                condition=models.Q(status="pending"),
                name="unique_pending_offer_per_application_architect",
            ),
        ]
