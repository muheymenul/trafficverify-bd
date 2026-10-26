"""
Django settings for TrafficVerify BD (DEMO / educational project).

This is NOT an official Bangladesh Police or BRTA system.
All data in this project is fictional.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# ---------------------------------------------------------------
# Paths
# ---------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent

# Read secrets from the .env file (this file is NOT uploaded to GitHub)
load_dotenv(BASE_DIR / ".env")

# ---------------------------------------------------------------
# Core security settings (development values come from .env)
# ---------------------------------------------------------------
SECRET_KEY = os.environ["DJANGO_SECRET_KEY"]

DEBUG = os.environ.get("DJANGO_DEBUG", "False") == "True"

ALLOWED_HOSTS = [
    host.strip()
    for host in os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")
    if host.strip()
]

# ---------------------------------------------------------------
# Applications
# ---------------------------------------------------------------
INSTALLED_APPS = [
    # Django built-in apps
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Our apps
    "accounts",
    "dashboard",
    "vehicles",
    "licences",
    "verification",
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
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# ---------------------------------------------------------------
# Database (SQLite for the first prototype; PostgreSQL later)
# ---------------------------------------------------------------
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

# ---------------------------------------------------------------
# Custom user model (MUST be set before the first migration)
# ---------------------------------------------------------------
AUTH_USER_MODEL = "accounts.User"

# ---------------------------------------------------------------
# Password validation
# ---------------------------------------------------------------
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# ---------------------------------------------------------------
# Language and time
# ---------------------------------------------------------------
LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Dhaka"
USE_I18N = True
USE_TZ = True

# ---------------------------------------------------------------
# Static and media files
# ---------------------------------------------------------------
STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]

MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

# ---------------------------------------------------------------
# Misc
# ---------------------------------------------------------------
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# ---------------------------------------------------------------
# Login / logout / sessions
# ---------------------------------------------------------------
LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "dashboard:home"
LOGOUT_REDIRECT_URL = "accounts:login"

SESSION_COOKIE_AGE = 60 * 60 * 2          # login expires after 2 hours without activity
SESSION_SAVE_EVERY_REQUEST = True         # every page visit extends the 2 hours
SESSION_EXPIRE_AT_BROWSER_CLOSE = True    # closing the browser logs the user out
SESSION_COOKIE_HTTPONLY = True            # JavaScript can not read the session cookie
SESSION_COOKIE_SAMESITE = "Lax"

PASSWORD_RESET_TIMEOUT = 60 * 60          # reset link works for 1 hour

# ---------------------------------------------------------------
# Email (DEVELOPMENT ONLY)
# The "console" backend prints emails in the Terminal.
# It does NOT send real emails.
# ---------------------------------------------------------------
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
DEFAULT_FROM_EMAIL = "TrafficVerify BD Demo <noreply@trafficverify.local>"

# ---------------------------------------------------------------
# Make Django message colours match Bootstrap colours
# ---------------------------------------------------------------
from django.contrib.messages import constants as messages_constants  # noqa: E402

MESSAGE_TAGS = {messages_constants.ERROR: "danger"}


# ---------------------------------------------------------------
# Security settings that are safe in development AND production
# ---------------------------------------------------------------
X_FRAME_OPTIONS = "DENY"                 # the site can not be shown inside another site's frame
SECURE_CONTENT_TYPE_NOSNIFF = True       # browsers must trust our content types
SECURE_REFERRER_POLICY = "same-origin"   # other sites do not see our page addresses

# ---------------------------------------------------------------
# PRODUCTION security (only switched on with DJANGO_PRODUCTION=True)
# These need HTTPS. Never turn them on for plain http://127.0.0.1 testing.
# ---------------------------------------------------------------
PRODUCTION = os.environ.get("DJANGO_PRODUCTION", "False") == "True"

if PRODUCTION:
    from django.core.exceptions import ImproperlyConfigured

    if DEBUG:
        raise ImproperlyConfigured(
            "DJANGO_DEBUG must be False when DJANGO_PRODUCTION is True."
        )

    SECURE_SSL_REDIRECT = True           # http:// is redirected to https://
    SESSION_COOKIE_SECURE = True         # the login cookie travels only over https
    CSRF_COOKIE_SECURE = True            # the CSRF cookie travels only over https
    SECURE_HSTS_SECONDS = 3600           # browsers remember "https only" for 1 hour