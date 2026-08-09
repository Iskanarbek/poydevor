from django.conf import settings
from django.db import models


class Style(models.Model):
    name = models.CharField(max_length=50, unique=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Skill(models.Model):
    name = models.CharField(max_length=50, unique=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class ArchitectProfile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="architect_profile")
    bio = models.TextField()
    telegram_username = models.CharField(max_length=50, blank=True)
    avatar = models.ImageField(upload_to="avatars/", blank=True, null=True, max_length=500)
    rating = models.DecimalField(max_digits=3, decimal_places=2, default=0)
    completed_projects_count = models.PositiveIntegerField(default=0)
    styles = models.ManyToManyField(Style, related_name="architects", blank=True)
    skills = models.ManyToManyField(Skill, related_name="architects", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.first_name} {self.user.last_name}"


class PortfolioProject(models.Model):
    architect = models.ForeignKey(ArchitectProfile, on_delete=models.CASCADE, related_name="projects")
    title = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    style = models.ForeignKey(Style, on_delete=models.SET_NULL, null=True, related_name="projects")
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order", "id"]

    def __str__(self):
        return self.title


class PortfolioImage(models.Model):
    project = models.ForeignKey(PortfolioProject, on_delete=models.CASCADE, related_name="images")
    # max_length raised from Django's 100-char default: when Vercel Blob
    # storage is active (see poydevor/storage_backends.py), the "name"
    # stored here is the entire Blob CDN URL, which is well over 100 chars.
    image = models.ImageField(upload_to="portfolio/", max_length=500)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order", "id"]
