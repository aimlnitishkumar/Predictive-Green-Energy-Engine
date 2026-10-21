import os
from pathlib import Path
from urllib.parse import urlparse

from django.core.exceptions import ImproperlyConfigured
from django.core.management.utils import get_random_secret_key
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

DEBUG = os.getenv("DJANGO_DEBUG", "false").lower() == "true"
SECRET_KEY = os.getenv("DJANGO_SECRET_KEY")
placeholder_secrets = {"replace-this", "change-me-in-production"}
if not SECRET_KEY or len(SECRET_KEY) < 32 or SECRET_KEY in placeholder_secrets:
    if not DEBUG:
        raise ImproperlyConfigured(
            "Set DJANGO_SECRET_KEY to a strong, unique secret when DEBUG is false."
        )
    SECRET_KEY = get_random_secret_key()
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY") or SECRET_KEY
if len(JWT_SECRET_KEY) < 32 or JWT_SECRET_KEY in placeholder_secrets:
    if not DEBUG:
        raise ImproperlyConfigured(
            "Set JWT_SECRET_KEY to a strong, unique secret when DEBUG is false."
        )
    JWT_SECRET_KEY = SECRET_KEY
ALLOWED_HOSTS = [
    host.strip()
    for host in os.getenv(
        "DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1"
    ).split(",")
    if host.strip()
]
if not DEBUG and "*" in ALLOWED_HOSTS:
    raise ImproperlyConfigured("Set explicit DJANGO_ALLOWED_HOSTS when DEBUG is false.")

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "rest_framework",
    "mrv",
]
MIDDLEWARE = []
ROOT_URLCONF = "config.urls"
TEMPLATES = []
WSGI_APPLICATION = "config.wsgi.application"
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

_database_url = urlparse(
    os.getenv("DATABASE_URL", "postgresql://mrv:mrv@localhost:5432/mrv")
)
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": _database_url.path.lstrip("/"),
        "USER": _database_url.username or "mrv",
        "PASSWORD": _database_url.password or "mrv",
        "HOST": _database_url.hostname or "localhost",
        "PORT": _database_url.port or 5432,
        "CONN_MAX_AGE": 60,
    }
}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
USE_TZ = True
TIME_ZONE = "UTC"

CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/1")
