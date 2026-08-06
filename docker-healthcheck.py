"""Healthcheck del contenedor web.

Pega a /accounts/login/, que responde 200 sin autenticación.

Los dos headers no son decorativos — sin ellos el healthcheck falla aunque la
app esté perfecta:

- Host: en prod ALLOWED_HOSTS es el dominio real, así que un request a
  127.0.0.1 sin Host correcto se lleva un 400 DisallowedHost.
- X-Forwarded-Proto: prod.py tiene SECURE_SSL_REDIRECT=True. Sin este header
  SecurityMiddleware ve un request HTTP y contesta 301 a https.

O sea: hay que imitar lo que manda Caddy.
"""

import os
import sys
import urllib.request

# ALLOWED_HOSTS puede venir como lista separada por comas; el primero es el
# host canónico.
host = os.environ.get("ALLOWED_HOSTS", "localhost").split(",")[0].strip()

request = urllib.request.Request(
    "http://127.0.0.1:8000/accounts/login/",
    headers={"Host": host, "X-Forwarded-Proto": "https"},
)

try:
    with urllib.request.urlopen(request, timeout=5) as response:
        sys.exit(0 if response.status == 200 else 1)
except Exception as exc:  # noqa: BLE001 — cualquier fallo es "unhealthy"
    print(f"healthcheck falló: {exc}", file=sys.stderr)
    sys.exit(1)
