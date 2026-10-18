from django.apps import AppConfig


class ArchitectsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'architects'

    def ready(self):
        from architects import signals  # noqa: F401  (connects the portfolio signals)
