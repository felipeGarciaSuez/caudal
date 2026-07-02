"""Create a non-staff test/demo user (idempotent) and seed its base data.

Test accounts must never be staff or superuser: they can use the app fully but
cannot reach the admin. Use this instead of createsuperuser for anyone you hand
credentials to.

Usage:
    uv run python manage.py create_test_user demo --password secreto123
    uv run python manage.py create_test_user demo   # random password, printed
"""

import secrets

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import BaseCommand

User = get_user_model()


class Command(BaseCommand):
    help = "Crea un usuario de prueba sin acceso al admin (no staff, no superuser)."

    def add_arguments(self, parser):
        parser.add_argument("username", help="Nombre de usuario de la cuenta de prueba.")
        parser.add_argument(
            "--password",
            default=None,
            help="Contraseña. Si no se pasa, se genera una al azar y se imprime.",
        )
        parser.add_argument(
            "--no-seed",
            action="store_true",
            help="No cargar billeteras/categorías base para el usuario.",
        )

    def handle(self, *args, **options):
        username = options["username"]
        password = options["password"] or secrets.token_urlsafe(9)

        user, created = User.objects.get_or_create(
            username=username,
            defaults={"is_staff": False, "is_superuser": False},
        )
        # Belt and suspenders: never leave a test account with admin access.
        if user.is_staff or user.is_superuser:
            user.is_staff = False
            user.is_superuser = False
        user.set_password(password)
        user.save()

        if not options["no_seed"]:
            call_command("seed_data", user=username)

        verb = "creado" if created else "actualizado"
        self.stdout.write(
            self.style.SUCCESS(f"Usuario de prueba '{username}' {verb}. Contraseña: {password}")
        )
