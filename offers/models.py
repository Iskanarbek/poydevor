from django.db import models
from django.utils import timezone

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
    # Coins the architect paid to apply (0 for invitations and for offers made
    # before this was recorded); used to refund them if the order is deleted.
    coins_spent = models.PositiveIntegerField(default=0)
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


class StudioAssignment(models.Model):
    """How a studio hands an accepted order to one of its own employees.

    Created the moment a studio owner's offer is accepted (offers/services.py ::
    accept_offer). Starts OPEN — visible to every employee of the studio, any of
    whom may claim it — until either an employee claims it or the studio owner
    assigns it to someone specific; both land it on ASSIGNED. The deadline is
    always optional and the owner may set or change it at any point.
    """

    class Status(models.TextChoices):
        OPEN = "open", "Xodimlarga ochiq"
        ASSIGNED = "assigned", "Biriktirilgan"
        DONE = "done", "Bajarildi"

    offer = models.OneToOneField(Offer, on_delete=models.CASCADE, related_name="studio_assignment")
    worker = models.ForeignKey(
        ArchitectProfile, null=True, blank=True, on_delete=models.SET_NULL, related_name="studio_assignments",
    )
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.OPEN)
    # Set by the studio owner; never required.
    deadline = models.DateField(null=True, blank=True)
    assigned_at = models.DateTimeField(null=True, blank=True)
    done_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.offer} — {self.get_status_display()}"

    @property
    def is_overdue(self):
        return bool(self.deadline) and self.status != self.Status.DONE and timezone.now().date() > self.deadline
