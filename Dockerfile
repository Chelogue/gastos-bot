# syntax=docker/dockerfile:1.7
# Etapa 1: resolver e instalar dependencias con uv (lockfile congelado, sin dev).
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project --extra gemini --extra anthropic
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --extra gemini --extra anthropic

# Etapa 2: imagen final mínima, usuario no-root, escucha en $PORT (Cloud Run lo inyecta).
FROM python:3.12-slim-bookworm
RUN groupadd --system app && useradd --system --gid app --home-dir /app app
WORKDIR /app
COPY --from=builder --chown=app:app /app /app
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8080
USER app
EXPOSE 8080
CMD ["sh", "-c", "exec uvicorn gastos_bot.main:app --factory --host 0.0.0.0 --port ${PORT}"]
