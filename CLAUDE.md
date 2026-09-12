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
- Al leer el Sheet, valores sin formatear: formateados dependen del idioma de la planilla (es_MX).
- No desplegar a Cloud Run ni cambiar el webhook de Telegram sin confirmación explícita del usuario.

## Estado
Ver docs/PRD.md §13 (fases). Marcar aquí la fase en curso y los requerimientos cerrados.

**Fase en curso:** ninguna: fases 0 a 4 desplegadas. El 2026-09-12 se sumó el objetivo de ahorro
e inversión (ADR 0010), la pestaña `Movimientos` para tableros (ADR 0011) y se arregló un bug que
descartaba en silencio toda fila de mil o más al leer el Sheet (es_MX formatea «1,167.50»). El
tablero de Looker Studio lo arma Marcelo siguiendo `docs/looker.md`. Abierto: el bake-off R19.

**Infra real:** GitHub Actions → Artifact Registry → Cloud Run (`DEPLOY_ENABLED=true`); secretos
en Secret Manager; Drive y Sheets con el token OAuth de Marcelo (ADR 0006), no con la service
account (cuota 0 en Drive). Modelo `gemini-3.6-flash`. Webhook registrado en la URL de Cloud Run.
Cloud Scheduler llama `/jobs/fx` (día 1, 00:05) y `/jobs/reporte` (días 1 y 16, 09:00) con un
token OIDC de `gastos-bot-sa`, que el servicio verifica contra `JOBS_OIDC_EMAIL` y `JOBS_AUDIENCE`
(variable de repo `CLOUD_RUN_URL`).

**Requerimientos cerrados:** R1–R6, R14–R18 (validados de punta a punta con fotos reales el
2026-09-10). R7, R8, R10 y la autorización OIDC de los jobs: en producción y verificados.
R9: el reporte se probó con los datos reales del Sheet contra Telegram; falta verlo salir solo
el día 16. R11, R12, R13: desplegados; `/total` y `/ultimos` verificados en producción, `/editar`
y `/borrar` cubiertos por tests. R20–R24 (P1): desplegados; `/dashboard` verificado en producción. R19: único requerimiento
abierto, el script está listo y faltan los 30 comprobantes.
