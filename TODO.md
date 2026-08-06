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

## 2. Multiples fuentes de ingreso (sueldo + extras)

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

**Notas:** decidir si un ingreso es una fila de `Transaction (income)` (mas simple,
unifica con el flujo) o una entidad aparte del presupuesto. Confirmar el modelo
contra `CLAUDE.md` antes de codear.

---

## 3. Login con Google (OAuth)

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

## 4. Aviso estilizado al bloquearse por reintentos (django-axes)

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
