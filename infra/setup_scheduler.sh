#!/usr/bin/env bash
# Crea (o actualiza) los dos jobs de Cloud Scheduler de la Fase 2. Idempotente.
#
# Uso:  infra/setup_scheduler.sh <PROJECT_ID> [REGION]
#       infra/setup_scheduler.sh gastos-bot-508217 us-central1
#
# Qué crea, con qué permisos y qué cuesta:
#   - gastos-bot-fx      → POST /jobs/fx      el día 1 a las 00:05 (R7)
#   - gastos-bot-reporte → POST /jobs/reporte los días 1 y 16 a las 09:00 (R9)
#     Ambos en zona America/Montevideo, con 3 reintentos si el servicio devuelve error.
#   - Costo: el free tier de Cloud Scheduler son 3 jobs por cuenta de facturación; estos dos
#     entran ahí, así que no suman nada. Los 3 disparos por mes a Cloud Run también son free tier.
#   - Permisos: para crear un job que firme tokens OIDC con la service account del servicio hace
#     falta actAs sobre ella (lo tiene el dueño del proyecto). La API cloudscheduler.googleapis.com
#     ya la habilita infra/setup_gcp.sh.
#   - Seguridad: cada llamada lleva un token OIDC firmado por la SA del servicio; el bot verifica
#     firma, audiencia y email (R14, auth.require_job_auth). No abre ningún endpoint nuevo.
#
# El servicio tiene que tener seteadas JOBS_OIDC_EMAIL y JOBS_AUDIENCE (las pone el deploy).
# Para probar un job sin esperar al cron:
#   gcloud scheduler jobs run gastos-bot-reporte --location us-central1
set -euo pipefail

PROJECT_ID="${1:?PROJECT_ID requerido}"
REGION="${2:-us-central1}"
SERVICE="gastos-bot"
SA_RUN="gastos-bot-sa@$PROJECT_ID.iam.gserviceaccount.com"

say() { printf '\n== %s\n' "$*"; }

gcloud config set project "$PROJECT_ID" --quiet >/dev/null
SERVICE_URL="$(gcloud run services describe "$SERVICE" --region "$REGION" --format 'value(status.url)')"
[ -n "$SERVICE_URL" ] || { echo "No encontré el servicio $SERVICE en $REGION" >&2; exit 1; }
say "Servicio en $SERVICE_URL"

ensure_job() {
  local name="$1" schedule="$2" ruta="$3" descripcion="$4"
  local accion=create
  gcloud scheduler jobs describe "$name" --location="$REGION" >/dev/null 2>&1 && accion=update
  say "$accion $name  ($schedule)"
  gcloud scheduler jobs "$accion" http "$name" \
    --location="$REGION" \
    --schedule="$schedule" \
    --time-zone="America/Montevideo" \
    --uri="$SERVICE_URL$ruta" \
    --http-method=POST \
    --oidc-service-account-email="$SA_RUN" \
    --oidc-token-audience="$SERVICE_URL" \
    --attempt-deadline=180s \
    --max-retry-attempts=3 \
    --min-backoff=60s \
    --description="$descripcion" \
    --quiet
}

ensure_job gastos-bot-fx "5 0 1 * *" /jobs/fx \
  "Fija el tipo de cambio del mes en Config (R7)"
ensure_job gastos-bot-reporte "0 9 1,16 * *" /jobs/reporte \
  "Reporte quincenal a Marcelo y Nikole (R9)"

say "Listo. Variables que el servicio tiene que tener:"
echo "  JOBS_OIDC_EMAIL = $SA_RUN"
echo "  JOBS_AUDIENCE   = $SERVICE_URL"
