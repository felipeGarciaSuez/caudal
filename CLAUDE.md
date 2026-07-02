# CLAUDE.md — Caudal (gestor de finanzas personales)

> Archivo de contexto para Claude Code. Léelo entero antes de tocar nada.
> Nombre del proyecto: **Caudal**. Único dueño/usuario por ahora: Felipe.

---

## 1. Qué es esto y por qué existe

App **personal** y **self-hosted** para llevar sueldo y gastos, con foco en **gastos hormiga**
(los gastos chicos y frecuentes que hoy no se registran y hacen que no se llegue a fin de mes).

Hoy las cuentas se llevan en dos lados que esta app tiene que unificar y mejorar:

1. **Notas de iPhone** → vista macro mensual: `SUELDO` arriba, una lista de rubros grandes
   (GASTOS DEPA, ICBC VISA, ICBC MASTER, GALICIA, SUPER, TELEFONO, NAFTA, GYM, OBRA SOCIAL, etc.),
   un total `GASTOS` y el indicador estrella `RESTO SUELDO` (sueldo − gastos).
2. **Excel `GASTOS_DEPA`** → desglose fino de UN rubro (el depto, en este caso compartido con un roommate):
   columnas `Gasto | Monto | DONDE | Pagado`, una hoja por mes, con totales `GASTO FIJO` / `GASTO TOTAL`.
   La columna **DONDE** es clave: de qué billetera/cuenta salió cada pago
   (`ICBC`, `Galicia`, `MP`/Mercado Pago, `UALA`/Ualá, `PPAY`/Personal Pay, inmobiliaria, `APARTE`, efectivo).

**El agujero a tapar:** ninguno de los dos registra el día a día (café, delivery, kiosco, transporte,
apps, compras chicas). Por eso se anota lo grande y a fin de mes no cierra.

### Objetivo del producto (en orden de prioridad)
1. Registrar gastos en **2 segundos** desde el celu (si cargar cuesta, no se usa → el proyecto muere).
2. Ver **a dónde se va realmente la plata**, separando **fijos** vs **variables** vs **hormiga**.
3. Proyectar el **RESTO SUELDO a fin de mes** y avisar si se va a quedar corto.
4. Soportar **multi-billetera** (banco + billeteras virtuales + tarjetas + efectivo), porque así se vive acá.
5. Importar movimientos desde **CSV/export** (Mercado Pago, Ualá, Personal Pay, resumen del banco).
6. Llevar el **ahorro y el patrimonio** valuado: dólar billete, dólar cripto (USDT) y —a futuro— acciones/cripto.
   Ahorrar es un **destino del sueldo**, no un gasto: tiene que verse aparte y también descontar del "resto".

---

## 2. Stack técnico (decisiones ya tomadas)

| Capa            | Elección                                  | Por qué |
|-----------------|-------------------------------------------|---------|
| Lenguaje        | Python 3.12                               | Preferencia del dueño. |
| Framework       | **Django 5.x**                            | Pedido explícito. ORM + admin + auth listos. |
| Gestor de deps  | **uv**                                    | Rápido, lockfile reproducible. (pip+requirements como fallback). |
| Base de datos   | **PostgreSQL**                            | Prod en **Neon** (free permanente); dev en Postgres local o Docker. |
| Frontend        | **Django templates + HTMX + Alpine.js**   | Mobile-first, sin SPA. Un solo dev, máxima velocidad. |
| Estilos         | **Tailwind CSS**                          | Rápido y consistente en mobile. |
| PWA             | manifest + service worker                 | "Instalar" en el celu y cargar gastos como si fuera app nativa. |
| Estáticos prod  | **WhiteNoise**                            | Sin S3, simple. |
| Server prod     | **gunicorn**                              | Estándar en Render. |
| Config          | **django-environ** + `.env`               | Nada de secrets hardcodeados. |
| Tests           | **pytest** + `pytest-django` + factory_boy| |
| Lint/format     | **ruff** (lint + format)                  | Una sola herramienta. |

### Deploy (importante por costos)
- **App** → Render (web service). Free hace spin-down a los 15 min (cold start ~30-60s): aceptable para uso personal.
- **Base** → **Neon**, NO el Postgres de Render. El Postgres free de Render **se borra a los 30 días**.
  Neon da Postgres gratis permanente. Se conecta por `DATABASE_URL`.
- Build: `uv sync` · Start: `uv run gunicorn config.wsgi:application`.
- Migraciones en deploy: `uv run python manage.py migrate` en el build/predeploy.
- `collectstatic` en build. Leer `PORT` de env y bindear a `0.0.0.0`.

---

## 3. Arquitectura y estructura de carpetas

Proyecto Django con apps chicas y enfocadas. Settings divididos por entorno.

