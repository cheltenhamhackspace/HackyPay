# HackyPay™ Self Checkout System

A web-based self-checkout system for Cheltenham Hackspace, using the SumUp reader API. Touch kiosk UI for the Raspberry Pi Touch Display 2 (720×1280 portrait), with SumUp API credentials kept backend-side only.

## Features

- 🔒 Credentials never exposed to the frontend; server-side price-limit enforcement
- 📱 Kiosk UI targeted at the 7" Pi touch display (720×1280), fully offline (self-hosted brand font, no CDNs)
- 🛒 Shopping cart with on-screen keypad
- 💳 SumUp card reader integration with reader-state polling
- 🎨 Cheltenham Hackspace branding (Hack Yellow `#FED202` / Ink / Paper)
- 🔧 FastAPI + Pydantic v2, managed with [uv](https://docs.astral.sh/uv/)

## Layout

```
backend/           FastAPI app (package: backend/app), tests, items config
frontend/          Static kiosk UI (served by the backend, same origin)
deploy/            Dockerfile + Kubernetes manifests (deploy/k8s/)
SECURITY-REVIEW.md Security audit report (September 2026)
CONFIGURATION.md   How to configure item types and limits
```

## Backend Setup

Prerequisites: Python 3.10+, [uv](https://docs.astral.sh/uv/), a SumUp merchant account with an API key and card reader.

```bash
cd backend
uv sync                      # creates .venv from uv.lock
cp .env.example .env         # then edit with your real SumUp credentials
uv run pytest                # run the test suite
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
```

The backend serves the kiosk UI at `http://127.0.0.1:8000/` — no separate frontend server needed.

## Kiosk (Raspberry Pi Touch Display 2)

- Target resolution is fixed 720×1280 portrait; the UI is portrait-first CSS.
- Fully offline: the Dunbar Low brand font is self-hosted (`frontend/assets/fonts/`) and there are no CDN requests. If the brand font fails to load, a dismissible warning banner appears under the header.
- For kiosk boot, point Chromium at the backend address, e.g. `chromium-browser --kiosk http://127.0.0.1:8000`.

## API Endpoints

| Method | Path | Notes |
|---|---|---|
| GET | `/api/health` | Health check (used by K8s probes) |
| GET | `/api/item-types` | Enabled item types + price settings |
| GET | `/api/reader/status` | SumUp reader status |
| GET | `/api/transaction/{id}/status` | Poll transaction status by `client_transaction_id` |
| POST | `/api/cart/validate` | Validate cart contents |
| POST | `/api/checkout` | Trigger the reader charge (validated against `items_config.json` limits server-side) |
| POST | `/api/config/reload` | Admin only: `X-Admin-Token` header when `ADMIN_TOKEN` is set, loopback-only otherwise |

FastAPI docs (`/docs`, `/redoc`) are available only when `DEBUG=true`.

## Configuration

- **Environment**: `backend/.env` — see `.env.example`. `ADMIN_TOKEN` (optional) protects the config-reload endpoint.
- **Item types & price limits**: `backend/items_config.json` — see `CONFIGURATION.md`. In Kubernetes the file is mounted from a ConfigMap.

## Deploying on Kubernetes

Images are built automatically by GitHub CI (`.github/workflows/container-image.yml`) and published to GHCR as multi-arch (amd64 + arm64):

- pushes to `main` → `ghcr.io/cheltenhamhackspace/hackypay:main` (+ `:sha-<sha>`)
- `v*` tags → `ghcr.io/cheltenhamhackspace/hackypay:<version>`

> GHCR packages are **private by default** — either flip the package to public in GitHub → Packages settings, or create an `imagePullSecret` (the Deployment has a commented `imagePullSecrets` block ready for it).

The manifests in `deploy/k8s/` are pinned to the current release image (`:1.0.0` — bumped with each release, see [Releasing](#releasing)). Plain manifests: Namespace, Secret (SumUp credentials), ConfigMap (items config + CORS), Deployment (1 replica — the rate limiter and the single physical reader are singletons; probes on `/api/health`; non-root, read-only root FS), Service (ClusterIP, with a NodePort variant commented in for LAN kiosk access).

```bash
kubectl apply -f deploy/k8s/namespace.yaml
kubectl apply -f deploy/k8s/secret.yaml     # or create the real secret via kubectl create secret
kubectl apply -f deploy/k8s/configmap.yaml
kubectl apply -f deploy/k8s/deployment.yaml
kubectl apply -f deploy/k8s/service.yaml
```

Building locally instead (e.g. for direct import into k3s/microk8s without a registry):

```bash
docker build -f deploy/Dockerfile -t hackypay:latest .            # native arch
docker buildx build --platform linux/amd64,linux/arm64 \
  -f deploy/Dockerfile -t hackypay:latest --load .                # multi-arch
```

The backend calls `api.sumup.com:443` — ensure egress is allowed if you run default-deny NetworkPolicies.

## Releasing

1. Bump `version` in `backend/pyproject.toml`.
2. Commit the bump, then tag (annotated tag, `v` prefix, matching the pyproject version):
   ```bash
   git tag -a vX.Y.Z -m "Release vX.Y.Z: one-line summary"
   git push origin vX.Y.Z
   ```
3. CI builds and publishes multi-arch images:
   - `ghcr.io/cheltenhamhackspace/hackypay:X.Y.Z`
   - `ghcr.io/cheltenhamhackspace/hackypay:X.Y`
4. Update the image tag in `deploy/k8s/deployment.yaml` to the new version and apply.
5. Optionally add release notes under GitHub → Releases (the tag already exists there).

Rolling back = pointing the Deployment back at the previous version tag and re-applying.

## Security

See `SECURITY-REVIEW.md` for the full audit (findings, fixes, accepted risks). Key points:

- SumUp credentials live only in backend env/Secret.
- Price limits from `items_config.json` are enforced server-side at checkout.
- Strict CSP, security headers on all responses (including 429/413).
- Config reload requires an admin token when configured; loopback-only otherwise.
- Dependencies locked with `uv.lock`.

## License

Proprietary software for Cheltenham Hackspace.