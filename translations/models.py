from django.db import models


class ContentTranslation(models.Model):
    """A machine translation of something a person wrote (a project description, a bio...), kept so
    the same text is only ever translated once per language."""

    source_hash = models.CharField(max_length=64)
    lang = models.CharField(max_length=5)
    text = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["source_hash", "lang"], name="one_translation_per_text_and_language")]
        indexes = [models.Index(fields=["source_hash", "lang"])]
