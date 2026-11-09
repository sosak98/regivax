"""Configuration Django du projet RegiVax."""

import os
from pathlib import Path

from registre.apercu import est_mode_apercu

BASE_DIR = Path(__file__).resolve().parent.parent

APERCU = est_mode_apercu()

DEBUG = (
    os.environ.get("DEBUG", "False" if APERCU else "True").strip().lower()
    in ("1", "true", "oui", "yes")
)

SECRET_KEY = os.environ.get(
    "SECRET_KEY",
    "regivax-cle-locale-de-developpement-a-ne-pas-utiliser-en-production",
)

_allowed_hosts_env = os.environ.get("ALLOWED_HOSTS", "").strip()
if _allowed_hosts_env:
    ALLOWED_HOSTS = [
        hote.strip() for hote in _allowed_hosts_env.split(",") if hote.strip()
    ]
else:
    ALLOWED_HOSTS = ["127.0.0.1", "localhost"]

_csrf_origins_env = os.environ.get("CSRF_TRUSTED_ORIGINS", "").strip()
if _csrf_origins_env:
    CSRF_TRUSTED_ORIGINS = [
        origine.strip()
        for origine in _csrf_origins_env.split(",")
        if origine.strip()
    ]
else:
    CSRF_TRUSTED_ORIGINS = []

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "registre.apps.RegistreConfig",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
]

if APERCU:
    MIDDLEWARE.append("registre.apercu.ApercuMiddleware")
    SESSION_COOKIE_SAMESITE = "None"
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SAMESITE = "None"
    CSRF_COOKIE_SECURE = True
else:
    MIDDLEWARE.append("django.middleware.clickjacking.XFrameOptionsMiddleware")
    X_FRAME_OPTIONS = "DENY"
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_REFERRER_POLICY = "same-origin"
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    CSRF_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = os.environ.get("SESSION_COOKIE_SECURE", "0") == "1"
    CSRF_COOKIE_SECURE = os.environ.get("CSRF_COOKIE_SECURE", "0") == "1"

ROOT_URLCONF = "regivax.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "registre.apercu.contexte_apercu",
            ],
        },
    },
]

WSGI_APPLICATION = "regivax.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": Path(os.environ.get("REGIVAX_DB_PATH", BASE_DIR / "db.sqlite3")),
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

LANGUAGE_CODE = "fr-fr"
TIME_ZONE = "Africa/Porto-Novo"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedStaticFilesStorage",
    },
}

LOGIN_URL = "/connexion/"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/connexion/"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
