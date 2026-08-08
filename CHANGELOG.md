# Changelog

Formato basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/).
Versionado según [SemVer](https://semver.org/lang/es/) — criterio detallado en
[`CLAUDE.md`](./CLAUDE.md#10-versionado-y-ramas).

## [1.5.0] — 2026-08-08

Onboarding para el lanzamiento público: un tour guiado que le muestra al usuario
nuevo cómo usar la app, en su lugar.

### Agregado
- **Tour de bienvenida (spotlight).** Resalta cada parte de la app en su lugar
  con una explicación corta (nada de cartelones de texto). Cada pantalla tiene
  su propio "?": el del **Mes** recorre resto sueldo → ingresos → gastos grandes
  → hormiga → el "+" → Ahorro → Importar → Ajustes; el de **Ajustes** recorre
  billeteras → categorías → reglas → fijos → umbral → exportar. Auto-abre una
  sola vez para usuarios nuevos y se re-lanza desde el "?".
- El **logo de Caudal** ahora lleva al inicio al tocarlo.

### Notas
- Motor de tour propio sin dependencias (`static/js/tour.js`), targets marcados
  con `data-tour`. Nuevo flag `accounts.User.has_seen_tour` (migración `0005`) +
  endpoint `dashboard:tour_seen`.

## [1.4.1] — 2026-08-08

Tanda de fixes y pulido de UX (mayormente sobre lo de 1.4.0). Incluye una
migración destructiva (elimina el "cobrado" de los ingresos).

### Arreglado
- **Cotización del dólar** (Ahorros): el input "Dólar hoy" no guardaba porque los
  atributos HTMX estaban en el `<form>` y por herencia no disparaban; van en el
  input. Ahora recalcula el valor en pesos y persiste al salir/volver.
- **Alta de gasto**: el "+" del Mes ahora despliega el formulario y baja al fondo
  en un solo toque (antes había que tocarlo dos veces).
- **Tilde del checklist** centrado (se veía corrido en el teléfono).
- **Flicker del tabbar** en iOS (elemento fijo con `backdrop-filter`): se fuerza
  su propia capa de GPU para que no parpadee al cambiar de página.

### Cambiado
- **Ingresos**: se elimina la lógica de "cobrado"; la pantalla queda solo con los
  montos esperados. El bloque de ingresos ahora muestra un indicador de que abre
  otra pantalla.
- **Alta de gasto**: tocar una categoría solo la **selecciona**; se agrega un botón
  "Confirmar gasto" (antes se cargaba solo al tocar el chip).
- **Tabbar**: el "+" aparece solo en la vista de Mes; en el resto el botón central
  es una **casita** que lleva al Mes.
- **Ajustes**: el input de umbral hormiga es más grande y legible en el celu.

### Eliminado
- Campo `received_amount` de las fuentes de ingreso (migración destructiva
  `budgets/0003`).

### Backlog
- Se anotó: cotización del dólar automática (fetch diario vía API con fallback
  manual) y un tour de onboarding.

## [1.4.0] — 2026-08-07

Rediseño de categorías: el tipo de un gasto (fijo / grande / hormiga) lo define
el gasto, no el rubro. Y ahora se pueden borrar los gastos grandes del checklist.

### Cambiado
- **Las categorías dejan de tener tipo (fijo/variable/hormiga) y grupos.** Una
  categoría es solo una etiqueta (nombre + ícono). Qué es fijo/grande/hormiga lo
  decide cada gasto, no el rubro:
  - **Checklist de fijos** = los gastos **recurrentes** que declarás (Gastos Fijos).
  - **Grande vs hormiga** = por **monto** (umbral) + la marca "es un gasto grande".
  - Así, un gasto chico de Salud cae en **hormiga** en vez de "grande" solo por
    ser de esa categoría.
- Cualquier categoría puede respaldar un gasto fijo recurrente (antes solo las fijas).

### Agregado
- **Borrar gastos grandes desde el checklist** (antes solo se podían borrar los
  de un único movimiento).

### Interno
- Normalización de fin de línea del repo a LF (`.gitattributes`).

### Migraciones
- `transactions`: elimina `Category.kind` y `Category.parent` (borra esas
  columnas; los rubros se conservan, pierden su tipo/grupo).

## [1.3.0] — 2026-08-06

Login con Google, ingresos con varias fuentes (sueldo + extras), importadores de
resumen de tarjeta ICBC VISA y MASTERCARD desde PDF, y salida a producción en un
VPS con Docker.

### Agregado
- **Login con Google** (django-allauth): botón en el login, alta y vinculación
  por email, convive con el login usuario/contraseña. Credenciales por `.env`
  (`GOOGLE_OAUTH_CLIENT_ID` / `GOOGLE_OAUTH_SECRET`); si faltan, el botón no aparece.
- **Múltiples fuentes de ingreso** por mes (`budgets.IncomeSource`): sueldo +
  extras (freelance, alquiler…), cada una con monto **esperado** y **cobrado**.
  El RESTO SUELDO se calcula sobre el total planeado. Pantalla dedicada editable.
- **Importadores de resumen de tarjeta ICBC desde PDF**: **VISA** y **MASTERCARD**
  (cuotas, cargos en USD, dedupe). Revisión de extracto con "Guardar todo" y
  confirmación por consumo; botón para eliminar el resumen entero desde su detalle.
- **Aviso de bloqueo estilizado** (en español, con la marca) cuando django-axes
  bloquea el login por demasiados intentos.
- **Dockerización para producción en VPS**: `docker-compose.prod.yml` (web +
  Postgres), entrypoint que corre migraciones, healthcheck, límites de
  memoria/CPU, detrás de Caddy.
- **Auto-seed** de datos base al crear un usuario y comando **`seed_demo`** (mes
  de ejemplo en una cuenta demo).
- **Export CSV** de movimientos.
- **Páginas de error 404/500** con la identidad de Caudal.
- **Marca**: favicon, PWA manifest, isotipo y bundle de identidad visual.

### Cambiado
- **Importador VISA**: el período se toma de la fecha de **vencimiento**
  (VENCIMIENTO ACTUAL), no del cierre, para que los consumos cuenten en el mes en
  que se paga el resumen.
- **Importación sin vista previa**: los movimientos entran directo (con dedupe),
  sin pantalla intermedia.
- En la revisión del resumen, **guardar un consumo no reordena la lista ni saltea
  el scroll**.

### Corregido
- Isotipo desincronizado entre páginas (marca centralizada en un partial único).
- Bit de ejecutable del `docker-entrypoint.sh`.
- django-axes leyendo la IP real detrás del proxy en producción.
- Un resumen de tarjeta importado a una billetera que **no** era de crédito caía
  como gastos sueltos en vez de agruparse en el resumen de la tarjeta. El
  importador ahora **valida que la billetera sea compatible con la fuente** (y
  filtra el select en vivo), y **solo ofrece las fuentes con parser probado**
  (Tarjeta ICBC, Banco ICBC, Mercado Pago). Además, un mensaje claro cuando el
  archivo ya estaba importado, en vez de un ambiguo "0 filas".

### Migraciones
- `budgets`: `IncomeSource`.
- `sites`, `account`, `socialaccount` (django-allauth).

## [1.2.0] — 2026-07-07

Rework de la clasificación grande/hormiga (ahora por monto), gastos grandes
forzables a mano, porcentaje libre en gastos compartidos y alta de gasto unificada.

### Agregado
- **Umbral hormiga configurable** (`User.ant_threshold`, default $100.000):
  un gasto por debajo cuenta como hormiga, salvo los fijos. Editable en Ajustes.
- **Gastos grandes automáticos** (`User.auto_big_expenses`): toggle en Ajustes
  para prender/apagar la clasificación por monto.
- **"Es un gasto grande"** (`Transaction.is_big`): checkbox en el alta y la
  edición para forzar que un gasto cuente como grande sin importar el monto.
- **"Mi parte" como porcentaje libre** (0–100%) en la revisión del resumen de
  tarjeta; **0%** marca que el consumo no sale de tu billetera.

### Cambiado
- La separación **grande vs hormiga** ahora es **por monto**, no por el tipo de
  categoría. Los gastos fijos siguen siendo grandes siempre, aunque sean chicos.
- **Alta de gasto unificada**: un solo formulario "Agregar un gasto" (se eliminó
  el de "gasto grande puntual"), ya que el monto define el destino.
- **Seed** de categorías reescrito a buckets amplios (Vivienda, Servicios,
  Suscripciones, Salud, Impuestos…); ya no crea categorías-factura (Expensas,
  TGI, Flow…) ni gastos fijos recurrentes de ejemplo.
- Inputs numéricos sin las flechitas (spinners).

### Migraciones
- `accounts`: `ant_threshold`, `auto_big_expenses`.
- `transactions`: `is_big`.

## [1.1.0] — 2026-07-02

Descripción en la carga rápida, opción "sin categoría" y endurecimiento de seguridad
para poder exponer la app al público.

### Agregado
- **Descripción** en los dos formularios de carga rápida (gasto grande puntual y gasto
  suelto/hormiga), para identificar cada movimiento.
- Opción **"Sin categoría"**: en el select de gastos grandes y como chip en gastos sueltos.
- Comando `create_test_user`: crea cuentas de prueba sin acceso al admin (nunca staff/superuser).
- Protección de fuerza bruta en el login con **django-axes** (bloqueo por IP, cooloff).

### Cambiado
- Importador: tope de 2000 filas por archivo e inserción con `bulk_create`, para que un CSV
  enorme no dispare decenas de miles de INSERTs ni cuelgue el worker.
- Admin fuera de `/admin/`: ruta configurable vía `ADMIN_URL`.
- `prod`: `SECRET_KEY` sin fallback inseguro (falla fuerte si falta) y `gunicorn --timeout 30`.

### Corregido
- Cargar un gasto sin categoría tiraba un error 500 al renderizar: el filtro `default`
  resolvía `tx.category.name` de forma eager. Se usa `tx.category` (mismo texto vía `__str__`).

## [1.0.0] — 2026-07-02

Primera versión estable.

### Agregado
- Vista mensual: checklist de **Gastos grandes** (fijos recurrentes + agregado por categoría),
  panel de **Gastos hormiga** retrospectivo, agrupamiento "Gastos Vivienda".
- Importadores CSV: banco ICBC, tarjeta de crédito (cuotas, cargos en USD, revisión previa a
  contar en el mes), Mercado Pago. Dedupe y auto-categorización por reglas.
- Gastos compartidos: pantalla de revisión para asignar categoría y "mi parte" a movimientos
  de tarjeta.
- Ahorro y patrimonio: compra/venta de dólares (billete y cripto), valuación por cotización
  manual, integración con el RESTO SUELDO.
- Login propio, PWA mobile-first, íconos SVG (sin emojis).
- Deploy: Blueprint de Render + Postgres en Neon.
