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

    USERNAME_FIELD = "phone"
    REQUIRED_FIELDS = ["first_name", "last_name", "role"]

    objects = UserManager()

    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.phone})"
