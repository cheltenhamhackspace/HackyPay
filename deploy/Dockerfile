# HackyPay backend + kiosk frontend, single container.
# Multi-stage: deps installed with uv from the lockfile, then a slim runtime.
# Venv path (/app/.venv) must match in BOTH stages — console-script shebangs embed it.
# Build from repo root:  docker build -f deploy/Dockerfile -t hackypay:latest .

FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder

ENV UV_COMPILE_BYTECODE=0 \
    UV_LINK_MODE=copy

WORKDIR /app

# Install dependencies first (cached layer) — requires uv.lock
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev

# Install the project itself
COPY backend/ ./
RUN uv sync --frozen --no-dev

# ------------------------------------------------------------------

FROM python:3.12-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app \
    PATH="/app/.venv/bin:$PATH" \
    HOST=0.0.0.0 \
    PORT=8000 \
    FRONTEND_DIR=/app/frontend \
    ITEMS_CONFIG_PATH=/app/items_config.json

# Non-root user
RUN groupadd --gid 1000 hackypay && \
    useradd --uid 1000 --gid hackypay --create-home hackypay

WORKDIR /app

COPY --from=builder --chown=hackypay:hackypay /app/.venv /app/.venv
COPY --chown=hackypay:hackypay backend/app /app/app
COPY --chown=hackypay:hackypay backend/items_config.json /app/items_config.json
COPY --chown=hackypay:hackypay frontend /app/frontend

USER hackypay

EXPOSE 8000

# Requires SUMUP_* env at runtime (from Secret) — config validators enforce format.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-proxy-headers"]