```
caudal/
├── manage.py
├── pyproject.toml            # uv
├── uv.lock
├── .env.example              # plantilla de variables (NUNCA commitear .env real)
├── render.yaml               # blueprint de deploy (opcional)
├── config/                   # proyecto Django
│   ├── settings/
│   │   ├── base.py
│   │   ├── dev.py
│   │   └── prod.py
│   ├── urls.py
│   ├── wsgi.py
│   └── asgi.py
├── apps/
│   ├── accounts/             # usuario/auth (single-user hoy, multi-user-ready)
│   ├── wallets/              # medios de pago: banco, billetera, efectivo, tarjeta de crédito
│   ├── transactions/         # movimientos: ingreso / gasto / transferencia
│   ├── budgets/              # presupuesto mensual, gastos fijos recurrentes, proyección
│   ├── savings/              # ahorro/inversiones: holdings multi-activo + cotizaciones + patrimonio
│   ├── imports/              # importadores CSV (MP, Ualá, PPay, banco) con dedupe
│   └── dashboard/            # vistas y reportes (la cara de la app)
├── templates/
├── static/
└── tests/
```

---

## 4. Modelo de datos (núcleo — calcado a la realidad del dueño)

> Montos en **`DecimalField(max_digits=14, decimal_places=2)`** (ARS, inflación → montos grandes).
> Nunca float. Locale `es-AR`, timezone `America/Argentina/Cordoba`.

### `wallets.Wallet` (medio de pago / "DONDE")
- `name` (ICBC, Galicia, Mercado Pago, Ualá, Personal Pay, Efectivo…)
- `kind` → `bank` | `wallet` | `cash` | `credit_card`
- `currency` (default `ARS`)
- `is_active`
- (si `kind == credit_card`) `closing_day`, `due_day` → para tarjetas con cierre/vencimiento.

### `transactions.Category`
- `name`
- `kind` → `fixed` (fijo: alquiler, expensas, servicios, suscripciones) | `variable` | `ant` (hormiga)
- `parent` (opcional, jerarquía)
- `icon`, `color` (para el dashboard)

### `transactions.Transaction` (la tabla central)
- `date`
- `amount` (Decimal, positivo)
- `kind` → `expense` | `income` | `transfer`
- `wallet` (FK) — de dónde sale/entra
- `category` (FK, nullable para ingresos)
- `description`
- `is_paid` (bool) — replica el ✓ de las notas/Excel
- `is_shared` (bool) + `shared_ratio` (Decimal, ej. 0.50 para un depa compartido) — opcional, fase 3
- `source` → `manual` | `import` | `api`
- `external_id` (string, nullable) — para **dedupe** en importaciones
- `period` (YYYY-MM, indexado) — para vistas mensuales rápidas

### `budgets.RecurringExpense` (plantilla de gasto fijo)
Genera automáticamente los fijos de cada mes (alquiler, expensas, agua, luz, gas, TGI, Flow, gym, teléfono, obra social, suscripciones).
- `name`, `default_amount`, `category`, `wallet`, `day_of_month`, `is_active`

### `budgets.MonthlyBudget` (período mensual)
- `period` (YYYY-MM)
- `expected_income` (sueldo esperado del mes, ~1.9M con variación)
- Calculados (propiedades, no columnas): `total_spent`, `total_fixed`, `total_variable`,
  `total_ant`, `remaining` (= RESTO SUELDO), `projected_remaining` (proyección a fin de mes).

### `imports.ImportBatch`
- `wallet`, `source` (`mercadopago` | `uala` | `personalpay` | `bank_icbc` | `bank_galicia` | `generic_csv`)
- `file`, `imported_at`, `rows_total`, `rows_imported`, `rows_skipped` (duplicados)

### Ahorro / patrimonio (app `savings`) — *stock*, no *flujo*

> El ahorro NO va en `transactions`. Un gasto es flujo (sale y desaparece); el ahorro es una **tenencia**
> que sigue existiendo y **vale algo según la cotización**. Por eso vive en su propia app.
> Diseñado multi-activo desde el día 1: hoy dólar billete y USDT; mañana cripto volátil y acciones, sin rehacer nada.

#### `savings.Asset` (catálogo del activo)
- `symbol` (USD, USDT, BTC, ETH, AAPL/CEDEAR…)
- `name`
- `kind` → `fiat_cash` (dólar billete) | `stablecoin` (USDT/USDC) | `crypto` (BTC, ETH…) | `stock_cedear`
- `quote_currency` → moneda en la que cotiza (`USD` para cripto/acciones; el dólar billete se valúa vía dólar ARS)

