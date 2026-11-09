"""Configuration de l'application registre."""

from django.apps import AppConfig


class RegistreConfig(AppConfig):
    """Configuration Django de l'application du registre vaccinal."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "registre"
    verbose_name = "Registre vaccinal"
