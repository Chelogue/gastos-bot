# gastos-bot

Bot de Telegram para que dos personas registren gastos con una foto, los archiven en Google Drive, los organicen en Google Sheets y reciban un reporte quincenal con la regla 50/30/20.

- **Producto:** `docs/PRD.md` (fuente de verdad)
- **Código y prácticas:** `docs/estructura.md`
- **Reglas para Claude Code:** `CLAUDE.md`
- **Decisiones:** `docs/decisions/`
- **Operación:** `docs/runbook.md`

## Requisitos

`uv` (gestiona Python 3.12), `gcloud`, `cloudflared` para el túnel local. En macOS: `brew install uv cloudflared && brew install --cask google-cloud-sdk`.

## Correr en local

```bash
uv sync --all-extras
cp .env.example .env            # completar valores (ver abajo)
uv run pytest                   # sin red ni credenciales
uv run python scripts/autorizar_google.py    # abre el navegador y deja el token en .env (ADR 0006)
uv run python scripts/create_sheet.py --ids Marcelo=<id>,Nikole=<id>   # crea/repara el Sheet
./scripts/run_local.sh          # uvicorn + túnel cloudflared
uv run python scripts/set_webhook.py --url https://<tunel>.trycloudflare.com/webhook
```

Qué va en `.env`:

| Variable | Dónde se consigue |
|---|---|
| `TELEGRAM_BOT_TOKEN` | @BotFather → /newbot |
| `TELEGRAM_WEBHOOK_SECRET` | `openssl rand -hex 24` |
| `TELEGRAM_ALLOWED_IDS` | @userinfobot te dice tu ID (los dos, separados por coma) |
| `LLM_PROVIDER` / `LLM_MODEL` / `LLM_API_KEY` | `gemini` + `gemini-3.6-flash` + key de AI Studio (tier pago) |
| `GOOGLE_SHEET_ID` | el ID en la URL del Sheet (creá uno vacío y compartilo como editor con tu cuenta y con la service account) |
| `GOOGLE_DRIVE_ROOT_FOLDER_ID` | el ID en la URL de la carpeta `Gastos/` en Drive (compartida igual) |
| `GOOGLE_OAUTH_TOKEN_JSON` | lo escribe `scripts/autorizar_google.py` (necesita `GOOGLE_OAUTH_CLIENT_ID` y `GOOGLE_OAUTH_CLIENT_SECRET` del cliente de escritorio) |
| `JOBS_OIDC_EMAIL` / `JOBS_AUDIENCE` | solo en Cloud Run: los pone el deploy para validar las llamadas de Cloud Scheduler |

**Por qué un token de usuario y no la service account:** una service account no tiene cuota de
Drive (sube y falla con `storageQuotaExceeded`), así que Drive y Sheets se usan con el token OAuth
de Marcelo (ADR 0006). Los archivos quedan en su Drive, dentro de la carpeta compartida.

## Jobs (tipo de cambio y reporte)

Cloud Scheduler llama dos endpoints con un token OIDC que el servicio verifica (R14):

| Job | Cuándo | Qué hace |
|---|---|---|
| `POST /jobs/fx` | día 1, 00:05 | fija el UYU/USD del mes en `Config` (ADR 0007), reconvierte las filas del mes y recalcula el Dashboard |
| `POST /jobs/reporte` | días 1 y 16, 09:00 | manda a los dos el reporte de la quincena que cerró, con el avance del mes contra los topes 50/30/20 |

Se crean con `infra/setup_scheduler.sh <PROJECT_ID> us-central1` (idempotente, free tier). Para
dispararlos a mano, `gcloud scheduler jobs run gastos-bot-fx --location us-central1`. Detalles y
diagnóstico en `docs/runbook.md`.

## Bake-off de modelos (R19)

Poné 30 comprobantes en `tests/fixtures/comprobantes/` y su verdad en `tests/fixtures/ground_truth.json` (ver el README de esa carpeta). Después:

```bash
uv run python tests/evals/run_extraction_eval.py --provider gemini --model gemini-3.6-flash
uv run python tests/evals/run_extraction_eval.py --provider anthropic --model claude-haiku-4-5
```

Imprime precisión por campo, % de comprobantes que no habría que editar, latencia media y p95. El resultado se documenta en el ADR del proveedor elegido.

## Deploy

Imagen: `docker build -t gastos-bot .` (probado con colima). En producción, push a `main` → GitHub Actions construye la imagen y despliega a Cloud Run (`.github/workflows/deploy.yml`, con Workload Identity). Los secretos viven en Secret Manager; ninguno en el repo. Primer deploy y registro del webhook: ver `docs/runbook.md`.

## Estado

Ver la sección "Estado" en `CLAUDE.md`.