#### `savings.Holding` (tenencia actual)
- `asset` (FK)
- `location` (dónde está: `colchón`, `Belo`, `Binance`, `Lemon`, `broker X`, `caja de seguridad`…)
- `quantity` (**`DecimalField(max_digits=24, decimal_places=8)`** — cripto necesita 8 decimales)
- `avg_buy_price` (opcional, costo promedio de compra → para calcular ganancia/pérdida)
- `notes`
- Propiedad calculada `current_value_ars` = `quantity × precio_actual_del_asset` (vía cotización).

#### `savings.SavingsMovement` (aportes, conversiones, compras/ventas) — conecta ahorro con el flujo mensual
- `date`
- `kind` → `deposit` (aporte) | `withdraw` (rescate) | `buy` | `sell` | `convert`
- `asset` (FK), `quantity`, `price` (precio de la operación)
- `from_wallet` (FK nullable) — si el aporte salió de plata en ARS de una wallet
  → permite descontar el ahorro del **RESTO SUELDO** del mes (ahorrar también "gasta" el sueldo).
- `period` (YYYY-MM)

#### `savings.PriceSnapshot` (cotizaciones, con fallback manual)
- `asset` (o tipo de dólar), `price_ars`, `source` (`api` | `manual`), `fetched_at`
- **Regla de oro**: si la API de cotización falla o no existe para ese activo, el usuario **carga la cotización a mano**
  ("el dólar cripto está a X"). Nunca depender de una API para que la app funcione.
- Fuentes a *evaluar* (no asumir que andan; siempre con fallback manual): API de dólar (oficial/blue/MEP/cripto),
  CoinGecko para cripto, y para CEDEARs/acciones algún proveedor de precios. Cotización editable siempre.

> **Patrimonio** = suma de `current_value_ars` de todos los holdings. Se reporta en **ARS y en USD**,
> con distribución por activo (% dólar billete / % USDT / % cripto / % acciones) y evolución en el tiempo.

---

## 5. Funcionalidad por fases (construir en este orden)

### Fase 0 — Scaffolding
- Proyecto Django + uv + settings por entorno + `.env.example` + ruff + pytest.
- Modelos base + migraciones + Django admin configurado (admin como primera UI usable).
- Seed: wallets reales (ICBC, Galicia, Mercado Pago, Ualá, Personal Pay, Efectivo) y categorías base.

### Fase 1 — MVP usable (replica Notas + Excel, mejor)
- **Carga manual rápida** de gasto/ingreso (form mínimo: monto, categoría, wallet, fecha=hoy por defecto).
  HTMX para que no recargue. Categorías frecuentes como botones de 1 toque.
- **Vista mensual** estilo Notas: sueldo, lista de gastos por categoría, total, **RESTO SUELDO**.
- **Vista detalle de un rubro** estilo Excel: movimientos con su `wallet` (DONDE) y `is_paid`.
- Marcar pagado/pendiente con un toque.

### Fase 2 — Importación CSV (ataca el gasto hormiga en serio)
- Importadores por fuente: **Mercado Pago export**, **Ualá**, **Personal Pay**, **resumen banco** (CSV/XLSX).
- **Dedupe** por `external_id` (o hash fecha+monto+desc) para no duplicar al re-importar.
- **Auto-categorización por reglas**: keyword en la descripción → categoría
  (ej. "RAPPI"/"PEDIDOSYA" → delivery/hormiga, "YPF"/"SHELL" → nafta, "NETFLIX"/"SPOTIFY" → suscripciones).
  Reglas editables; lo no matcheado queda "sin categoría" para revisión.

### Fase 3 — Inteligencia: fijos, proyección y alertas hormiga
- **Gastos fijos recurrentes** auto-generados cada mes desde `RecurringExpense` (pre-cargados como pendientes).
- **Proyección de RESTO SUELDO a fin de mes**: en base al ritmo de gasto del mes + fijos pendientes.
- **Panel de gastos hormiga**: total del mes en categoría `ant`, ranking de los que más suman,
  comparación contra meses anteriores, y alerta si el ritmo se dispara.
- **Gastos compartidos**: `is_shared` + `shared_ratio` para el depa (ver solo "mi parte").

### Fase 4 — Ahorro y patrimonio
- **Holdings con carga manual**: dólar billete y USDT primero (cantidad + dónde está).
- **Valuación**: traer cotización del dólar (blue/MEP/cripto) automática **con fallback a carga manual**.
- **Aportes desde el sueldo**: registrar `SavingsMovement` tipo `deposit` que descuenta del RESTO SUELDO del mes,
  así se ve cuánto del sueldo se fue a ahorro (no es plata "perdida", pero tampoco está disponible para gastar).
- **Tasa de ahorro mensual** (aportes / sueldo) y **panel de patrimonio** (total en ARS y USD, distribución por activo).
- Modelo ya preparado para **cripto volátil y acciones/CEDEARs**: sumarlos es cargar un `Asset` nuevo, nada estructural.

