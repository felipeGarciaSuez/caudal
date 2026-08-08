# TODO / Backlog — Caudal

> Ideas y features pendientes, con contexto y notas técnicas para que sean accionables.
> El roadmap por fases del producto vive en `CLAUDE.md` (seccion 5); esto es el backlog vivo.
> Orden = prioridad acordada con Felipe (no estricto).

---

## 1. Chatbot de Caudal por WhatsApp con IA (via n8n) [PRIORITARIO]

**Que:** poder registrar un gasto mandando un **audio por WhatsApp** a un bot. La IA
transcribe e interpreta el audio, arma el gasto (monto + categoria + descripcion) y
**antes de guardarlo muestra un preview de confirmacion**. Recien al confirmar se
registra en Caudal.

**Por que:** es el objetivo #1 del producto (registrar en 2 segundos desde el celu).
WhatsApp es donde ya esta el usuario; hablar es mas rapido que abrir la app y tipear.

**Ejemplo de recorrido:**
1. El usuario manda un audio: _"registrar gasto de 80 mil pesos categoria ocio por
   salir a comer con mi novia"_.
2. El bot responde con el preview:
   > Gasto: **$80.000,00** · Ocio · "salir a comer con mi novia" · hoy · ICBC
   > Responde CONFIRMAR o CANCELAR.
3. Al confirmar, el gasto queda registrado en Caudal.

**Alcance / piezas:**
- **Canal WhatsApp:** n8n con WhatsApp Business Cloud API (Meta) o Twilio. Evaluar
  costos y verificacion de numero. El servidor propio (VPS) hostea n8n.
- **Login / vinculacion por WhatsApp:** mapear numero de telefono -> usuario Caudal.
  Un usuario "vincula" su numero una vez (codigo de emparejamiento o desde Ajustes).
  Guardar el mapeo `phone -> user` de forma segura. Nunca registrar gasto de un
  numero no vinculado.
- **Transcripcion de audio:** speech-to-text (Whisper API u otro) dentro del flujo n8n.
- **Interpretacion (NLU) con IA:** pasar el texto a un LLM (Claude) que extraiga un
  JSON estructurado: `{ amount, category, description, date?, wallet? }`. Debe
  matchear la categoria dicha ("ocio") contra las categorias reales del usuario, y
  dejar el gasto "sin categoria" / para revisar si no hay match claro.
- **API de Caudal para crear transacciones:** endpoint REST autenticado (API key o
  token por usuario) que reciba el gasto ya confirmado y cree la `Transaction`
  (`source = "api"`). Hoy Caudal no expone API: hay que agregarla (empezar minima:
  crear gasto + listar categorias/wallets del usuario).
- **Preview + confirmacion:** el flujo n8n mantiene el estado "pendiente de confirmar"
  y solo hace el POST a la API cuando llega "CONFIRMAR". Timeout / cancelacion.

**Notas / riesgos:**
- Seguridad: la API key mapea a un usuario; tratarla como secret. Rate limiting.
- Ambiguedad del audio: montos ("80 mil" -> 80000), fechas relativas ("ayer"),
  categoria inexistente. El preview es la red de seguridad: el usuario ve y corrige.
- Fuera de alcance inicial: multi-idioma, adjuntar fotos de tickets, otros tipos de
  movimiento (ingreso/transferencia) — sumar despues.

---

## 2. Multiples fuentes de ingreso (sueldo + extras) [HECHO]

> Implementado: modelo `budgets.IncomeSource` (esperado + cobrado por mes),
> `MonthlyBudget.income_planned` / `income_received`, el RESTO SUELDO ahora va
> sobre el total planeado, y pantalla `dashboard:month_income` para desglosar en
> fuentes (editable inline por HTMX, plan vs cobrado). Con tests y verificado en
> el server real.

