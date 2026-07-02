"""Create the first admin user from environment variables (idempotent).

Meant for the deploy build step, where there's no interactive shell to run
`createsuperuser`. Safe to run on every build: no-ops if the env vars aren't
set, or if a user with that username already exists.

Usage:
    uv run python manage.py ensure_superuser

Reads DJANGO_SUPERUSER_USERNAME / DJANGO_SUPERUSER_PASSWORD /
DJANGO_SUPERUSER_EMAIL (optional) from the environment.
"""

import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

User = get_user_model()


class Command(BaseCommand):
    help = "Crea el primer superusuario desde variables de entorno (idempotente)."

    def handle(self, *args, **options):
        username = os.environ.get("DJANGO_SUPERUSER_USERNAME")
        password = os.environ.get("DJANGO_SUPERUSER_PASSWORD")
        email = os.environ.get("DJANGO_SUPERUSER_EMAIL", "")

        if not username or not password:
            self.stdout.write(
                "DJANGO_SUPERUSER_USERNAME/PASSWORD no están seteadas: nada que hacer."
            )
            return

        if User.objects.filter(username=username).exists():
            self.stdout.write(f"El usuario '{username}' ya existe: nada que hacer.")
            return

        User.objects.create_superuser(username=username, email=email, password=password)
        self.stdout.write(self.style.SUCCESS(f"Superusuario '{username}' creado."))
