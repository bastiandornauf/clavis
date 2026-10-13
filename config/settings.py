"""Django settings for Clavis."""

from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# User data (database, cloned sources, backups) lives outside the code tree by default.
CLAVIS_DATA_DIR = Path(
    os.environ.get("CLAVIS_DATA_DIR", str(BASE_DIR / "data"))
).expanduser().resolve()
CLAVIS_DATA_DIR.mkdir(parents=True, exist_ok=True)

CLAVIS_SOURCES_DIR = CLAVIS_DATA_DIR / "sources"
CLAVIS_BACKUP_DIR = CLAVIS_DATA_DIR / "backups"
CLAVIS_SOURCES_DIR.mkdir(parents=True, exist_ok=True)
CLAVIS_BACKUP_DIR.mkdir(parents=True, exist_ok=True)

CLAVIS_SOURCE_REPO_URL = os.environ.get(
    "CLAVIS_SOURCE_REPO_URL",
    "https://github.com/OriginalMadman/Ars-Magica-Open-License.git",
)
CLAVIS_SOURCE_REPO_NAME = os.environ.get("CLAVIS_SOURCE_REPO_NAME", "ars-magica-open-license")
CLAVIS_APP_REPO_URL = os.environ.get(
    "CLAVIS_APP_REPO_URL",
    "https://github.com/bastiandornauf/clavis",
)

SECRET_KEY = os.environ.get(
    "DJANGO_SECRET_KEY",
    "dev-only-change-me-clavis-local-secret-key",
)

DEBUG = os.environ.get("DJANGO_DEBUG", "1") == "1"

ALLOWED_HOSTS = [
    host.strip()
    for host in os.environ.get("DJANGO_ALLOWED_HOSTS", "127.0.0.1,localhost").split(",")
    if host.strip()
]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "apps.sources",
    "apps.library",
    "apps.reader",
    "apps.search",
    "apps.annotations",
    "apps.campaigns",
    "apps.catalog",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "config.context_processors.clavis_globals",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": CLAVIS_DATA_DIR / "clavis.sqlite3",
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = CLAVIS_DATA_DIR / "staticfiles"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {
        "console": {"class": "logging.StreamHandler"},
    },
    "root": {
        "handlers": ["console"],
        "level": os.environ.get("CLAVIS_LOG_LEVEL", "INFO"),
    },
}
