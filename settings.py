import importlib.machinery
import importlib.util
import os
import sys
from pathlib import Path
from urllib.parse import unquote, urlparse

from django.contrib.messages import constants as message_constants

# --- Flat layout bootstrap --------------------------------------------------
# Every file of this project sits in ONE folder. Django wants the "core" app to be a
# package, so we register this very folder as the package "core": core.models -> models.py,
# core.views -> views.py, core.migrations -> migrations/ (created by makemigrations).
BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))
if "core" not in sys.modules:
    _spec = importlib.machinery.ModuleSpec("core", None, is_package=True)
    _spec.submodule_search_locations = [str(BASE_DIR)]
    sys.modules["core"] = importlib.util.module_from_spec(_spec)

import supabase_client  # noqa: E402  (needs BASE_DIR on sys.path)

# --- Core -------------------------------------------------------------------
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "dev-only-change-me-before-deploying")
DEBUG = os.environ.get("DJANGO_DEBUG", "1") == "1"
if not DEBUG and SECRET_KEY.startswith("dev-only"):
    from django.core.exceptions import ImproperlyConfigured

    raise ImproperlyConfigured("Set DJANGO_SECRET_KEY when DJANGO_DEBUG=0.")
ALLOWED_HOSTS = [h.strip() for h in os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",") if h.strip()]
# Hosts like Render / Railway / Heroku give you an https URL; trust it for CSRF when listed.
CSRF_TRUSTED_ORIGINS = [o.strip() for o in os.environ.get("DJANGO_CSRF_TRUSTED_ORIGINS", "").split(",") if o.strip()]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "core",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    *(["whitenoise.middleware.WhiteNoiseMiddleware"] if importlib.util.find_spec("whitenoise") else []),
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "urls"
WSGI_APPLICATION = "wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR],  # templates live next to this file
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "core.context_processors.notifications",
            ],
        },
    },
]

# --- Database ---------------------------------------------------------------
# Default: SQLite file next to this file (fine locally; on hosts with an ephemeral disk the
# data is LOST on every redeploy). For real deployment set DATABASE_URL to a PostgreSQL URL,
# e.g. Supabase > Connect > "Session pooler" (port 5432; NOT the port-6543 transaction pooler): postgresql://user:pass@host:5432/postgres
def _database_from_url(url):
    u = urlparse(url)
    if u.scheme not in ("postgres", "postgresql"):
        raise ValueError("DATABASE_URL must start with postgres:// or postgresql://")
    return {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": unquote(u.path.lstrip("/")) or "postgres",
        "USER": unquote(u.username or ""),
        "PASSWORD": unquote(u.password or ""),
        "HOST": u.hostname or "",
        "PORT": str(u.port or 5432),
        "CONN_MAX_AGE": 60,
        "DISABLE_SERVER_SIDE_CURSORS": True,  # safe behind PgBouncer / Supabase poolers
        "OPTIONS": {"sslmode": os.environ.get("DATABASE_SSLMODE", "require")},
    }


if os.environ.get("DATABASE_URL"):
    DATABASES = {"default": _database_from_url(os.environ["DATABASE_URL"])}
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": os.environ.get("SQLITE_PATH", str(BASE_DIR / "db.sqlite3")),
        }
    }

# --- Auth -------------------------------------------------------------------
AUTH_USER_MODEL = "core.User"
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "dashboard"
LOGOUT_REDIRECT_URL = "home"
SESSION_COOKIE_AGE = 60 * 60 * 8  # sessions expire after 8 hours

# --- i18n -------------------------------------------------------------------
LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Kolkata"
USE_I18N = True
USE_TZ = True

# --- Static & media ---------------------------------------------------------
# style.css is served by a dedicated view (see urls.py) because there is no static/ folder.
# Django-admin's own CSS/JS is served by WhiteNoise straight from Django's packages.
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
WHITENOISE_USE_FINDERS = True
WHITENOISE_AUTOREFRESH = DEBUG

# --- Supabase Storage -------------------------------------------------------
# Provider photos  -> PUBLIC bucket  (direct image URLs)
# Verification docs -> PRIVATE bucket (only ever streamed through Django after a permission check)
SUPABASE_ENABLED = os.environ.get("USE_SUPABASE", "1") == "1"
SUPABASE_URL = os.environ.get("SUPABASE_URL", supabase_client.DEFAULT_URL)
SUPABASE_PUBLISHABLE_KEY = os.environ.get("SUPABASE_PUBLISHABLE_KEY", supabase_client.DEFAULT_PUBLISHABLE_KEY)
# Optional but STRONGLY recommended on the server: a secret / service_role key lets the private
# bucket stay closed to everyone except this server. Never commit it or put it in templates.
SUPABASE_SECRET_KEY = os.environ.get("SUPABASE_SECRET_KEY", "")
SUPABASE_KEY = SUPABASE_SECRET_KEY or SUPABASE_PUBLISHABLE_KEY
SUPABASE_PUBLIC_BUCKET = os.environ.get("SUPABASE_PUBLIC_BUCKET", "photos")
SUPABASE_PRIVATE_BUCKET = os.environ.get("SUPABASE_PRIVATE_BUCKET", "documents")

# Local fallbacks, used only when USE_SUPABASE=0
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"
PRIVATE_MEDIA_ROOT = BASE_DIR / "private_media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- Email (prints to the console in development) ---------------------------
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
DEFAULT_FROM_EMAIL = "HomeServe <no-reply@homeserve.local>"

# --- Messages ---------------------------------------------------------------
MESSAGE_TAGS = {message_constants.ERROR: "danger"}

# --- Security hardening when DEBUG is off -----------------------------------
if not DEBUG:
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_SSL_REDIRECT = True
    SECURE_HSTS_SECONDS = 31536000
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")  # hosts terminate TLS in front of Django