**Que:** hoy el mes tiene un solo ingreso esperado (`MonthlyBudget.expected_income`,
pensado como "el sueldo"). Permitir documentar **varias fuentes**: sueldo + ingreso
extra (freelance, alquiler, venta, aguinaldo, etc.).

**Por que:** mucha gente no vive de un solo sueldo. El RESTO SUELDO y la tasa de
ahorro tienen que calcularse sobre el **ingreso total** del mes, no solo el sueldo.

**Alcance / piezas:**
- Modelo de fuentes de ingreso por periodo (ej. `IncomeSource` o varias filas de
  ingreso asociadas al `MonthlyBudget`), cada una con nombre, monto y si es
  recurrente. Alternativa: apoyarse en `Transaction` con `kind = income` y sumar.
- Revisar todos los calculos que hoy usan `expected_income` como un unico numero
  (RESTO SUELDO, proyeccion, tasa de ahorro) para que usen el **total de ingresos**.
- UI: en la vista mensual, poder agregar/editar varias lineas de ingreso arriba,
  no un solo campo "sueldo".
- Migracion de datos: el `expected_income` actual pasa a ser la fuente "Sueldo".

**Estado del codigo hoy (relevado):**
- `MonthlyBudget.expected_income` es UN solo numero (el sueldo planeado). El RESTO
  SUELDO (`remaining`) se calcula con ese numero.
- Ya existe `MonthlyBudget.actual_income`: suma las `Transaction(kind=income)` del
  mes. PERO hoy no se usa en el RESTO (que va contra `expected_income`).

**Notas:** decidir si un ingreso es una fila de `Transaction (income)` (mas simple,
unifica con el flujo, ya hay `actual_income`) o una entidad de "fuentes esperadas"
aparte del presupuesto. Confirmar el modelo contra `CLAUDE.md` antes de codear.

---

## 3. Login con Google (OAuth) [HECHO - en producción]

> Implementado y **andando en prod**: django-allauth + provider Google, botón
> "Continuar con Google" en el login, alta/vinculación por email, backend junto a
> axes/ModelBackend, config por `.env` (GOOGLE_OAUTH_CLIENT_ID / _SECRET).
> Credenciales OAuth cargadas en el VPS y redirect URI del dominio autorizada en
> Google Cloud. Requiere `django-allauth`, `requests`, `pyjwt[crypto]`.

**Que:** permitir iniciar sesion con cuenta de Google, ademas de usuario/contrasena.

**Por que:** bajar la friccion para **invitar a otros usuarios** a probar Caudal
(hoy es single-user con superuser creado a mano).

**Alcance / piezas:**
- Integrar OAuth de Google. Candidato: `django-allauth` (soporta social login y se
  integra con el `accounts.User` actual). Evaluar peso de la dependencia (el stack
  es chico a proposito — justificarlo).
- Configurar credenciales OAuth (client id/secret) via `.env`, nunca hardcodeadas.
- Flujo de alta: primer login con Google crea el usuario y sus wallets/categorias
  base (reusar el seed). Vincular email de Google al `User`.
- Coexistencia con el login actual (username/password) y con django-axes.

**Notas:** al abrir el registro a mas usuarios, revisar aislamiento de datos por
`owner` en TODAS las vistas/queries (ya se filtra por `owner`, reconfirmar).

---

## 4. Aviso estilizado al bloquearse por reintentos (django-axes) [HECHO]

> Implementado: template propio `templates/lockout.html` con branding y en
> español, `AXES_LOCKOUT_TEMPLATE` en settings, filtro `duration_es` para el
> tiempo de reintento. Con tests.

**Que:** cuando django-axes bloquea la cuenta por demasiados intentos fallidos,
hoy aparece el texto plano _"Account locked: too many login attempts. Please try
again later."_ **sin estilo** (texto suelto, sin la UI de Caudal).

**Por que:** se ve roto/descuidado y encima en ingles. Tiene que ser una pantalla
propia, en español y con el estilo de la app.

