from django.contrib.auth.models import AbstractUser
from django.db import models

from accounts.managers import UserManager


class User(AbstractUser):
    username = None

    class Role(models.TextChoices):
        USER = "user", "Foydalanuvchi"
        ARCHITECT = "architect", "Arxitektor"

    phone = models.CharField(max_length=20, unique=True)
    role = models.CharField(max_length=10, choices=Role.choices)
    # Set together with is_active=False when an admin freezes this account
    # (accounts/services.py :: freeze_account). A frozen user can't log in —
    # PhoneBackend and ModelBackend both refuse an inactive user — but the
    # row and all their data stay exactly as they were.
    frozen_at = models.DateTimeField(null=True, blank=True)
    frozen_reason = models.CharField(max_length=255, blank=True)

    USERNAME_FIELD = "phone"
    REQUIRED_FIELDS = ["first_name", "last_name", "role"]

    objects = UserManager()

    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.phone})"
