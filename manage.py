#!/usr/bin/env python
"""Utilitaire en ligne de commande pour les tâches d'administration Django."""
import os
import sys


def main():
    """Exécute les commandes d'administration."""
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "regivax.settings")
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Impossible d'importer Django. Vérifiez que Django est installé et "
            "que votre environnement virtuel est activé."
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
