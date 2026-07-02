# Changelog

Formato basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/).
Versionado según [SemVer](https://semver.org/lang/es/) — criterio detallado en
[`CLAUDE.md`](./CLAUDE.md#10-versionado-y-ramas).

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
