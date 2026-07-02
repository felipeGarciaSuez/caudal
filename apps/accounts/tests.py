import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command

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