**Alcance / piezas:**
- Template propio para la respuesta de lockout de django-axes (`AXES_LOCKOUT_TEMPLATE`
  o vista `AXES_LOCKOUT_URL`), extendiendo `base.html`.
- Texto en español (es-AR), explicando que espere unos minutos, con el branding.
- Opcional: indicar cuanto falta para poder reintentar.

**Notas:** es el cambio mas chico y rapido de esta lista; buen candidato para
arrancar. Verificar la config actual de axes (`AXES_*` en settings).

---

## 5. UX del tipo de billetera (facil de interpretar)

**Que:** al crear una billetera el usuario elige un `kind` (banco / billetera
virtual / efectivo / tarjeta de credito) que no siempre es obvio: *"voy a
registrar ICBC, ¿pongo tarjeta o banco?"*. El tipo es clave porque condiciona
que importador funciona y como se agrupan los movimientos.

**Por que:** un tipo mal elegido rompe el flujo **en silencio** — ej: un resumen
de tarjeta importado a una cuenta "banco" caia como gastos sueltos en vez de
agruparse. Salio de un bug real. El goal es que elegir el tipo sea **solido y
facil de interpretar**, o este bien explicado.

**Alcance / ideas:**
- Explicar cada tipo con un ejemplo al crear/editar la billetera (banco = caja de
  ahorro/cuenta; billetera virtual = MP/Ualá/Personal Pay; tarjeta de credito =
  resumen con cierre/vencimiento; efectivo).
- Aclarar que un mismo emisor (ICBC) puede tener **dos** billeteras distintas: la
  cuenta (banco) y la tarjeta (credito).
- Que el tipo se entienda desde la UI (iconos, hints) sin adivinar.
- Ya mitigado en parte: el importador ahora **restringe las billeteras
  compatibles por fuente** y valida en el backend. La raiz sigue siendo que el
  tipo se entienda al crear la billetera.

---

## 6. Cotizacion del dolar automatica (fetch diario via API)

**Que:** que todos los dias se traiga la cotizacion del dolar desde una API
publica y se actualice sola para cada usuario que tenga activado el modo
**"cotizacion automatica"** en su configuracion. Hoy la cotizacion del dolar en
Ahorros es 100% manual (el usuario escribe "el dolar esta a X").

**Por que:** el valor en pesos del patrimonio queda desactualizado si el usuario
no entra a cargar el dolar a mano. Un fetch diario lo mantiene al dia sin
esfuerzo, respetando siempre el fallback manual (regla de oro del CLAUDE.md).

**Alcance / piezas:**
- **Fuente de datos:** evaluar API de **dolarapi.com** (dolar blue/oficial/MEP/
  cripto, gratis y sin key) o el endpoint de cotizaciones de **AFIP/BCRA**.
  Elegir que "dolar" se usa por defecto (blue o cripto suelen ser los relevantes
  para ahorro). Nunca asumir que la API anda: si falla, se queda la ultima
  cotizacion manual/automatica cargada.
- **Config por usuario:** flag `auto_dollar_price` (bool) en `accounts.User`
  (o en un modelo de settings), editable desde Ajustes. Off por defecto para no
  pisar la cotizacion manual de quien la quiere fija.
- **Job diario:** un management command (`fetch_dollar_price`) corrido por cron/
  scheduler del VPS una vez al dia, que pegue a la API y haga un `PriceSnapshot`
  (`source="api"`) para los assets USD de los usuarios con el modo activado.
  Reusar `savings.services.set_dollar_price` (hoy es global; ver si conviene
  volverlo por-usuario cuando haya multi-user real).
- **UI:** en Ahorros, mostrar si la cotizacion vigente es automatica (API) o
  manual, y la fecha. Permitir siempre sobrescribir a mano (el manual gana hasta
  el proximo fetch, o se respeta segun se decida).

**Notas / riesgos:**
- Hoy `PriceSnapshot` y `set_dollar_price` son **globales** (no por usuario). El
  fetch diario encaja bien con eso mientras sea single-user; revisar al abrir
  multi-user.
