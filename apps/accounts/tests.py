import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.utils import timezone

pytestmark = pytest.mark.django_db

User = get_user_model()


def test_ensure_superuser_noop_without_env(monkeypatch):
    monkeypatch.delenv("DJANGO_SUPERUSER_USERNAME", raising=False)
    monkeypatch.delenv("DJANGO_SUPERUSER_PASSWORD", raising=False)
    call_command("ensure_superuser")
    assert User.objects.count() == 0


def test_ensure_superuser_creates_from_env(monkeypatch):
    monkeypatch.setenv("DJANGO_SUPERUSER_USERNAME", "felipe")
    monkeypatch.setenv("DJANGO_SUPERUSER_PASSWORD", "a-strong-password")
    call_command("ensure_superuser")
    user = User.objects.get(username="felipe")
    assert user.is_superuser is True
    assert user.check_password("a-strong-password")


def test_ensure_superuser_is_idempotent(monkeypatch):
    monkeypatch.setenv("DJANGO_SUPERUSER_USERNAME", "felipe")
    monkeypatch.setenv("DJANGO_SUPERUSER_PASSWORD", "a-strong-password")
    call_command("ensure_superuser")
    call_command("ensure_superuser")  # must not raise or duplicate
    assert User.objects.filter(username="felipe").count() == 1


def test_seed_demo_populates_and_is_idempotent():
    from apps.budgets.models import MonthlyBudget
    from apps.savings.models import SavingsMovement
    from apps.transactions.models import Transaction

    call_command("create_test_user", "demo", password="x", no_seed=True)
    call_command("seed_demo", "demo")
    user = User.objects.get(username="demo")
    period = timezone.localdate().strftime("%Y-%m")

    assert MonthlyBudget.objects.filter(owner=user, period=period).exists()
    assert Transaction.objects.filter(owner=user).count() >= 15
    assert SavingsMovement.objects.filter(owner=user, kind="buy").count() == 2
    # Card charges land as "sin revisar" so they don't count until confirmed.
    assert Transaction.objects.filter(owner=user, needs_review=True).count() == 3

    # Re-running resets to the same month instead of duplicating.
    call_command("seed_demo", "demo")
    assert SavingsMovement.objects.filter(owner=user).count() == 2


def test_new_user_is_seeded_when_enabled(settings):
    from apps.accounts import seeding
    from apps.transactions.models import Category
    from apps.wallets.models import Wallet

    settings.SEED_NEW_USERS = True
    user = User.objects.create_user(username="nuevo", password="x")

    assert {w.name for w in Wallet.objects.filter(owner=user)} == {"Mercado Pago", "Efectivo"}
    assert Category.objects.filter(owner=user).count() == len(seeding.CATEGORIES)


def test_new_user_not_seeded_when_disabled(settings):
    from apps.transactions.models import Category
    from apps.wallets.models import Wallet

    settings.SEED_NEW_USERS = False
    user = User.objects.create_user(username="pelado", password="x")

    assert Wallet.objects.filter(owner=user).count() == 0
    assert Category.objects.filter(owner=user).count() == 0


def test_new_user_seeding_is_idempotent_on_update(settings):
    from apps.wallets.models import Wallet

    settings.SEED_NEW_USERS = True
    user = User.objects.create_user(username="repe", password="x")
    before = Wallet.objects.filter(owner=user).count()

    # Saving again (update, not create) must not re-seed or duplicate.
    user.monthly_income_default = 1000
    user.save()

    assert Wallet.objects.filter(owner=user).count() == before
