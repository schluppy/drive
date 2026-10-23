"""Einstellungen für Drive – Fahrtenbuch, Tankfüllungen und Kosten für Familien.

Konfiguration über Umgebungsvariablen, damit dasselbe Image lokal (SQLite)
und auf dem Server (PostgreSQL) läuft.
"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "nur-fuer-entwicklung-aendern")
DEBUG = os.environ.get("DJANGO_DEBUG", "1") == "1"
ALLOWED_HOSTS = os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "konten",
    "fahrzeuge",
    "logbuch",
    "auswertung",
    "importe",
    "portal",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "konten.middleware.zuletzt_aktiv",
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
                "portal.kontext.fahrzeugauswahl",
            ],
            "builtins": ["portal.templatetags.drive"],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

if os.environ.get("POSTGRES_DB"):
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.environ["POSTGRES_DB"],
            "USER": os.environ.get("POSTGRES_USER", "drive"),
            "PASSWORD": os.environ.get("POSTGRES_PASSWORD", ""),
            "HOST": os.environ.get("POSTGRES_HOST", "db"),
            "PORT": os.environ.get("POSTGRES_PORT", "5432"),
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

# Eigenes Benutzermodell: Login per E-Mail, keine Benutzernamen, keine Passwörter.
AUTH_USER_MODEL = "konten.Person"

# Sitzung bleibt nach Magic-Link-Login 90 Tage bestehen (Handy an der Tankstelle).
SESSION_COOKIE_AGE = 60 * 60 * 24 * 90
MAGIC_LINK_GUELTIGKEIT_MINUTEN = 15
# Einladungen in eine Familie gelten länger als ein Anmeldelink
EINLADUNG_GUELTIGKEIT_TAGE = 7

LANGUAGE_CODE = "de-de"
TIME_ZONE = "Europe/Berlin"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_ROOT = Path(os.environ.get("MEDIA_ROOT", BASE_DIR / "media"))
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage" if DEBUG
                    else "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

# Uploads: Fahrzeugfotos und DriveNote-Backups (mit Fotos einige MB)
DATA_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024
IMPORT_MAX_MB = 60

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

EMAIL_BACKEND = os.environ.get(
    "EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend"
)
DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", "drive@localhost")
SERVER_EMAIL = DEFAULT_FROM_EMAIL
MSMTP_BINARY = os.environ.get("MSMTP_BINARY", "/usr/bin/msmtp")
MSMTP_ACCOUNT = os.environ.get("MSMTP_ACCOUNT", "drive")

# Hinter einem Reverse Proxy: echte Client-IP aus X-Real-IP (für die Begrenzung der Anmeldelinks)
HINTER_PROXY = os.environ.get("HINTER_PROXY", "0") == "1"

# Absolute Adresse der Anwendung für Links in E-Mails
BASIS_URL = os.environ.get("BASIS_URL", "http://localhost:8000").rstrip("/")

LOGIN_URL = "portal:anmelden"
LOGIN_REDIRECT_URL = "portal:start"

# Betreiber für den Datenschutzhinweis (/datenschutz/)
BETREIBER_NAME = os.environ.get("BETREIBER_NAME", "")
BETREIBER_EMAIL = os.environ.get("BETREIBER_EMAIL", "")

# Erinnerungen: so viele Tage bzw. Kilometer vorher kommt eine Mail
ERINNERUNG_TAGE_VORHER = 14
ERINNERUNG_KM_VORHER = 500

if not DEBUG:
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    CSRF_TRUSTED_ORIGINS = [BASIS_URL]
    SECURE_HSTS_SECONDS = 60 * 60 * 24 * 365
    SECURE_CONTENT_TYPE_NOSNIFF = True

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": "WARNING"},
}
