# gastos-bot — Estructura del repositorio

Monorepo pequeño, Python 3.12, un solo servicio desplegado en Cloud Run. Pensado para que Claude Code lo construya por fases y para que en seis meses cualquiera entienda dónde está cada cosa.

```
gastos-bot/
├── README.md                      # qué es, cómo correr local, cómo desplegar (5 min de lectura)
├── CLAUDE.md                      # instrucciones para Claude Code (ver abajo)
├── docs/
│   ├── PRD.md                     # el PRD v1.0, fuente de verdad del producto
│   ├── decisions/                 # ADRs cortos: 0001-llm-provider.md, 0002-sheet-as-db.md, …
│   └── runbook.md                 # qué hacer si el bot no responde, rotar tokens, cambiar TC a mano
├── pyproject.toml                 # deps con uv; ruff, pytest, mypy configurados aquí
├── uv.lock
├── .python-version                # 3.12
├── .env.example                   # todas las variables, sin valores
├── .gitignore                     # .env, tests/fixtures/comprobantes/*.jpg, *.json de credenciales
├── .pre-commit-config.yaml        # ruff format + ruff check + mypy
├── Dockerfile                     # multi-stage, uv, usuario no-root, puerto $PORT
├── .dockerignore
├── .github/
│   └── workflows/
│       ├── ci.yml                 # lint + tests en cada PR
│       └── deploy.yml             # build → Artifact Registry → Cloud Run, en push a main, con Workload Identity
├── infra/
│   ├── setup_gcp.sh               # habilita APIs, crea SA, secretos, Artifact Registry, Scheduler jobs (idempotente)
│   ├── setup_scheduler.sh         # crea los dos jobs (fx, reporte) con OIDC, idempotente
│   └── cloudrun.yaml              # servicio: min-instances 0, timeout 120s, env vars, secretos montados
├── scripts/
│   ├── create_sheet.py            # crea el Sheet completo: Dashboard, Config, Categorias, Pendientes, plantilla de mes, gráficos
│   ├── set_webhook.py             # registra el webhook en Telegram con secret token
│   ├── run_local.sh               # uvicorn + túnel (ngrok/cloudflared) para probar con Telegram real
│   └── recalc_dashboard.py        # recalcula el Dashboard entero (útil tras editar TC a mano)
├── src/gastos_bot/
│   ├── __init__.py
│   ├── main.py                    # FastAPI: POST /webhook, POST /jobs/fx, POST /jobs/reporte, GET /health
│   ├── config.py                  # pydantic-settings: lee env vars; falla al arrancar si falta alguna
│   ├── logging.py                 # structlog → JSON para Cloud Logging, con update_id en cada línea
│   ├── auth.py                    # verifica secret token de Telegram y OIDC de Scheduler
│   │
│   ├── domain/                    # lógica pura, sin I/O, 100 % testeable
│   │   ├── models.py              # Gasto, Pendiente, Extraccion, Persona, Config (Pydantic)
│   │   ├── categorias.py          # subcategoría → rubro, validación contra la lista
│   │   ├── quincena.py            # Q1/Q2, rangos de fechas, zona horaria
│   │   ├── fx.py                  # conversión a USD con TC del mes
│   │   ├── indicador.py           # cálculo 50/30/20, tasa de ahorro, cumplimiento
│   │   ├── naming.py              # nombre de archivo y de carpeta en Drive, slug de comercio
│   │   └── ids.py                 # generación de G-YYMMDD-NNN
│   │
│   ├── extraction/                # el LLM
│   │   ├── base.py                # interfaz: extract(image_bytes | text, categorias) -> Extraccion
│   │   ├── prompts.py             # prompt de extracción (reglas $ / U$S, cuotas, reembolsos)
│   │   ├── schema.py              # JSON schema que se le pasa al modelo
│   │   ├── gemini.py
│   │   ├── anthropic.py
│   │   ├── deepseek.py
│   │   └── factory.py             # elige proveedor por LLM_PROVIDER
│   │
│   ├── storage/                   # I/O con Google
│   │   ├── sheets.py              # cliente gspread; pestaña del mes, Config, Categorias (con caché)
│   │   ├── pendientes.py          # CRUD de Pendientes + expiración + dedupe de update_id
│   │   ├── drive.py               # carpetas por mes/persona (IDs cacheados), subida, borrado
│   │   └── dashboard.py           # recalcula la fila del mes en Dashboard
│   │
│   ├── bot/                       # Telegram
│   │   ├── app.py                 # construye la Application de python-telegram-bot
│   │   ├── handlers/
│   │   │   ├── media.py           # fotos, documentos, álbumes
│   │   │   ├── text.py            # registro por texto y lenguaje natural ("cuánto llevamos")
│   │   │   ├── callbacks.py       # botones de la tarjeta (compartido/personal, guardar, editar…)
│   │   │   └── commands.py        # /start /ayuda /total /ultimos /borrar /editar
│   │   ├── keyboards.py           # construcción de inline keyboards
│   │   ├── messages.py            # todos los textos que ve el usuario, en un solo lugar
│   │   └── flow.py                # orquesta: extracción → pendiente → tarjeta → confirmar → Drive → Sheets → Dashboard
│   │
│   ├── reports/
│   │   ├── quincenal.py           # arma el reporte del día 1 y 16
│   │   └── formatting.py          # números, monedas, porcentajes, barras de progreso en texto
│   │
│   └── jobs/
│       ├── fx_job.py              # obtiene TC y lo guarda en Config
│       └── report_job.py          # genera y envía el reporte a ambos
│
└── tests/
    ├── conftest.py                # fixtures: config de prueba, cliente de Sheets falso, LLM falso
    ├── unit/                      # domain/ y reports/ sin I/O
    ├── integration/               # sheets/drive contra un Sheet de pruebas (marcados, no corren en CI por defecto)
    ├── fixtures/
    │   ├── comprobantes/          # 30 imágenes reales (gitignored) + README con cómo obtenerlas
    │   └── ground_truth.json      # respuesta correcta de cada comprobante
    └── evals/
        └── run_extraction_eval.py # corre los 30 por cada proveedor, imprime precisión por campo
```

