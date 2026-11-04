from django.conf import settings
from django.db import models


class Notification(models.Model):
    """One line in a person's notification list (the bell in the top bar)."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications")
    text = models.CharField(max_length=300)
    # Where clicking it leads (a path on this site; may be empty).
    url = models.CharField(max_length=300, blank=True)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["user", "is_read"])]

    def __str__(self):
        return f"{self.user_id}: {self.text}"
