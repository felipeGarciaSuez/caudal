"""Production settings (Render + Neon Postgres)."""

from .base import *  # noqa: F401, F403
from .base import env

DEBUG = False

# No insecure fallback in prod: fail loudly if SECRET_KEY isn't set. A default
# key would make session cookies forgeable.
SECRET_KEY = env("SECRET_KEY")

ALLOWED_HOSTS = env("ALLOWED_HOSTS")

# Postgres is mandatory in prod — fail loudly if DATABASE_URL is missing.
DATABASES = {"default": env.db("DATABASE_URL")}
DATABASES["default"]["CONN_MAX_AGE"] = 600
DATABASES["default"].setdefault("OPTIONS", {})["sslmode"] = env("DB_SSLMODE", default="require")

# WhiteNoise compressed + hashed static files.
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

# Security hardening behind Render's TLS proxy.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = env.bool("SECURE_SSL_REDIRECT", default=True)
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = env.int("SECURE_HSTS_SECONDS", default=2592000)
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_CONTENT_TYPE_NOSNIFF = True

CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=[])
