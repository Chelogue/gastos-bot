#!/usr/bin/env bash
# Levanta el servicio en local con recarga y abre un túnel cloudflared para que Telegram
# pueda llegar al webhook. Requiere .env completo (ver .env.example).
#
# Uso:  ./scripts/run_local.sh
# Luego, con la URL https://xxxx.trycloudflare.com que imprime cloudflared:
#       uv run python scripts/set_webhook.py --url https://xxxx.trycloudflare.com/webhook
set -euo pipefail
cd "$(dirname "$0")/.."

if [[ ! -f .env ]]; then
  echo "Falta .env (copiá .env.example y completalo)." >&2
  exit 1
fi
command -v cloudflared >/dev/null || { echo "Falta cloudflared: brew install cloudflared" >&2; exit 1; }

PORT="${PORT:-8080}"
export LOG_FORMAT="${LOG_FORMAT:-console}"

uv run uvicorn gastos_bot.main:app --factory --host 127.0.0.1 --port "$PORT" --reload &
UVICORN_PID=$!
trap 'kill "$UVICORN_PID" 2>/dev/null || true' EXIT

echo
echo ">>> Servicio en http://127.0.0.1:$PORT  (health: /health)"
echo ">>> Abriendo túnel; copiá la URL *.trycloudflare.com y registrá el webhook con scripts/set_webhook.py"
echo
cloudflared tunnel --url "http://127.0.0.1:$PORT" --no-autoupdate
