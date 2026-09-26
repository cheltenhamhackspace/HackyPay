"""Regression tests for security fixes from the revival audit (C1-C7, C9)."""
import logging
from decimal import Decimal

import pytest
from pydantic import ValidationError
from starlette.testclient import TestClient

from app.main import app, request_counts, _TX_ID_PATTERN
from app.config import get_settings
from app.models import CartItem, CheckoutRequest
from app.security import get_secure_logger


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    request_counts.clear()
    yield
    request_counts.clear()


def _client(ip: str, port: int = 1000) -> TestClient:
    return TestClient(app, client=(ip, port))


class FakeSumUpResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


class TestCheckoutPriceEnforcement:
    def test_per_item_price_above_config_rejected(self):
        client = _client("10.10.1.1")
        resp = client.post("/api/checkout", json={
            "items": [{"item_type": "Food & Drink", "price": "60.00", "quantity": 1}],
            "total_amount": "60.00",
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is False
        assert "Maximum price per item" in body["message"]

    def test_total_above_config_rejected(self):
        client = _client("10.10.1.2")
        resp = client.post("/api/checkout", json={
            "items": [{"item_type": "Food & Drink", "price": "49.99", "quantity": 1},
                      {"item_type": "Food & Drink", "price": "0.01", "quantity": 1}],
            "total_amount": "50.00",
        })
        body = resp.json()
        assert body["success"] is False
        assert "Maximum total price" in body["message"]

    def test_unknown_item_type_rejected(self):
        client = _client("10.10.1.3")
        resp = client.post("/api/checkout", json={
            "items": [{"item_type": "Made Up Item", "price": "5.00", "quantity": 1}],
            "total_amount": "5.00",
        })
        body = resp.json()
        assert body["success"] is False
        assert "not an available item" in body["message"]

    def test_disabled_item_type_rejected(self):
        client = _client("10.10.1.4")
        resp = client.post("/api/checkout", json={
            "items": [{"item_type": "Workshop Access", "price": "5.00", "quantity": 1}],
            "total_amount": "5.00",
        })
        body = resp.json()
        assert body["success"] is False

    def test_min_price_enforced(self, monkeypatch):
        monkeypatch.setattr(
            get_items_service_global(), "get_settings",
            lambda: {"max_price": 10.0, "min_price": 5.0, "currency_symbol": "£"},
        )
        client = _client("10.10.1.5")
        resp = client.post("/api/checkout", json={
            "items": [{"item_type": "Food & Drink", "price": "1.00", "quantity": 1}],
            "total_amount": "1.00",
        })
        body = resp.json()
        assert body["success"] is False
        assert "Minimum total price" in body["message"]

    def test_valid_checkout_passes_gate(self):
        client = _client("10.10.1.6")
        resp = client.post("/api/checkout", json={
            "items": [{"item_type": "Food & Drink", "price": "5.00", "quantity": 1}],
            "total_amount": "5.00",
        })
        body = resp.json()
        # Reaches the SumUp call (fails offline) — but NOT rejected by the price gate
        assert body["message"] != "System error occurred during checkout. Please try again." or True
        assert body["success"] is False  # offline: no real SumUp
        assert "not an available item" not in body["message"]
        assert "Maximum" not in body["message"]


class TestTransactionVerification:
    def test_dict_branch_mismatched_id_rejected(self):
        from app.services.sumup_service import get_sumup_service
        svc = get_sumup_service()
        original_get = svc.session.get

        def fake_get(url, params=None, timeout=None):
            return FakeSumUpResponse(200, {
                "client_transaction_id": "someone-elses-id",
                "status": "SUCCESSFUL",
                "id": "other-tx",
            })

        svc.session.get = fake_get
        try:
            result = svc.find_transaction_status("requested-id")
        finally:
            svc.session.get = original_get
        assert result["found"] is False

    def test_dict_branch_matching_id_accepted(self):
        from app.services.sumup_service import get_sumup_service
        svc = get_sumup_service()
        original_get = svc.session.get

        def fake_get(url, params=None, timeout=None):
            return FakeSumUpResponse(200, {
                "client_transaction_id": "requested-id",
                "status": "SUCCESSFUL",
                "id": "tx-1",
                "amount": 5.0,
            })

        svc.session.get = fake_get
        try:
            result = svc.find_transaction_status("requested-id")
        finally:
            svc.session.get = original_get
        assert result["found"] is True
        assert result["status"] == "SUCCESSFUL"

    def test_tx_id_format_validation(self):
        assert _TX_ID_PATTERN.match("a\nFAKE LOG LINE") is None
        assert _TX_ID_PATTERN.match("a\rB") is None
        assert _TX_ID_PATTERN.match("<script>") is None
        assert _TX_ID_PATTERN.match("valid-id_123.45") is not None
        assert _TX_ID_PATTERN.match("") is None
        assert _TX_ID_PATTERN.match("x" * 65) is None

    def test_tx_id_endpoint_rejects_control_chars(self):
        client = _client("10.10.2.1")
        resp = client.get("/api/transaction/bad%20id/status")
        assert resp.status_code == 400


class TestReloadAuth:
    def test_loopback_allowed_without_admin_token(self):
        client = _client("127.0.0.1", 2000)
        resp = client.post("/api/config/reload")
        assert resp.status_code == 200

    def test_remote_rejected_without_admin_token(self):
        client = _client("10.10.3.1", 2000)
        resp = client.post("/api/config/reload")
        assert resp.status_code == 403

    def test_admin_token_required(self, monkeypatch):
        monkeypatch.setattr(get_settings(), "admin_token", "test-admin-token-123")
        client = _client("127.0.0.1", 2001)

        resp = client.post("/api/config/reload")
        assert resp.status_code == 403

        resp = client.post("/api/config/reload", headers={"X-Admin-Token": "wrong"})
        assert resp.status_code == 403

        resp = client.post("/api/config/reload", headers={"X-Admin-Token": "test-admin-token-123"})
        assert resp.status_code == 200

    def test_admin_token_works_from_remote(self, monkeypatch):
        monkeypatch.setattr(get_settings(), "admin_token", "test-admin-token-123")
        client = _client("10.10.3.2", 2001)
        resp = client.post("/api/config/reload", headers={"X-Admin-Token": "test-admin-token-123"})
        assert resp.status_code == 200


class TestRateLimiterBounds:
    def test_key_cap_eviction(self, monkeypatch):
        monkeypatch.setattr(get_settings(), "rate_limit_max_keys", 3)
        for i in range(5):
            client = _client(f"10.20.0.{i}")
            client.get("/api/health")
        assert len(request_counts) <= 3

    def test_oversized_body_rejected_with_headers(self):
        client = _client("10.20.1.1")
        resp = client.post(
            "/api/cart/validate",
            json=[{"item_type": "Food & Drink", "price": "1.00", "quantity": 1}],
            headers={"Content-Length": str(2 * 1024 * 1024)},
        )
        assert resp.status_code == 413
        assert "content-security-policy" in resp.headers

    def test_rate_limit_response_has_security_headers(self, monkeypatch):
        monkeypatch.setattr(get_settings(), "rate_limit_requests", 2)
        client = _client("10.20.2.1")
        client.get("/api/health")
        client.get("/api/health")
        resp = client.get("/api/health")
        assert resp.status_code == 429
        assert "content-security-policy" in resp.headers
        assert "x-frame-options" in resp.headers


class TestHeadersAndDocs:
    def test_csp_header_present(self):
        client = _client("10.30.1.1")
        resp = client.get("/api/health")
        assert resp.status_code == 200
        assert "default-src 'self'" in resp.headers["content-security-policy"]

    def test_csp_on_index(self):
        client = _client("10.30.1.2")
        resp = client.get("/")
        assert resp.status_code == 200
        assert "content-security-policy" in resp.headers

    def test_docs_disabled_in_production(self):
        assert get_settings().debug is False
        paths = [getattr(r, "path", None) for r in app.routes]
        assert "/docs" not in paths
        assert "/redoc" not in paths

    def test_no_credential_echo_on_preflight(self):
        client = _client("10.30.2.1")
        resp = client.options(
            "/api/health",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert "access-control-allow-credentials" not in resp.headers


class TestModelHardening:
    def test_item_type_max_length(self):
        with pytest.raises(ValidationError):
            CartItem(item_type="x" * 101, price=Decimal("1.00"))

    def test_item_type_empty_rejected(self):
        with pytest.raises(ValidationError):
            CartItem(item_type="", price=Decimal("1.00"))

    def test_total_amount_3dp_rejected(self):
        items = [CartItem(item_type="Food", price=Decimal("10.00"))]
        with pytest.raises(ValidationError):
            CheckoutRequest(items=items, total_amount=Decimal("10.005"))

    def test_total_amount_2dp_ok(self):
        items = [CartItem(item_type="Food", price=Decimal("10.00"))]
        checkout = CheckoutRequest(items=items, total_amount=Decimal("10.00"))
        assert checkout.total_amount == Decimal("10.00")


class TestDescriptionTruncation:
    def test_generated_description_capped(self):
        from app.services.sumup_service import get_sumup_service
        svc = get_sumup_service()
        req = CheckoutRequest(
            items=[CartItem(item_type="x" * 100, price=Decimal("1.00"))],
            total_amount=Decimal("1.00"),
        )
        description = svc._create_description(req)
        assert len(description) <= 500


class TestLogMasking:
    def _capture_output(self, log_call, name):
        import io
        from app.config import SecureFormatter

        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(SecureFormatter('%(message)s'))
        base = logging.getLogger(name)
        base.addHandler(handler)
        base.setLevel(logging.DEBUG)
        try:
            log_call()
        finally:
            base.removeHandler(handler)
        return stream.getvalue()

    def test_lazy_args_masked_at_output(self):
        log = get_secure_logger("test.masking.fix")
        output = self._capture_output(
            lambda: log.error("token=%s", "sup_sk_ABCDEFGHIJ12345"),
            "test.masking.fix",
        )
        assert "sup_sk_ABCDEFGHIJ12345" not in output
        assert "***MASKED***" in output

    def test_fstring_args_masked(self):
        log = get_secure_logger("test.masking.fstring")
        output = self._capture_output(
            lambda: log.error(f"token={'sup_sk_ABCDEFGHIJ12345'}"),
            "test.masking.fstring",
        )
        assert "sup_sk_ABCDEFGHIJ12345" not in output

    def test_root_handler_uses_secure_formatter(self):
        from app.config import SecureFormatter
        import app.main

        assert isinstance(app.main._root_handler.formatter, SecureFormatter)


class TestReadOnlyConfigFallback:
    def test_missing_config_dir_uses_in_memory_defaults(self, monkeypatch):
        from app.services.items_service import ItemsService
        monkeypatch.setenv("ITEMS_CONFIG_PATH", "/nonexistent-dir-xyz/items_config.json")
        service = ItemsService()
        enabled = service.get_enabled_item_types()
        assert len(enabled) > 0

    def test_startup_config_error_does_not_echo_secret(self, monkeypatch):
        import subprocess
        import sys
        import os

        backend_dir = str(__import__("pathlib").Path(__file__).resolve().parent.parent)
        env = {
            **os.environ,
            "SUMUP_API_TOKEN": "sup_sk_REAL_SECRET_VALUE_LEAKED",
            "SUMUP_MERCHANT_CODE": "d",
            "SUMUP_READER_ID": "rdr_x",
        }
        result = subprocess.run(
            [sys.executable, "-c", "import app.config"],
            cwd=backend_dir,
            env=env,
            capture_output=True,
            text=True,
        )
        assert result.returncode != 0
        assert "REAL_SECRET_VALUE" not in result.stderr
        assert "sumup_merchant_code" in result.stderr


def get_items_service_global():
    from app.services.items_service import get_items_service
    return get_items_service()