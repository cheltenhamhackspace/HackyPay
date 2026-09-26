# HackyPay Security Review — September 2026

**Verdict: PASS WITH FINDINGS — all reproduced findings fixed, regression-tested (53 tests green).**

## Scope

- Target: HackyPay self-checkout kiosk (FastAPI backend + SumUp reader integration + vanilla JS frontend), full working-tree audit.
- Method: 3 independent vulnerability hunters → 2 PoC engineers (independent prove/falsify) → cross-check. All PoCs executed offline against local mocks in isolated copies; **no contact with the real SumUp API**.
- Context: payment kiosk on a hackspace LAN; frontend served by the backend itself (same-origin).

## Findings (all reproduced by ≥2 independent engineers, all fixed)

| Severity | Finding | CWE | Fix | Regression test |
|---|---|---|---|---|
| HIGH | `/api/checkout` unauthenticated; charged amount was the client-supplied `total_amount` up to £9999.99; `items_config.json` max/min prices (£49.99/£0.01) enforced only in the frontend; `validate_item_type()` existed but was never called | CWE-306, CWE-602 | Server-side enforcement in checkout: per-item price cap, total cap, minimum, and item-type membership against `items_config.json` | `TestCheckoutPriceEnforcement` (6 tests) |
| MEDIUM | `/api/config/reload` trusted `request.client.host == 127.0.0.1` as authorization — behind the README's own nginx topology every client appears loopback; uvicorn's default proxy-header trust honored attacker-supplied `X-Forwarded-For` (proven end-to-end: `XFF: 127.0.0.1` → reload 200; 130 rotating-XFF requests → 0×429 vs control 429 at #98) | CWE-290, CWE-346 | Optional `ADMIN_TOKEN` setting + timing-safe `X-Admin-Token` check; loopback-only fallback when no token; `proxy_headers=False` in both `__main__` and container CMD | `TestReloadAuth` (5 tests) |
| MEDIUM | Stored XSS: item names/icons/descriptions from `/api/item-types` rendered via `innerHTML` (3 sinks), no CSP; reachable via local config tamper or plain-HTTP LAN MITM | CWE-79, CWE-693 | Frontend rewritten with DOM APIs (0 `innerHTML` sinks); strict CSP `default-src 'self'` on all responses | `TestHeadersAndDocs` + frontend escaping |
| LOW–MED | Unbounded memory/payloads: rate-limit keys never evicted (memory DoS), unbounded `item_type` strings built multi-MB SumUp descriptions (1MB item_type → 977 KiB description), `max_request_size` setting never enforced | CWE-770, CWE-400 | Key eviction cap (`rate_limit_max_keys`), `item_type` max_length=100, generated description truncated to 500, Content-Length check → 413 | `TestRateLimiterBounds`, `TestDescriptionTruncation` |
| LOW | Transaction status dict branch returned `found=True` for whatever dict SumUp returned without verifying the requested ID. (PoC corrected the hunters: per SumUp's OpenAPI, this branch is the *documented normal* response shape — not dead code; exploitation requires SumUp misbehavior on a TLS leg, so LOW) | CWE-345 | Dict branch now verifies `client_transaction_id` matches the request | `TestTransactionVerification` (3 tests) |
| LOW | Log injection: `%0A` in the transaction-id path param reached logs raw; log masking bypassable via lazy `%`-args (secret rendered after sanitization) and dead `SecureFormatter`; merchant code unmasked in exception URLs; pydantic v2 echoed secret `input_value` to stderr on startup validation errors | CWE-117, CWE-532 | Transaction-id format validation (400 on control chars); `SecureFormatter` installed on the root handler (masks rendered output incl. `%`-args); merchant-token pattern extended; startup `ValidationError` re-raised with field names only | `TestLogMasking`, `test_tx_id_*`, `test_startup_config_error_does_not_echo_secret` |
| LOW | Read-only FS (K8s ConfigMap mount) crashed the whole app at import: `PermissionError` raised inside `except FileNotFoundError` escapes the sibling handler; module-level `ItemsService()` instantiation | CWE-755 | Default config built in memory first; file write is best-effort (`OSError` → warning) | `TestReadOnlyConfigFallback` |
| INFO–LOW | CORS `allow_credentials=True` + operator-set `*` echoed arbitrary origins (Starlette source confirmed); 429 responses carried no security headers; `/docs`/`/redoc` exposed on LAN; DEBUG check bypassed via lowercase env-var *name* (pydantic case-insensitive, `os.getenv('DEBUG')` case-sensitive); `total_amount` accepted 3dp values (sub-penny truncation); `serve_index` locale-dependent `read_text()` | various | `allow_credentials=False` (no cookies exist); headers on 429/413 paths; docs disabled unless `DEBUG`; DEBUG check via settings (case-insensitive); 2dp validator on `total_amount`; `read_text(encoding="utf-8")` | `TestHeadersAndDocs`, `TestModelHardening` |

## Also fixed during the audit

- Removed `python-multipart` dependency (declared, never used — attack surface with known CVE history).
- Dependency pins: `uv.lock` generated and committed (was gitignored + missing → non-reproducible builds on a payment kiosk).
- Duplicate `request_counts` declaration removed; dead code (`get_masked_token` etc.) trimmed or repurposed.

## Accepted risks (documented, not bugs)

- **Checkout is intentionally unauthenticated** (self-service kiosk for hackspace members). With server-side enforcement the worst outcome per request is a £49.99 reader prompt. Documented as accepted; revisit if the kiosk is ever exposed beyond the LAN.
- Payment audit trail is SumUp's dashboard + stdout logs; no local persistence. Acceptable for the volume; revisit for reconciliation needs.

## Residual risk

- No HTTPS on the LAN (API + UI are plain HTTP). Reader/PAN data never touches the backend; SumUp traffic is TLS. A LAN attacker can observe/sniff kiosk traffic — mitigate with Wi-Fi isolation or a reverse proxy with TLS if the threat model changes.
- Sync `requests` calls block the event loop up to 30s per SumUp call (single-replica deployment). Availability risk under degraded SumUp connectivity, not exploitable beyond nuisance.
- In-browser XSS execution was demonstrated via parser emulation, not a real Chromium run (no node/browser in the audit environment) — the fix (DOM APIs + CSP) covers the sink regardless.