# Handoff: Caudal — Identidad "Corriente" (1a) + pantalla Mes

## Overview
**Caudal** es una app personal, self-hosted (Django) de finanzas: sueldo, gastos, ahorro y
foco en los **gastos hormiga**. Mobile-first / PWA, público es-AR, tema dark.

Este paquete contiene la **dirección de marca elegida — "Corriente" (1a)** y la pantalla
principal ("Mes" con el **RESTO SUELDO** como número estrella) rediseñada con esa identidad.

## Sobre los archivos de diseño
Los archivos de este bundle son **referencias de diseño hechas en HTML/SVG** — prototipos que
muestran la apariencia y el comportamiento buscados, **no** código de producción para copiar tal
cual. La tarea es **recrear estos diseños dentro del entorno del repo existente**
(`felipeGarciaSuez/caudal`, Django + templates + CSS con Lucide icons) usando sus patrones
establecidos. Los SVG y PNG del logo **sí** son entregables finales listos para usar.

## Fidelidad
**Alta fidelidad (hifi).** Colores, tipografía, espaciados y radios son finales. Recrear la UI
pixel-perfect con los tokens de abajo. Los assets de marca (SVG/PNG) son de uso directo.

---

## Identidad "Corriente"

**Concepto:** el doble sentido de *caudal* — el flujo de un río y un caudal de dinero. El
isotipo es una **app-tile** con dos corrientes (≈) que fluyen: agua que fluye = plata que fluye.

- **Isotipo:** tile redondeada (radius 18/64 del lado) con gradiente menta→cyan y dos ondas
  en verde muy oscuro (`#052a20`). Pensado para verse bien como ícono de home screen y a 32px.
- **Wordmark:** "Caudal" en **Bricolage Grotesque 800**, letter-spacing ~-1px, con degradé de
  texto `#eaf0ff → #93a1c4` sobre fondo oscuro (o `#eaf0ff` plano en reverso claro).
- **Lockup:** isotipo + wordmark, gap ≈ 0.25× del alto del isotipo, centrados verticalmente.

### Tipografía
- **Titulares / número estrella / wordmark:** Bricolage Grotesque (500 / 700 / 800).
- **Datos y UI general:** system-ui (`-apple-system, system-ui, "Segoe UI", Roboto`).
- Números siempre con `font-variant-numeric: tabular-nums`.

### Íconos
Lucide (los que ya usa el repo), stroke 2, esquinas redondeadas.

---

## Design tokens (paleta dark, ya definida)

Fondos
- `--bg-0` #0b1020 · base
- `--bg-1` #0f1629 · secundario
- `--surface` #161f38 · tarjetas
- `--surface-2` #1e2a4a · elevada
- `--line` #26324f · bordes/divisores

Texto
- `--text` #eaf0ff · principal
- `--muted` #93a1c4 · atenuado
- `--faint` #64729a · tenue

Marca / semántica
- `--brand` / `--pos` #34e2b0 · menta (marca + positivo)
- `--brand-2` #22d3ee · cyan (acento / gradiente)
- `--neg` #fb7185 · coral (negativo)
- Verde oscuro del isotipo: #052a20

Categorías de gasto
- `--fixed` #8b93ff · fijos
- `--variable` #fbbf24 · variables
- `--ant` #fb7185 · hormiga
- `--none` #64729a · sin categoría

Gradiente de marca: `linear-gradient(135deg, #34e2b0, #22d3ee)`.

Radios
- Tarjetas / superficies: **20px**
- Isotipo (tile): 18 en viewBox 64 → **~28% del lado**
- Chips/pills: 999px; botones de nav íconos: 12–13px

Sombras
- Tarjeta: `0 12px 30px -12px rgba(0,0,0,.55)`
- Elevada / teléfono: `0 24px 50px -22px rgba(0,0,0,.7)`
- FAB (botón +): `0 10px 22px -6px rgba(52,226,176,.5)`

---

## Pantalla: "Mes" (home)
**Propósito:** ver de un vistazo cuánto sueldo queda (RESTO SUELDO) y en qué se va la plata,
con énfasis en gastos hormiga.

**Layout** (mobile, ancho de contenido con padding lateral ~16px, fondo `--bg-0` con glow
radial `#17233f` arriba):
1. **Topbar:** lockup (isotipo 22px + "Caudal" Bricolage 800 17px) a la izquierda; botón ícono
   (logout/importar) 38×38, `--surface`, borde `--line`, radius 12.
2. **Selector de mes:** flechas ‹ › (40×40, `--surface`, radius 13) + "Julio 2026" (17px, 700)
   centrado con subtítulo "este mes" en `--faint` uppercase.
