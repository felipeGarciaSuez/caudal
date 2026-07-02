"""Base settings shared across environments."""

from pathlib import Path

import environ

# config/settings/base.py -> repo root is three levels up.
BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env(
    DEBUG=(bool, False),
    ALLOWED_HOSTS=(list, ["localhost", "127.0.0.1"]),
)

# Read .env at the repo root if present.
environ.Env.read_env(BASE_DIR / ".env")

SECRET_KEY = env("SECRET_KEY", default="insecure-dev-key-change-me")
DEBUG = env("DEBUG")
ALLOWED_HOSTS = env("ALLOWED_HOSTS")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Third-party
    "axes",  # brute-force protection on login
    # Local apps
    "apps.accounts",
    "apps.wallets",
    "apps.transactions",
    "apps.budgets",
    "apps.savings",
    "apps.imports",
    "apps.dashboard",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    # AxesMiddleware must be last so it sees the final auth outcome.
    "axes.middleware.AxesMiddleware",
]

# Auth backends: AxesStandaloneBackend first so failed logins are throttled,
# then Django's default ModelBackend for the actual credential check.
AUTHENTICATION_BACKENDS = [
    "axes.backends.AxesStandaloneBackend",
    "django.contrib.auth.backends.ModelBackend",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
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
ASGI_APPLICATION = "config.asgi.application"

AUTH_USER_MODEL = "accounts.User"

# Database configured per-environment (see dev.py / prod.py).
DATABASES = {}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# i18n / l10n — es-AR, Córdoba.
LANGUAGE_CODE = env("LANGUAGE_CODE", default="es-ar")
TIME_ZONE = env("TIME_ZONE", default="America/Argentina/Cordoba")
USE_I18N = True
USE_TZ = True

# Static files (WhiteNoise in prod).
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]

MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Auth — branded login at /accounts/login/ (see config.urls).
LOGIN_URL = "/accounts/login/"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/accounts/login/"

# App-wide money defaults.
DEFAULT_CURRENCY = "ARS"

# --- Brute-force protection (django-axes) ------------------------------------
# Lock out an IP after too many failed logins, then auto-release after a while.
# Uses the database handler by default, so lockouts hold across gunicorn workers.
AXES_FAILURE_LIMIT = env.int("AXES_FAILURE_LIMIT", default=5)
AXES_COOLOFF_TIME = env.int("AXES_COOLOFF_HOURS", default=1)  # hours until auto-release
AXES_LOCKOUT_PARAMETERS = ["ip_address"]
AXES_RESET_ON_SUCCESS = True
# Behind Render's proxy the real client IP is in X-Forwarded-For.
AXES_IPWARE_PROXY_COUNT = env.int("AXES_PROXY_COUNT", default=0) or None
AXES_IPWARE_META_PRECEDENCE_ORDER = ["HTTP_X_FORWARDED_FOR", "REMOTE_ADDR"]

# Admin URL is configurable so it can be moved off the well-known /admin/ path
# in prod (set ADMIN_URL to something hard to guess; keep the trailing slash).
ADMIN_URL = env("ADMIN_URL", default="admin/")
