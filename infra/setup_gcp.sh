#!/usr/bin/env bash
# Prepara el proyecto de GCP para gastos-bot. Idempotente: se puede correr las veces que haga falta.
#
# Uso:  infra/setup_gcp.sh <PROJECT_ID> [REGION] [GITHUB_REPO]
#       infra/setup_gcp.sh gastos-bot-508217 us-central1 Chelogue/gastos-bot
#
# Requiere: gcloud autenticado (gcloud auth login) y facturación habilitada en el proyecto.
# Qué crea (todo dentro del free tier salvo el almacenamiento de imágenes en Artifact Registry):
#   - APIs: Cloud Run, Artifact Registry, Secret Manager, Cloud Scheduler, IAM Credentials, STS,
#     Sheets, Drive
#   - Service account del servicio (gastos-bot-sa) con acceso a secretos únicamente. Sheets y
#     Drive no usan IAM: hay que compartir el Sheet y la carpeta con su email como editor.
#   - Repositorio Docker en Artifact Registry
#   - Secretos vacíos (se cargan aparte, ver abajo): TELEGRAM_BOT_TOKEN, TELEGRAM_WEBHOOK_SECRET,
#     LLM_API_KEY
#   - Workload Identity Federation para que GitHub Actions despliegue sin JSON keys, con una
#     service account de deploy (gastos-bot-deployer) que puede subir imágenes y desplegar.
#
# Cargar un secreto (una versión nueva cada vez):
#   printf '%s' "$VALOR" | gcloud secrets versions add TELEGRAM_BOT_TOKEN --data-file=- --project "$PROJECT_ID"
set -euo pipefail

PROJECT_ID="${1:?PROJECT_ID requerido}"
REGION="${2:-us-central1}"
GITHUB_REPO="${3:-Chelogue/gastos-bot}"
SERVICE="gastos-bot"
SA_RUN="gastos-bot-sa"
SA_DEPLOY="gastos-bot-deployer"
AR_REPO="gastos-bot"
POOL="github-pool"
PROVIDER="github-provider"

say() { printf '\n== %s\n' "$*"; }

say "Proyecto $PROJECT_ID, región $REGION"
gcloud config set project "$PROJECT_ID" --quiet >/dev/null
PROJECT_NUMBER="$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')"

say "APIs"
gcloud services enable \
  run.googleapis.com artifactregistry.googleapis.com secretmanager.googleapis.com \
  cloudscheduler.googleapis.com iamcredentials.googleapis.com sts.googleapis.com \
  sheets.googleapis.com drive.googleapis.com cloudbuild.googleapis.com --quiet

ensure_sa() {
  local name="$1" display="$2"
  if ! gcloud iam service-accounts describe "$name@$PROJECT_ID.iam.gserviceaccount.com" >/dev/null 2>&1; then
    gcloud iam service-accounts create "$name" --display-name="$display" --quiet
  fi
}

say "Service account del servicio"
ensure_sa "$SA_RUN" "gastos-bot (Cloud Run)"
SA_RUN_EMAIL="$SA_RUN@$PROJECT_ID.iam.gserviceaccount.com"

say "Artifact Registry"
if ! gcloud artifacts repositories describe "$AR_REPO" --location="$REGION" >/dev/null 2>&1; then
  gcloud artifacts repositories create "$AR_REPO" --repository-format=docker --location="$REGION" \
    --description="Imágenes de gastos-bot" --quiet
fi

say "Secretos"
for s in TELEGRAM_BOT_TOKEN TELEGRAM_WEBHOOK_SECRET LLM_API_KEY; do
  if ! gcloud secrets describe "$s" >/dev/null 2>&1; then
    gcloud secrets create "$s" --replication-policy=automatic --quiet
  fi
  gcloud secrets add-iam-policy-binding "$s" --member="serviceAccount:$SA_RUN_EMAIL" \
    --role="roles/secretmanager.secretAccessor" --quiet >/dev/null
done

say "Service account de deploy + Workload Identity Federation ($GITHUB_REPO)"
ensure_sa "$SA_DEPLOY" "gastos-bot deploy desde GitHub Actions"
SA_DEPLOY_EMAIL="$SA_DEPLOY@$PROJECT_ID.iam.gserviceaccount.com"
for role in roles/run.admin roles/artifactregistry.writer roles/iam.serviceAccountUser; do
  gcloud projects add-iam-policy-binding "$PROJECT_ID" --member="serviceAccount:$SA_DEPLOY_EMAIL" \
    --role="$role" --quiet >/dev/null
done
if ! gcloud iam workload-identity-pools describe "$POOL" --location=global >/dev/null 2>&1; then
  gcloud iam workload-identity-pools create "$POOL" --location=global --display-name="GitHub" --quiet
fi
if ! gcloud iam workload-identity-pools providers describe "$PROVIDER" --location=global \
     --workload-identity-pool="$POOL" >/dev/null 2>&1; then
  gcloud iam workload-identity-pools providers create-oidc "$PROVIDER" --location=global \
    --workload-identity-pool="$POOL" --display-name="GitHub OIDC" \
    --issuer-uri="https://token.actions.githubusercontent.com" \
    --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository" \
    --attribute-condition="assertion.repository == '$GITHUB_REPO'" --quiet
fi
PROVIDER_NAME="projects/$PROJECT_NUMBER/locations/global/workloadIdentityPools/$POOL/providers/$PROVIDER"
gcloud iam service-accounts add-iam-policy-binding "$SA_DEPLOY_EMAIL" \
  --role="roles/iam.workloadIdentityUser" \
  --member="principalSet://iam.googleapis.com/projects/$PROJECT_NUMBER/locations/global/workloadIdentityPools/$POOL/attribute.repository/$GITHUB_REPO" \
  --quiet >/dev/null

say "Listo. Valores para los secretos del repo de GitHub (Settings → Secrets → Actions):"
echo "  GCP_PROJECT_ID          = $PROJECT_ID"
echo "  GCP_REGION              = $REGION"
echo "  GCP_WIF_PROVIDER        = $PROVIDER_NAME"
echo "  GCP_DEPLOY_SA           = $SA_DEPLOY_EMAIL"
echo
echo "Compartir como EDITOR con la service account del servicio:"
echo "  $SA_RUN_EMAIL   (el Sheet y la carpeta Gastos/ de Drive)"
echo
echo "Secretos pendientes de cargar (ver cabecera de este script): TELEGRAM_BOT_TOKEN, TELEGRAM_WEBHOOK_SECRET, LLM_API_KEY"
