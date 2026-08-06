#!/usr/bin/env bash
#
# Corre las migraciones y después entrega el control a gunicorn (el CMD).
#
# Las migraciones van acá y no en el Dockerfile porque necesitan la base
# viva, que en build no existe. Y no van en un job aparte porque con un solo
# contenedor web no hay riesgo de que dos las corran a la vez.

set -euo pipefail

echo "==> Esperando a Postgres"
# depends_on con condition: service_healthy ya nos garantiza que la base
# acepta conexiones, pero si alguien levanta este contenedor suelto conviene
# no explotar en el primer intento.
for i in $(seq 1 30); do
    if python -c "
import sys, django
django.setup()
from django.db import connection
try:
    connection.ensure_connection()
except Exception:
    sys.exit(1)
" 2>/dev/null; then
        echo "    Postgres responde"
        break
    fi
    if [ "$i" -eq 30 ]; then
        echo "    Postgres no respondió después de 30 intentos" >&2
        exit 1
    fi
    sleep 2
done

echo "==> Migraciones"
python manage.py migrate --noinput

# ensure_superuser es idempotente: si las variables no están seteadas, o el
# usuario ya existe, no hace nada. Ver apps/accounts/management/commands/.
echo "==> Superusuario (si corresponde)"
python manage.py ensure_superuser

echo "==> Arrancando"
exec "$@"
