"""Signals for the accounts app."""

from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import User


@receiver(post_save, sender=User, dispatch_uid="accounts.seed_new_user")
def seed_new_user(sender, instance, created, raw=False, **kwargs):
    """Seed base wallets/categories/rules for a freshly created user.

    Covers every creation path (createsuperuser, admin, ensure_superuser).
    Gated by ``settings.SEED_NEW_USERS`` so the test suite -- which creates many
    users and asserts a clean slate -- can turn it off. Skips fixture loads
    (``raw=True``) and updates (``created=False``).
    """
    if raw or not created:
        return
    if not getattr(settings, "SEED_NEW_USERS", True):
        return
    # Imported lazily: seeding pulls in models from other apps, so keep it out of
    # module import time (this module is imported from AppConfig.ready()).
    from .seeding import seed_user

    seed_user(instance)
