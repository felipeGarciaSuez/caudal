import pytest


@pytest.fixture(autouse=True)
def _disable_user_autoseed(settings):
    """Keep user auto-seeding off by default in tests.

    Most tests create users and assert a clean slate (no wallets/categories), so
    the post_save seeding signal must not fire. Tests that exercise seeding turn
    it back on explicitly with ``settings.SEED_NEW_USERS = True``.
    """
    settings.SEED_NEW_USERS = False


@pytest.fixture(autouse=True)
def _no_social_providers(settings):
    """Isolate tests from the developer's .env: no Google login unless a test
    configures it. Otherwise a local .env with real OAuth credentials would leak
    the "Continuar con Google" button into unrelated login-page assertions."""
    settings.SOCIALACCOUNT_PROVIDERS = {}
