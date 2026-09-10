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

**Fase en curso:** Fase 0 (infra y plantilla). Nada implementado aún; el scaffold contiene solo docs, config y estructura de carpetas.
**Requerimientos cerrados:** ninguno.
