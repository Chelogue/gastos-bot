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

## Tipo de cambio (R7)

Lo fija solo el job `/jobs/fx` el día 1 a las 00:05, con la cotización de open.er-api.com
(ADR 0007). Si la API no responde, reusa el del mes anterior y avisa por Telegram.

**Cambiarlo a mano:** en `Config`, fila `tc | YYYY-MM`, editá `valor` (UYU por USD). El bot lo
toma solo dentro de los 5 minutos del caché. Para que las filas del mes y el Dashboard queden
con el número nuevo, cualquiera de estas dos cosas:

```bash
uv run python scripts/recalc_dashboard.py --mes YYYY-MM   # reconvierte y recalcula, al toque
```

o esperar al próximo reporte quincenal, que reconvierte antes de contar.

**Fijarlo ahora (sin esperar al día 1):**

```bash
gcloud scheduler jobs run gastos-bot-fx --location us-central1
```

Si el mes ya tiene TC, el job no hace nada. Para pisarlo hay que forzarlo:

```bash
curl -X POST "https://<servicio>.a.run.app/jobs/fx?forzar=true" \
  -H "X-Telegram-Bot-Api-Secret-Token: $TELEGRAM_WEBHOOK_SECRET"
```

## Los jobs de Cloud Scheduler (R7, R9)

| Job | Cuándo | Qué hace |
|---|---|---|
| `gastos-bot-fx` | día 1, 00:05 | fija el TC del mes, reconvierte las filas y recalcula el Dashboard |
| `gastos-bot-reporte` | días 1 y 16, 09:00 | manda el reporte de la quincena a los dos y cierra el mes en el Dashboard |

Se crean o actualizan con `infra/setup_scheduler.sh gastos-bot-508217 us-central1` (idempotente,
dentro del free tier). Ver qué pasó:

```bash
gcloud scheduler jobs list --location us-central1
gcloud scheduler jobs describe gastos-bot-reporte --location us-central1   # lastAttemptTime, status
gcloud run services logs read gastos-bot --region us-central1 --limit 50
```

**No llegó el reporte.** Mirá los logs del servicio: si dice `reporte_sin_tc`, falta el TC del mes
en `Config` (y los dos recibieron un aviso). Si el job figura con error, reintenta solo hasta tres
veces; después se dispara a mano con `gcloud scheduler jobs run gastos-bot-reporte
--location us-central1`.

**403 en los jobs.** El servicio verifica el token OIDC contra `JOBS_OIDC_EMAIL` y `JOBS_AUDIENCE`.
Si cambió la URL del servicio, actualizá la variable de repo `CLOUD_RUN_URL`, redesplegá y volvé a
correr `infra/setup_scheduler.sh` (la audiencia tiene que coincidir).

## Reautorizar Google (Drive/Sheets dejan de responder con 401/invalid_grant)

El bot usa el token OAuth de Marcelo (ADR 0006). Se invalida si cambia la contraseña, si quita
el acceso en https://myaccount.google.com/permissions o si Google lo expira. Para renovarlo:

```bash
uv run python scripts/autorizar_google.py --client-id "$GOOGLE_OAUTH_CLIENT_ID" --client-secret "$GOOGLE_OAUTH_CLIENT_SECRET"
grep '^GOOGLE_OAUTH_TOKEN_JSON=' .env | cut -d= -f2- | gcloud secrets versions add GOOGLE_OAUTH_TOKEN_JSON --data-file=- --project gastos-bot-508217
```

Después, un redeploy (push a `main` o "Re-run" del workflow Deploy) para que Cloud Run tome la
versión nueva del secreto. El cliente OAuth está en Google Auth Platform → Clientes.

## Rotar tokens

- **Token del bot:** @BotFather → /revoke, guardá el nuevo en Secret Manager
  (`gcloud secrets versions add TELEGRAM_BOT_TOKEN --data-file=-`), redeploy, y volvé a
  registrar el webhook.
- **Secret del webhook:** nueva versión del secreto + redeploy + `set_webhook.py --url ...`.
- **Key del LLM:** nueva versión de `LLM_API_KEY` + redeploy.

## Cambiar las columnas del Sheet

Cuando el esquema suma o renombra una columna (p. ej. `inversion_usd`, ADR 0008), después de
desplegar hay que migrar el Sheet una vez, en este orden:

```bash
uv run python scripts/create_sheet.py --reescribir-encabezados
```

Eso ensancha la grilla, reescribe la fila 1 con las etiquetas nuevas y crea los gráficos que
falten. Sin `--reescribir-encabezados` el script avisa y no toca un encabezado que no reconoce,
que es lo que queremos en el uso normal. Después:

```bash
uv run python scripts/recalc_dashboard.py
```

para reescribir las filas de cada mes con el orden de columnas nuevo.

## Reparar el Sheet

`uv run python scripts/create_sheet.py` es idempotente: crea lo que falte (pestañas, encabezados,
filas de `Config`/`Categorias`, gráficos) sin pisar lo que ya está. Si un encabezado no coincide
con el esquema, avisa y no lo toca: corregilo a mano.

## Pendientes colgados

Los pendientes viven en la pestaña `Pendientes` 48 h. Borrar una fila a mano es seguro: el usuario
recibe "expiró, reenviá la foto" si toca un botón viejo.

## Primer deploy (checklist)

1. `infra/setup_gcp.sh gastos-bot-508217 us-central1 Chelogue/gastos-bot` (idempotente): APIs,
   service accounts, Artifact Registry, secretos, Workload Identity para GitHub Actions.
2. Compartir el Sheet y la carpeta `Gastos/` con el email de la service account (editor).
3. Cargar los secretos: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_WEBHOOK_SECRET`, `LLM_API_KEY`,
   `GOOGLE_OAUTH_TOKEN_JSON` (ver "Reautorizar Google").
4. Variable de repo `DEPLOY_ENABLED=true` y push a `main` → deploy. Verificar `/health`.
5. `uv run python scripts/set_webhook.py --url https://<servicio>.a.run.app/webhook`.
6. Mandar `/start` desde cada uno de los dos chats.
7. Variable de repo `CLOUD_RUN_URL=https://<servicio>.a.run.app` y redeploy (es la audiencia OIDC).
8. `infra/setup_scheduler.sh <PROJECT_ID> us-central1` y probar con
   `gcloud scheduler jobs run gastos-bot-reporte --location us-central1`.
