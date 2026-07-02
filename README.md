
# Caudal

Gestor de finanzas personales, self-hosted. Sueldo, gastos (con foco en **gastos hormiga**),
ahorro y patrimonio. Mobile-first, carga de gastos en 2 toques.

Contexto completo del producto y decisiones: ver [`CLAUDE.md`](./CLAUDE.md).

Licencia [MIT](./LICENSE) — contribuciones bienvenidas.

## Contribuir

- **Nunca agregues coautoría de IA a los commits.** No incluyas trailers como `Co-Authored-By: Claude...`,
  `Claude-Session: ...` ni equivalentes de ninguna otra herramienta de IA, sin excepción.
- No commitees datos reales/sensibles (extractos bancarios, capturas, `.env`). Usá datos de ejemplo genéricos.

## Stack

Python 3.12 · Django 5.2 · PostgreSQL (Neon en prod, SQLite fallback en dev) ·
Django templates + HTMX/Alpine (próximas fases) · WhiteNoise · gunicorn · uv · ruff · pytest.

## Setup local

```bash
uv sync                                   # instala deps (crea .venv)
cp .env.example .env                      # editar valores; DATABASE_URL vacío = SQLite
uv run python manage.py migrate
uv run python manage.py createsuperuser
uv run python manage.py seed_data         # wallets y categorías reales
uv run python manage.py runserver
```

App en http://127.0.0.1:8000 · Admin en `/admin/`.

## Calidad

```bash
uv run ruff check . && uv run ruff format .
uv run pytest
```

## Deploy (Render + Neon)

Blueprint listo en [`render.yaml`](./render.yaml): en Render, **New → Blueprint** apuntando a este repo.

- **Base**: Neon (Postgres gratis permanente), vía `DATABASE_URL`. No usar el Postgres de Render (se borra a los 30 días).
- **Build**: `uv sync && collectstatic && migrate && ensure_superuser && seed_data` (los dos últimos son
  idempotentes: `ensure_superuser` crea el primer admin desde `DJANGO_SUPERUSER_USERNAME`/`_PASSWORD`
  —necesario porque el plan free no tiene shell interactiva para `createsuperuser`— y `seed_data`
  carga las categorías/wallets base).
- **Start**: `uv run gunicorn config.wsgi:application --bind 0.0.0.0:$PORT`
- Variables que hay que cargar a mano en el dashboard de Render después de crear el servicio:
  `DATABASE_URL` (la de Neon), `ALLOWED_HOSTS` y `CSRF_TRUSTED_ORIGINS` (el dominio que te asigna Render).
- `DJANGO_SETTINGS_MODULE=config.settings.prod` en prod.

## Estado

### Fase 0 — scaffolding ✅
- Proyecto Django + uv + settings por entorno + ruff + pytest.
- Modelos núcleo (wallets, transactions, budgets, savings, imports) + migraciones + admin.
- Seed de wallets y categorías reales.

### Fase 1 — MVP usable ✅
- **Carga rápida** de gasto (HTMX): escribís el monto y tocás la categoría → se guarda sin recargar.
  Categorías como chips de 1 toque, selector de billetera, fecha = hoy por defecto.
- **Vista mensual** estilo Notas (`/m/YYYY-MM/`): **RESTO SUELDO**, gastos por rubro, total y
  desglose fijo / variable / hormiga. Sueldo editable inline.
- **Detalle de rubro** estilo Excel: movimientos con su billetera (DONDE) y estado de pago.
- **Marcar pagado/pendiente** con un toque (HTMX).
- UI mobile-first con CSS propio (dark). HTMX y Alpine vendorizados en `static/vendor/`.

> Nota de stack: la Fase 1 usa CSS propio en `static/css/app.css` en vez de Tailwind, para no
> arrastrar un toolchain de Node en el MVP. Migrar a Tailwind al montar el pipeline de assets.

### Fase 2 — importación CSV ✅
- **Importador de CSV** en `/import/`: subís el export del extracto (Mercado Pago, Ualá,
  Personal Pay, banco) y elegís la billetera (DONDE).
- **Detección automática de columnas** por alias (fecha / monto / descripción / id), delimitador
  (`,` `;` `\t` `|`) y encoding. Montos es-AR (`1.234,56`, `-1.234,56`, `(1.234,56)`) y US (`1234.56`).
  Negativo = gasto, positivo = ingreso.
- **Dedupe** por `external_id` de la fuente, o hash de fecha+monto+descripción cuando no hay id,
  para no duplicar al re-importar.
- **Auto-categorización por reglas** (`CategoryRule`, editable en el admin): keyword en la
  descripción → categoría (RAPPI→Delivery, YPF→Nafta, NETFLIX→Suscripciones…). Lo no matcheado
  queda sin categoría para revisar.

> Sobre Mercado Pago "en vivo": evaluado y descartado. La API de MP es merchant-oriented y no
> expone los gastos propios del usuario (lado pagador). El camino es el import de CSV de arriba.

Próximo (Fase 3): gastos fijos recurrentes auto-generados, proyección de RESTO SUELDO a fin de
mes, panel de gastos hormiga y gastos compartidos.
