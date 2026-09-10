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

**Fase en curso:** Fase 0 (infra) a la espera de credenciales; Fase 1 (núcleo) construida y testeada
con dobles, pendiente de probar contra Telegram/Google reales y de correr el bake-off (R19).

**Hecho (2026-09-10):** toolchain, CI, config validada, logs JSON, FastAPI con /health y /webhook,
Dockerfile verificado, `create_sheet.py`, `set_webhook.py`, `recalc_dashboard.py`, `domain/`
completo, `extraction/` (Gemini, Claude, DeepSeek + bake-off), `storage/` real y fakes, `bot/`
(tarjeta de dos pasos, flujo completo con rollback). 169 tests sin red. ADRs 0001–0005.

**Falta de Fase 0:** `infra/setup_gcp.sh`, `infra/cloudrun.yaml`, `.github/workflows/deploy.yml`,
primer deploy y webhook (requieren proyecto GCP, `gcloud auth login` y OK explícito).

**Requerimientos cerrados (con tests, sin validación real aún):** R1, R2, R3, R4, R5, R6, R14, R16,
R17, R18. R19 tiene el script listo; faltan los 30 comprobantes. R15 al desplegar.
