from django.apps import AppConfig


class TrazabilidadConfig(AppConfig):
    name = "trazabilidad"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        from . import signals  # noqa
