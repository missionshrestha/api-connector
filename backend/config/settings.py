# backend/config/settings.py
from pathlib import Path

import environ

# ─── Paths ────────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent

# ─── Environment ──────────────────────────────────────────────────────────────
env = environ.Env()
environ.Env.read_env(BASE_DIR / ".env")

# ─── Core Security ────────────────────────────────────────────────────────────
# No default — missing DJANGO_SECRET_KEY raises ImproperlyConfigured at startup.
SECRET_KEY = env("DJANGO_SECRET_KEY")

# DEBUG defaults False. Only .env sets it True.
DEBUG = env.bool("DEBUG", default=False)

ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])

# ─── Applications ─────────────────────────────────────────────────────────────
INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.admin",
    # Third-party
    "rest_framework",
    "corsheaders",
    # Local
    "api_connector",
]

# ─── Middleware ───────────────────────────────────────────────────────────────
# CorsMiddleware MUST be first — before SecurityMiddleware.
# Any other position causes CORS preflight to fail silently as "Network Error"
# in the browser with no Django log entry.
MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
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
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# ─── Database ─────────────────────────────────────────────────────────────────
# SQLite is NOT supported. DATABASE_URL must point to PostgreSQL.
# JSONField uses JSONB on PostgreSQL. SQLite stores JSON as TEXT — queries that
# work on SQLite silently fail on PostgreSQL. This difference surfaces only in
# Phase 5+ query filtering and is extremely hard to diagnose retroactively.
DATABASES = {"default": env.db("DATABASE_URL")}

# ─── Internationalisation ─────────────────────────────────────────────────────
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True  # Required. Phase 1 timestamp comparisons depend on TZ-aware datetimes.

# ─── Static files ─────────────────────────────────────────────────────────────
STATIC_URL = "static/"

# ─── Primary key type ─────────────────────────────────────────────────────────
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ─── CORS ─────────────────────────────────────────────────────────────────────
# Must be a list. Do NOT use CORS_ALLOW_ALL_ORIGINS = True, even in development.
CORS_ALLOWED_ORIGINS = env.list(
    "CORS_ALLOWED_ORIGINS",
    default=["http://localhost:5173"],
)

# ─── Django REST Framework ────────────────────────────────────────────────────
REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
    ],
    "DEFAULT_PARSER_CLASSES": [
        "rest_framework.parsers.JSONParser",
    ],
    # TODO Phase 1: set to 'api_connector.exceptions.custom_exception_handler'
    # "EXCEPTION_HANDLER": "api_connector.exceptions.custom_exception_handler",
}

# ─── Encryption ───────────────────────────────────────────────────────────────
# Empty string default — Phase 1's EncryptionService validates non-empty on first
# use. A non-empty default here would silently mask misconfigured production.
ENCRYPTION_KEY = env("ENCRYPTION_KEY", default="")

# ─── HTTPS ────────────────────────────────────────────────────────────────────
SECURE_SSL_REDIRECT = env.bool("SECURE_SSL_REDIRECT", default=False)

# ─── Logging ──────────────────────────────────────────────────────────────────
# TODO Phase 1: configure structured logging with method/url/status/latency fields