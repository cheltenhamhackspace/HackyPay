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
compose.yaml       Single-container deployment (Docker Compose) + .env.example
CONFIGURATION.md   How to configure item types and limits
```

## Backend Setup

Prerequisites: Python 3.13+, [uv](https://docs.astral.sh/uv/), a SumUp merchant account with an API key and card reader.

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
- For kiosk boot, point Chromium at the backend address. Recommended flags for the Pi under Wayland (GPU rasterisation, no overscroll/history gestures, no crash bubbles, no GNOME keyring prompt):
  ```bash
  chromium --ozone-platform=wayland --password-store=basic --kiosk --noerrdialogs \
    --disable-session-crashed-bubble --enable-gpu-rasterization \
    --ignore-gpu-blocklist --overscroll-history-navigation=0 \
    --disable-features=Translate,MediaRouter \
    http://<backend-ip>
  ```
- Touch behaviour is tuned in the app: vertical-pan-only scroll containers, overscroll containment (no pull-to-refresh / page drift), long-press context menus suppressed, no text selection or tap flash.

### Raspberry Pi setup (automated)

`deploy/pi/setup-kiosk.sh` turns a Raspberry Pi OS (Bookworm+) image into a HackyPay kiosk — autologins the `kiosk` user into the labwc Wayland session (via lightdm on desktop installs, or getty autologin on Lite), launches Chromium kiosk pointing at the backend (respawned on crash via `lwrespawn`), and rotates the output via `wlr-randr` only if the panel comes up landscape (the official 7" panel is native portrait; touch mapping follows the output transform automatically under Wayland). The Pi is a thin client — no code checkout needed.

> Note: current Raspberry Pi OS uses Wayland (labwc/wlroots) by default. The previous X11 approach (xinit + X on tty1 from systemd) no longer works there — Xorg cannot take the virtual console from a systemd unit, and `unclutter` is X-only.

```bash
scp deploy/pi/setup-kiosk.sh pi@<pi-address>:
ssh pi@<pi-address>
sudo ./setup-kiosk.sh http://<backend-ip>
sudo reboot
```

- Re-run with a new URL any time (safe/idempotent): `sudo ./setup-kiosk.sh http://<new-url>`
- If the UI appears upside down: `KIOSK_ROTATE=right sudo ./setup-kiosk.sh <url>`
- Logs: `journalctl -u lightdm -f` (desktop installs) or `journalctl _COMM=labwc -f`

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

## Deploying with Docker Compose

The simplest way to self-host HackyPay — one container, no Kubernetes:

```bash
cp .env.example .env    # then edit .env with your SumUp credentials
docker compose up --build -d
```

The kiosk UI and API are served at `http://<host>:8000` — point the
Raspberry Pi kiosk at that URL (see [Kiosk](#kiosk-raspberry-pi-touch-display-2)).
`docker compose ps` shows health; the container restarts on failure and
after reboots (`unless-stopped`).

To customise the kiosk items (names, prices, currency), copy
`backend/items_config.json` to the repo root, edit it, and uncomment the
`volumes` block in `compose.yaml` — create the file *before* uncommenting,
since Docker otherwise auto-creates a directory in its place. Changes apply
on container restart, or hot-reload via `POST /api/config/reload` with your
`ADMIN_TOKEN` as the `X-API-Key` header.

To run a published image instead of building locally, remove the `build`
block in `compose.yaml` and set `image:` to
`ghcr.io/cheltenhamhackspace/hackypay:latest` (newest release) or a pinned
`:X.Y.Z`. Running from source needs no registry at all — updates are just
`git pull && docker compose up --build -d`; CI's automatic image-tag bump
applies only to the Kubernetes manifest, because that is the one place a
deployment references registry tags.

The Compose service uses the same hardening as the Kubernetes deployment:
non-root (uid 65532), read-only root filesystem, no capabilities, and no
privilege escalation.

## Deploying on Kubernetes

Images are built automatically by GitHub CI (`.github/workflows/container-image.yml`) and published to GHCR as multi-arch (amd64 + arm64):

- pushes to `main` → `ghcr.io/cheltenhamhackspace/hackypay:main` (+ `:sha-<sha>`)
- `v*` tags → `ghcr.io/cheltenhamhackspace/hackypay:<version>` (+ `:latest`)

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
4. CI bumps the image tag in `deploy/k8s/deployment.yaml` automatically (a `github-actions[bot]` commit to main, marked `[skip ci]`) once the multi-arch push succeeds. `git pull`, then apply the manifest to roll out.
5. Optionally add release notes under GitHub → Releases (the tag already exists there).

Rolling back = pointing the Deployment back at the previous version tag and re-applying.

## Security

Key points:

- SumUp credentials live only in backend env/Secret.
- Price limits from `items_config.json` are enforced server-side at checkout.
- Strict CSP, security headers on all responses (including 429/413).
- Config reload requires an admin token when configured; loopback-only otherwise.
- Dependencies locked with `uv.lock`.

### Supply chain security

- **Actions pinned by commit SHA** — every GitHub Action in `.github/workflows/` is pinned to a full commit SHA (mutable tags like `@v4` are an injection vector). Dependabot keeps the pins current; the version is noted in a trailing comment.
- **Base images pinned by digest** — both stages in `deploy/Dockerfile` are pinned to multi-arch image digests: the builder is `ghcr.io/astral-sh/uv:python3.13-trixie-slim`, the runtime is Google's [`gcr.io/distroless/python3-debian13:nonroot`](https://github.com/GoogleContainerTools/distroless) — no shell, no package manager, no pip, with ca-certificates and tzdata included. Neither image can be silently re-pointed upstream. Update with `docker buildx imagetools inspect <image:tag>`, bumping both digests together (the copied venv is tied to the interpreter minor version).
- **Distroless runtime, least-privilege pod** — the pod runs as uid 65532 (the distroless `nonroot` user, present in `/etc/passwd`) with `readOnlyRootFilesystem: true`, all capabilities dropped, `allowPrivilegeEscalation: false`, and seccomp `RuntimeDefault` (`deploy/k8s/deployment.yaml`). Interactive debugging uses the distroless `debug-nonroot` tag, not a runtime shell.
- **Lockfile-only installs** — the image is built with `uv sync --frozen`, and CI audits the runtime closure of `uv.lock` with [pip-audit](https://pypi.org/project/pip-audit/) on every push/PR (`audit` job; fails on any known vulnerability).
- **Image attestations** — pushed images carry SLSA provenance and an in-toto SBOM attestation (inspect with `docker buildx imagetools inspect ghcr.io/cheltenhamhackspace/hackypay:<tag>`).
- **Least-privilege CI** — the workflow defaults to `contents: read`; only the build job gets `packages: write`, and checkout runs with `persist-credentials: false`.
- **Automated updates** — [Dependabot](.github/dependabot.yml) opens weekly grouped PRs for GitHub Actions and Python dependencies (reads `uv.lock`).

## AI-assisted development

This project was built with heavy use of LLM-based coding assistants: essentially all of the code was drafted, refactored, and reviewed in collaboration with AI tools rather than written from scratch. Development ran on GLM 5.3 Flash (Z.ai) with max thinking enabled, orchestrated via the OhMyOpenCode agent harness. Human reviewers went through every change, and a separate manual security review was performed on the final result.

If you fork or reuse this code, apply the same scrutiny you would to any AI-generated codebase.

## License

Proprietary software for Cheltenham Hackspace.