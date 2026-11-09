"""Configuration WSGI pour le projet RegiVax."""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "regivax.settings")

application = get_wsgi_application()
