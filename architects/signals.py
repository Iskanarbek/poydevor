from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from architects.models import ArchitectProfile, PortfolioImage, PortfolioProject


def _refresh(profile_id):
    profile = ArchitectProfile.objects.filter(pk=profile_id).first()
    if profile is not None:
        profile.recompute_portfolio()


@receiver([post_save, post_delete], sender=PortfolioImage)
def photo_changed(sender, instance, **kwargs):
    project = PortfolioProject.objects.filter(pk=instance.project_id).only("architect_id").first()
    if project is not None:
        _refresh(project.architect_id)


@receiver([post_save, post_delete], sender=PortfolioProject)
def project_changed(sender, instance, **kwargs):
    _refresh(instance.architect_id)
