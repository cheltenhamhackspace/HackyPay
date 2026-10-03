# HackyPay backend + kiosk frontend, single container.
# Multi-stage: dependencies installed with uv from the lockfile, then a
# Google distroless runtime (no shell, no package manager, no pip) on
# Debian 13 (trixie).
# Venv path (/app/.venv) must match in BOTH stages — console-script shebangs embed it.
# Build from repo root:  docker build -f deploy/Dockerfile -t hackypay:latest .

# Base images are pinned by digest (multi-arch index, works for amd64 + arm64).
# To update: docker buildx imagetools inspect <image:tag> and copy the Digest.
#
# Builder: Python 3.13 on Debian 13 (trixie) + uv. NOTE: both stages must move
# in lockstep — the copied venv is tied to the interpreter minor version.
FROM ghcr.io/astral-sh/uv:python3.13-trixie-slim@sha256:a6aeb5c166af9f765f9c68e585b5a5148c28f3b8a362f90151cecea88b21a3e2 AS builder

ENV UV_COMPILE_BYTECODE=0 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0 \
    UV_PYTHON=/usr/bin/python

# The distroless runtime keeps its interpreter at /usr/bin/python, while the
# official builder images put Python at /usr/local/bin. Symlink the runtime
# path into the builder BEFORE uv creates the venv, so .venv/bin/python and
# pyvenv.cfg (home = /usr/bin) resolve inside the distroless image.
# https://github.com/GoogleContainerTools/distroless/blob/main/python3/README.md
RUN ln -s /usr/local/bin/python /usr/bin/python

WORKDIR /app

# Install dependencies first (cached layer) — requires uv.lock.
# The project itself is NOT installed into the venv: app code is imported
# from /app/app via PYTHONPATH in the runtime stage.
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev

# ------------------------------------------------------------------

# Runtime: distroless python3-debian13:nonroot — Python 3.13, glibc,
# ca-certificates + tzdata included, runs as uid 65532, no shell/package
# manager. Debug variant (busybox shell) for troubleshooting:
# gcr.io/distroless/python3-debian13:debug-nonroot
FROM gcr.io/distroless/python3-debian13:nonroot@sha256:774595d652a294b54c9bd575b2d9fdd1a4b47547dc17b8bfa4c0e953c64855b3 AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app \
    PATH="/app/.venv/bin:$PATH" \
    HOST=0.0.0.0 \
    PORT=8000 \
    FRONTEND_DIR=/app/frontend \
    ITEMS_CONFIG_PATH=/app/items_config.json

WORKDIR /app

COPY --from=builder --chown=65532:65532 /app/.venv /app/.venv
COPY --chown=65532:65532 backend/app /app/app
COPY --chown=65532:65532 backend/items_config.json /app/items_config.json
COPY --chown=65532:65532 frontend /app/frontend

# Matches the image's built-in `nonroot` user (uid 65532, in /etc/passwd).
USER 65532:65532

EXPOSE 8000

# Requires SUMUP_* env at runtime (from Secret) — config validators enforce format.
ENTRYPOINT ["/app/.venv/bin/uvicorn"]
CMD ["app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-proxy-headers"]