## Prácticas que el repo debe respetar

**Separación por capas.** `domain/` no importa nada de `storage/`, `bot/` ni `extraction/`. Toda la lógica de negocio (quincenas, 50/30/20, nombres de archivo, IDs) es funciones puras con tests. `bot/flow.py` es el único lugar que conecta las capas.

**Un proveedor de LLM es un adaptador.** `extraction/base.py` define la interfaz; cada proveedor la implementa; `factory.py` elige por env var. El prompt y el schema son compartidos. Nadie fuera de `extraction/` sabe qué modelo corre.

**Textos en un solo archivo.** Todo lo que el usuario lee en Telegram vive en `bot/messages.py`. Cambiar un texto no toca lógica.

**Configuración validada al arrancar.** `config.py` con `pydantic-settings`; si falta una variable el servicio no levanta y lo dice en el log. Nunca `os.getenv` suelto por el código.

**Secretos.** Ninguno en el repo ni en la imagen. En Cloud Run se montan desde Secret Manager como variables de entorno. Local: `.env` (gitignored). Deploy desde GitHub con Workload Identity Federation: sin JSON keys de service account en ningún lado.

**Idempotencia y orden de escritura.** `update_id` deduplicado antes de tocar nada. Al confirmar: Drive → Sheets → Dashboard; si Sheets falla, se borra lo subido a Drive. Nunca una fila sin imagen ni una imagen sin fila.

**Logs estructurados.** `structlog` en JSON con `update_id`, `telegram_id` (no el nombre), `pendiente_id`. Nunca se loguea el contenido de la imagen ni el JSON completo de extracción en producción (son datos financieros).

**Tests que valen la pena.** `domain/` al 100 %. `bot/flow.py` con un LLM falso y un Sheets falso. `evals/` no es un test: es un script que se corre a mano para elegir modelo y se documenta el resultado en un ADR.

**Commits pequeños, ramas por fase.** `feat/fase-1-nucleo`, PR con checklist de los requerimientos del PRD que cubre. CI verde antes de mergear. `main` siempre desplegable.

**ADRs.** Cada decisión que costó discutir se escribe en `docs/decisions/` en 10 líneas: contexto, decisión, consecuencias. Empezar por: proveedor de LLM (con los números del bake-off), Sheet como base de datos, Dashboard mantenido por el bot vs. fórmulas.

## Variables de entorno (`.env.example`)

```
# Telegram
TELEGRAM_BOT_TOKEN=
TELEGRAM_WEBHOOK_SECRET=          # string aleatorio, se pasa a setWebhook y se verifica en cada request
TELEGRAM_ALLOWED_IDS=             # respaldo; la fuente real es la pestaña Config

# LLM
LLM_PROVIDER=gemini               # gemini | anthropic | deepseek
LLM_MODEL=                        # nombre exacto del modelo
LLM_API_KEY=

# Google
GOOGLE_SHEET_ID=
GOOGLE_DRIVE_ROOT_FOLDER_ID=      # carpeta Gastos/
GOOGLE_APPLICATION_CREDENTIALS=   # solo en local; en Cloud Run se usa la SA nativa

# App
TZ=America/Montevideo
PENDIENTE_TTL_HOURS=48
FX_API_URL=                       # se define en Fase 2
LOG_LEVEL=INFO
```

## CLAUDE.md (contenido)

```markdown
# gastos-bot

Bot de Telegram que registra gastos de dos personas en Google Sheets y Drive, y reporta con la regla 50/30/20.
La fuente de verdad del producto es docs/PRD.md. Si algo en el código contradice el PRD, gana el PRD; si el PRD
es ambiguo, pregunta antes de decidir.

## Comandos
- `uv sync` — instalar deps
- `uv run pytest` — tests unitarios (rápidos, sin red)
- `uv run pytest -m integration` — contra el Sheet de pruebas (requiere .env)
- `uv run ruff check . && uv run ruff format .` — lint
- `uv run python scripts/create_sheet.py` — crea/repara la estructura del Sheet
- `uv run python tests/evals/run_extraction_eval.py --provider gemini` — bake-off
- `./scripts/run_local.sh` — servidor local con túnel para Telegram

## Reglas del proyecto
- Python 3.12, tipado, ruff, tests para todo lo de src/gastos_bot/domain/.
- domain/ es puro: sin imports de storage/, bot/ ni extraction/.
- Textos de usuario solo en bot/messages.py. En español rioplatense, tuteo, sin emojis excesivos (los de la tarjeta sí).
- Nunca loguear imágenes ni JSON de extracción completos. Nunca commitear .env, credenciales ni comprobantes.
- Orden de escritura al confirmar: Drive → Sheets → Dashboard, con rollback de Drive si Sheets falla.
- Todo update_id se deduplica antes de procesar.
- Los proveedores de LLM se agregan como adaptadores en extraction/; nunca condicionales por proveedor fuera de ahí.
- Cada decisión no trivial → ADR en docs/decisions/.
- No desplegar a Cloud Run ni cambiar el webhook de Telegram sin confirmación explícita del usuario.

## Estado
Ver docs/PRD.md §13 (fases). Marcar aquí la fase en curso y los requerimientos cerrados.
```