### Fase 5 — Integración automática (EXPERIMENTAL, opcional, NO bloqueante)
> ⚠️ En Argentina esto es lo más difícil. No es cimiento del proyecto.
- Mercado Pago: la API oficial apunta a cobros, no a leer movimientos personales fácil. Evaluar qué endpoints
  reales existen para tu cuenta antes de invertir tiempo. Si no alcanza → quedarse con el export CSV (Fase 2).
- Agregadores tipo Belvo: cobertura pobre en Argentina hoy. No asumir que funciona.
- Precios de cripto/acciones/dólar vía API para no cargar cotizaciones a mano (con fallback manual siempre).
- Tratar esta fase como spike de investigación, con fallback siempre al import/carga manual.

---

## 6. Convenciones para Claude Code

- **Idioma**: código, nombres y comentarios en **inglés**; UI/textos al usuario en **español (es-AR)**.
- **Sin emojis en el código.** Nada de emojis en identificadores, comentarios, docstrings, strings de
  log, mensajes de commit ni en el texto del código en general. Para iconografía de la UI usar un set
  de íconos real (SVG / icon font), no emojis literales hardcodeados en templates o seeds.
- **Mobile-first siempre.** Todo se diseña primero para una pantalla de celu, después escala.
- **Velocidad de carga > features.** Cualquier flujo de "agregar gasto" tiene que ser de 1-2 toques.
- **Plata**: siempre `Decimal`. Formateo con separador de miles `.` y decimales `,` (es-AR). Nunca redondear en cálculos.
- **Secrets**: solo vía `.env` / variables de entorno. Jamás commitear `.env`, tokens ni `SECRET_KEY`.
- **Migraciones**: cada cambio de modelo viene con su migración en el mismo cambio.
- **Tests**: lógica de cálculo (RESTO SUELDO, proyección, dedupe, categorización) va con tests sí o sí.
- **Commits**: chicos y atómicos, mensaje claro en español o inglés (consistente). No mezclar refactor + feature.
- **Nunca agregar Claude como coautor.** Ningún commit debe llevar trailers `Co-Authored-By: Claude...`
  ni `Claude-Session: ...` (ni de ninguna otra IA). Es un repo público con contribuciones humanas;
  esto aplica siempre, sin excepción, incluso si el flujo de commit por defecto los sugiere.
- **No metas dependencias pesadas** sin justificarlo. El stack es chico a propósito.
- **Antes de codear una fase nueva**, confirmá el modelo de datos contra este archivo.

---

## 7. Comandos

```bash
# Setup
uv sync                                   # instalar deps
cp .env.example .env                      # configurar entorno (editar valores)
uv run python manage.py migrate
uv run python manage.py createsuperuser

# Desarrollo
uv run python manage.py runserver
uv run python manage.py makemigrations
uv run python manage.py shell

# Calidad
uv run ruff check . && uv run ruff format .
uv run pytest

# Deploy (Render)
# build:  uv sync && uv run python manage.py collectstatic --noinput && uv run python manage.py migrate
# start:  uv run gunicorn config.wsgi:application --bind 0.0.0.0:$PORT
```

---

## 8. Variables de entorno (`.env.example`)

```
DJANGO_SETTINGS_MODULE=config.settings.dev
SECRET_KEY=changeme
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1
DATABASE_URL=postgres://user:pass@localhost:5432/caudal   # en prod: la URL de Neon
TIME_ZONE=America/Argentina/Cordoba
LANGUAGE_CODE=es-ar
```

---

## 9. Perfil de uso de referencia (para el seed — ajustá con tus propios datos)

> Ninguno de estos valores está hardcodeado en la lógica: son solo el punto de partida que carga
> `seed_data` (montos, wallets, categorías). Cada instancia de Caudal los edita desde la UI/admin
> para reflejar su propia situación real.

- **Sueldo**: variable mes a mes (`expected_income` se edita por mes desde la UI, sin valor fijo en el código).
- **Wallets de ejemplo**: banco(s), billeteras virtuales (Mercado Pago, Ualá, Personal Pay), efectivo.
- **Tarjetas de crédito**: uno o más resúmenes mensuales con cierre/vencimiento propio.
- **Fijos típicos del depa** (si se comparte con roommates, suelen ser gastos compartidos):
  Alquiler, Expensas, Agua, Luz, Gas, TGI, Flow, Super.
- **Otros fijos personales**: Teléfono, Nafta, Gym, Obra Social, suscripciones, cuotas/cursos puntuales.
- **Hormiga a vigilar**: delivery (Rappi/PedidosYa), kiosco, café, transporte/Uber, apps, compras chicas.
- **Ahorro hoy**: dólar billete (efectivo/colchón) y dólar cripto (USDT en exchange/billetera cripto).
- **Ahorro a futuro**: cripto volátil (BTC/ETH) y acciones/CEDEARs vía broker.
