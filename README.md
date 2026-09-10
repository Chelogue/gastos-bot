# gastos-bot

Bot de Telegram para que dos personas registren gastos con una foto, los archiven en Google Drive, los organicen en Google Sheets y reciban un reporte quincenal con la regla 50/30/20.

- **Producto:** `docs/PRD.md` (fuente de verdad)
- **Código y prácticas:** `docs/estructura.md`
- **Reglas para Claude Code:** `CLAUDE.md`
- **Decisiones:** `docs/decisions/`

## Correr en local

```bash
uv sync
cp .env.example .env   # completar valores
uv run pytest
./scripts/run_local.sh # requiere túnel (ngrok / cloudflared) para el webhook de Telegram
```

## Deploy

Push a `main` → GitHub Actions construye la imagen y despliega a Cloud Run (ver `.github/workflows/deploy.yml` cuando exista). Los secretos viven en Secret Manager; ninguno en el repo.

## Estado

Ver la sección "Estado" en `CLAUDE.md`.
