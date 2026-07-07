"""Seed base wallets and categories for a user (idempotent).

Usually you don't need this: a new user is seeded automatically on creation
(see apps/accounts/signals.py). Use this to (re)seed an existing user, or to
backfill after SEED_NEW_USERS was off.

Usage:
    uv run python manage.py seed_data            # uses first superuser
    uv run python manage.py seed_data --user me  # by username
"""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from apps.accounts.seeding import seed_user

User = get_user_model()


class Command(BaseCommand):
    help = "Crea wallets, categorías y reglas base (idempotente). No carga fijos."

    def add_arguments(self, parser):
        parser.add_argument("--user", help="username; por defecto, el primer superuser")

    def handle(self, *args, **options):
        user = self._resolve_user(options.get("user"))
        counts = seed_user(user)
        self.stdout.write(
            self.style.SUCCESS(
                f"Seed para '{user}': {counts['wallets']} wallets, "
                f"{counts['categories']} categorías, {counts['rules']} reglas "
                f"y {counts['assets']} activos nuevos."
            )
        )

    def _resolve_user(self, username):
        if username:
            try:
                return User.objects.get(username=username)
            except User.DoesNotExist as exc:
                raise CommandError(f"No existe el usuario '{username}'.") from exc
        user = User.objects.filter(is_superuser=True).order_by("id").first()
        if not user:
            raise CommandError("No hay superuser. Creá uno con 'createsuperuser' o pasá --user.")
        return user