- Es la Fase 5 (integracion automatica) del CLAUDE.md aplicada al dolar: tratar
  como spike, con fallback manual **siempre**.

---

## 7. Tour de onboarding (mapa para empezar a usar la app) [HECHO]

> Implementado: **tour spotlight** (resalta el elemento real en su lugar con un
> tooltip corto), sin deps, motor propio en `static/js/tour.js`. Cada pantalla
> tiene su "?" y resalta solo SUS elementos (no salta entre vistas): el del Mes
> muestra todo lo del Mes (8 pasos), el de Ajustes solo sus opciones (6 pasos).
> Auto-abre una vez en el Mes para usuarios nuevos (`accounts.User.has_seen_tour`
> + endpoint `dashboard:tour_seen`), re-lanzable desde el "?" de cada topbar.
> Targets marcados con `data-tour="..."`. Con tests.

**Que:** un **recorrido guiado** para el usuario nuevo, disparado desde un
**"?" arriba de todo** (siempre disponible, re-lanzable) y **auto-mostrado la
primera vez** (cuenta nueva / mes vacio, descartable). Va resaltando cada parte
de la app con un tooltip que explica que hacer, en orden de dependencias:

0. **Resto sueldo + ingresos** (el corazon): que es el numero grande y como
   cargar el sueldo / los ingresos del mes.
1. **Billeteras**: agregar las billeteras reales (banco, MP, Uala, efectivo,
   tarjeta) — es lo primero, todo lo demas cuelga de aca (el "DONDE").
2. **Gastos fijos**: cargar los fijos recurrentes (alquiler, servicios, gym…)
   para que aparezcan como checklist cada mes.
3. **Cargar un gasto suelto**: el "+" del Mes → monto, categoria, confirmar.
4. **Grande vs hormiga**: cuando un gasto cuenta como grande y cuando como
   hormiga, el **umbral** y el toggle de "gastos grandes automaticos" en Ajustes,
   y de paso para que sirven las **categorias**.
5. **Ahorro**: registrar compras de dolares y ver el patrimonio.
6. **Importar extractos**: subir el resumen de tarjeta / banco / MP para que las
   hormigas entren solas (sin cargarlas a mano).

**Por que:** hoy un usuario nuevo cae en un Mes vacio sin saber que **primero**
hay que cargar billeteras y fijos. Sin ese mapa, el numero de "resto sueldo" no
significa nada y la app parece vacia. El tour da el orden correcto para arrancar.

**Alcance / piezas:**
- **Disparadores:** icono "?" en la topbar (siempre), + auto-run la primera vez.
- **Persistencia:** guardar "tour completado" por usuario (bool en `accounts.User`)
  para no repetirlo en cada login; el "?" lo vuelve a lanzar cuando el usuario
  quiera.
- **Contenido por pasos:** cada paso apunta a un elemento real de la UI (la
  pestaña de Billeteras, el checklist de fijos, el "+", el umbral en Ajustes,
  etc.) con su tooltip. Ojo: algunos pasos viven en **otras pantallas** (Ajustes,
  Importar) — el tour tiene que poder navegar entre vistas o explicarlas sin
  exigir estar parado en cada una.
- **Como construirlo (sin CDN, self-host):** o **driver.js** vendorizado local
  (~5KB, hace justo esto: overlay + highlight + tooltip con pasos) o un mini-tour
  casero con Alpine (cero dependencias). Preferencia: driver.js por lo barato,
  respetando el "no meter deps pesadas" del CLAUDE.md. Todo el asset servido local
  (nada de `unpkg`), por la CSP del deploy.

**Notas:** mantenerlo corto (6-7 pasos, saltable en cualquier momento). No es un
wizard obligatorio: es un mapa opcional. A futuro, un "empty state" en cada
seccion podria reforzar el mismo mensaje sin depender del tour.