3. **Hero RESTO SUELDO:** tarjeta radius 20, fondo `linear-gradient(160deg,#16244a,#111a33)`
   con glow menta arriba-derecha y una onda ≈ tenue de fondo (opacity .35).
   - Label "Resto sueldo" (`--muted`, 10.5px, uppercase, tracking .12em).
   - Número: **40px, weight 800, color `--brand` (#34e2b0)**, con "$" chico `--muted` y los
     centavos a 22px. tabular-nums.
   - Barra de progreso: track `rgba(255,255,255,.07)`, fill gradiente marca, altura 10, radius 999.
   - Pie: "Sueldo $ 1.200.000" y "− gastos $ 787.650" en `--muted`/`--text`.
4. **Gastos grandes:** tarjeta `--surface`. Header uppercase `--faint` + pill "2/3 pagados".
   Filas: ícono 32×32 (pagado = gradiente marca con check; pendiente = `--surface-2` borde
   `--line`), nombre 14px 600, subtítulo `--faint` 11.5px, monto 14px 700 tabular a la derecha,
   divisores `--line`. "pendiente" en `--variable`.
5. **Gastos hormiga:** tarjeta `--surface`. Pill de alerta en ámbar
   (`color-mix(#fbbf24 20%, --surface-2)`, texto #ffe4a3) con ícono trending-up. Total del mes
   **23px, 800, color `--neg`**; comparación "+17%" en `--neg`. Filas con barra por ítem
   (gradiente `#fb7185→#fbbf24`, track `--bg-1`).
6. **Tab bar (fija, abajo):** fondo `--bg-0` 82% + blur 14px, borde superior `--line`.
   5 slots: Mes (activo, `--brand`), Ahorro, **FAB "+"** central elevado (círculo 54, gradiente
   marca, ícono `#04231b`), Importar, Ajustes. Inactivos `--faint`, labels 10px 700.
   Íconos Lucide: calendar-days, piggy-bank, plus, download, settings.

**Estados**
- Item de gasto pagado vs pendiente (ícono lleno vs contorno; badge "pendiente" ámbar).
- Pill hormiga cambia según comparación con el mes anterior (alerta ámbar si sube).
- Tab activo en `--brand`; resto `--faint`.

**Interacciones / comportamiento**
- Flechas ‹ › cambian de mes (recargar/HTMX el cuerpo del mes).
- FAB "+" abre alta de gasto.
- Barras de progreso reflejan gastado/sueldo.
- Copy en es-AR; montos con separador de miles "." y decimales ",".

---

## Assets (entregables finales)

`assets/` (SVG — fuente vectorial, editable):
- `logo-corriente.svg` — isotipo a color (gradiente menta→cyan). Base para todo.
- `logo-corriente-favicon.svg` — variante con stroke un poco más grueso para 32px.
- `logo-corriente-mono.svg` — 1 color (menta), contorno. Para 1 tinta.
- `logo-corriente-reverse.svg` — sobre fondo oscuro, ondas en `--text`.
- `lockup-corriente.svg` — isotipo + wordmark. **Ojo:** el wordmark usa `<text>` en Bricolage
  Grotesque; para producción, convertir a curvas o incrustar la fuente (webfont).

`assets/promo/` (PNG listos para redes / stores):
- `caudal-appicon-1024.png` / `-512.png` / `-192.png` — ícono de app, **fondo transparente**
  (corners redondeados), para App Store / Play / PWA `manifest`.
- `caudal-favicon-32.png` — favicon.
- `caudal-appicon-on-light-1024.png` — ícono centrado sobre fondo claro `#eaf0ff`.
- `caudal-mark-mono-1024.png` — solo la marca, mono, transparente.
- `caudal-lockup-horizontal.png` (2000×640, dark) — lockup para webs/headers.
- `caudal-lockup-transparent.png` (2000×640) — lockup con wordmark blanco, **fondo
  transparente** (para poner sobre cualquier fondo oscuro).
- `caudal-lockup-stacked.png` (1200×1200, dark) — versión apilada, para avatar/perfil.
- `caudal-social-banner.png` (1200×630) — banner Open Graph / redes con tagline
  "El flujo de tu plata, bajo control."

Íconos de UI: **Lucide** (ya en el repo, `apps/dashboard/templatetags/icons.py`).
Fuente: **Bricolage Grotesque** (Google Fonts) para títulos/marca.

## Files (referencias de diseño en el proyecto)
- `Caudal Identidad.dc.html` — las 3 direcciones de marca (1a Corriente, 1b Gota, 1c Cauce)
  con logo, tests a 32px/mono/reverso y la pantalla Mes en marco de iPhone. **1a es la elegida.**

## Sugerencias de implementación (Django del repo)
- Servir el favicon/app-icon desde `static/` y referenciarlos en `base.html` + `manifest`
  del PWA.
- Definir los tokens como CSS custom properties en el `:root` del stylesheet (`static/css/app.css`).
- Sumar Bricolage Grotesque vía `<link>` de Google Fonts (o self-host woff2) y aplicarla a
  títulos, número estrella y wordmark; dejar system-ui para datos.
- El número RESTO SUELDO y montos: clase utilitaria con `tabular-nums`.
