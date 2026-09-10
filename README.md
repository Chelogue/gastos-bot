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
gcloud auth application-default login \
  --impersonate-service-account=gastos-bot-sa@<PROJECT_ID>.iam.gserviceaccount.com
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
| `GOOGLE_APPLICATION_CREDENTIALS` | vacío: en local ADC impersona a la service account (ver nota); en Cloud Run se usa la SA nativa |

**Por qué impersonar y no pedir scopes de Drive:** Google bloquea el cliente OAuth de gcloud
cuando pide el scope de Drive ("Se bloqueó esta app"). Con `--impersonate-service-account` las
credenciales locales piden tokens en nombre de la service account del bot, que ya es editora del
Sheet y de la carpeta, y no hace falta ningún JSON key. Requiere ser Owner del proyecto o tener
`roles/iam.serviceAccountTokenCreator` sobre esa cuenta.

Las imágenes que sube la service account quedan en la carpeta compartida pero cuentan contra la cuota de la service account (15 GB): sobra por años.

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
