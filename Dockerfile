# Caudal — imagen de producción.
#
# Basada en uv, no en pip: el proyecto tiene uv.lock y `uv sync --frozen`
# instala exactamente esas versiones. Con pip habría que mantener un
# requirements.txt en paralelo, que se desincroniza en silencio.

# ---------- etapa 1: dependencias ----------
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

# Solo los archivos de dependencias primero: mientras no cambien, Docker
# reutiliza esta capa aunque cambie el código de la app.
COPY pyproject.toml uv.lock ./

# --no-install-project porque pyproject tiene [tool.uv] package = false:
# Caudal no es un paquete instalable, es código que se ejecuta desde /app.
# --no-dev deja afuera pytest, ruff y factory-boy.
RUN uv sync --frozen --no-dev --no-install-project

# ---------- etapa 2: runtime ----------
FROM python:3.12-slim-bookworm

# PYTHONUNBUFFERED para que los logs de gunicorn salgan al toque y no se
# queden en el buffer cuando docker logs los lee.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:$PATH" \
    DJANGO_SETTINGS_MODULE=config.settings.prod

WORKDIR /app

# El venv ya resuelto de la etapa anterior. psycopg viene como wheel binario
# (psycopg[binary]), así que no hace falta libpq-dev ni compilador acá.
COPY --from=builder /app/.venv /app/.venv

COPY . .

# Red de seguridad para el bit de ejecutable: git en Windows no lo rastrea por
# defecto, así que un clon puede traer el entrypoint sin permiso de ejecución
# y el contenedor muere con "permission denied" antes de arrancar. El modo
# correcto ya está en el índice de git; esto lo hace independiente de eso.
RUN chmod +x /app/docker-entrypoint.sh

# collectstatic en build y no en cada arranque: es determinístico y no toca
# la base. Pero config/settings/prod.py lee SECRET_KEY, ALLOWED_HOSTS y
# DATABASE_URL al importarse y explota si faltan, así que hay que pasarle
# valores de mentira. No quedan en la imagen: son solo de este RUN.
RUN SECRET_KEY="solo-para-el-build-no-se-usa-en-runtime" \
    ALLOWED_HOSTS="localhost" \
    DATABASE_URL="postgres://build:build@localhost:5432/build" \
    python manage.py collectstatic --noinput --clear

# Usuario sin privilegios. Si alguien logra ejecutar código vía la app, no
# arranca siendo root adentro del contenedor.
RUN useradd --create-home --shell /bin/bash caudal \
    && mkdir -p /app/media \
    && chown -R caudal:caudal /app
USER caudal

EXPOSE 8000

ENTRYPOINT ["/app/docker-entrypoint.sh"]

# --timeout 30 mata al worker trabado en un request lento (por ejemplo, la
# importación de un PDF grande) en vez de dejarlo colgado ocupando un slot.
CMD ["gunicorn", "config.wsgi:application", \
     "--bind", "0.0.0.0:8000", \
     "--workers", "3", \
     "--timeout", "30", \
     "--access-logfile", "-", \
     "--error-logfile", "-"]
