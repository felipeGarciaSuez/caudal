# Changelog

Formato basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/).
Versionado según [SemVer](https://semver.org/lang/es/) — criterio detallado en
[`CLAUDE.md`](./CLAUDE.md#10-versionado-y-ramas).

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
