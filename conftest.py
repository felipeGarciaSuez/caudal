import pytest


@pytest.fixture(autouse=True)
def _disable_user_autoseed(settings):
    """Keep user auto-seeding off by default in tests.

    Most tests create users and assert a clean slate (no wallets/categories), so
    the post_save seeding signal must not fire. Tests that exercise seeding turn
    it back on explicitly with ``settings.SEED_NEW_USERS = True``.
    """
    settings.SEED_NEW_USERS = False
