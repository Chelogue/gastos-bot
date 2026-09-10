# Runbook

## El bot no responde

1. `curl https://<servicio>.a.run.app/health` → debe devolver `{"status":"ok"}`. Si no, mirá los
   logs de Cloud Run (filtro `severity>=WARNING`); todas las líneas llevan `update_id`.
2. `uv run python scripts/set_webhook.py --info` → `url` tiene que ser la de Cloud Run y
   `último error` vacío. Un 403 ahí significa que el `TELEGRAM_WEBHOOK_SECRET` de Secret Manager
   no coincide con el que se registró: volvé a correr `set_webhook.py --url ...`.
3. Si responde a uno y al otro no: el ID de Telegram tiene que estar en `Config` (tipo `persona`)
   **y** en `TELEGRAM_ALLOWED_IDS`. Los cambios en `Config` tardan hasta 5 min (caché).
4. "No pude leer el comprobante": el proveedor de LLM falló. Chequeá la key y la cuota en la
   consola del proveedor; el usuario puede reenviar la foto.
5. "No pude guardar el gasto": Sheets o Drive fallaron. No queda nada a medias (si Drive subió y
   Sheets falló, el archivo se borra). Revisá que la service account siga siendo editora del Sheet
   y de la carpeta `Gastos/`.

## Cambiar el tipo de cambio a mano

En `Config`, fila `tc | YYYY-MM`: editá `valor` (UYU por USD) y `vigente_desde`. Después:

```bash
uv run python scripts/recalc_dashboard.py --mes YYYY-MM
```

Eso recalcula `monto_usd` en el Dashboard del mes. Las filas del mes conservan su `tc_mes`
original; si querés reescribirlas, editá la columna en el Sheet.

## Rotar tokens

- **Token del bot:** @BotFather → /revoke, guardá el nuevo en Secret Manager
  (`gcloud secrets versions add TELEGRAM_BOT_TOKEN --data-file=-`), redeploy, y volvé a
  registrar el webhook.
- **Secret del webhook:** nueva versión del secreto + redeploy + `set_webhook.py --url ...`.
- **Key del LLM:** nueva versión de `LLM_API_KEY` + redeploy.

## Reparar el Sheet

`uv run python scripts/create_sheet.py` es idempotente: crea lo que falte (pestañas, encabezados,
filas de `Config`/`Categorias`, gráficos) sin pisar lo que ya está. Si un encabezado no coincide
con el esquema, avisa y no lo toca: corregilo a mano.

## Pendientes colgados

Los pendientes viven en la pestaña `Pendientes` 48 h. Borrar una fila a mano es seguro: el usuario
recibe "expiró, reenviá la foto" si toca un botón viejo.

## Primer deploy (checklist)

1. `infra/setup_gcp.sh <PROJECT_ID>` (idempotente): APIs, service account, Artifact Registry,
   secretos, Workload Identity para GitHub Actions.
2. Compartir el Sheet y la carpeta `Gastos/` con el email de la service account (editor).
3. Cargar los secretos: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_WEBHOOK_SECRET`, `LLM_API_KEY`.
4. Push a `main` → deploy. Verificar `/health`.
5. `uv run python scripts/set_webhook.py --url https://<servicio>.a.run.app/webhook`.
6. Mandar `/start` desde cada uno de los dos chats.
