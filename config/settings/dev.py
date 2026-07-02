"""Development settings.

If DATABASE_URL is empty we fall back to SQLite so the app runs locally
without a Postgres instance. Prod always uses Postgres (Neon) via DATABASE_URL.
"""

from .base import *  # noqa: F401, F403
from .base import BASE_DIR, env

DEBUG = True

# Permissive in local dev so it works from the Windows browser / WSL IP / phone
# on the LAN without fighting DisallowedHost. Prod pins ALLOWED_HOSTS.
ALLOWED_HOSTS = ["*"]

_database_url = env("DATABASE_URL", default="")
if _database_url:
    DATABASES = {"default": env.db_url_config(_database_url)}
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}
