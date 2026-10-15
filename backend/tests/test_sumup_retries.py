"""Retry behaviour for transient SumUp/reader failures (reader wake-from-sleep etc.)."""
import pytest
import requests

from app.config import get_settings
from app.models import CheckoutRequest
from app.services.sumup_service import SumUpService


class FakeResponse:
    def __init__(self, status_code, payload=None):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}

    def json(self):
        return self._payload


class ScriptedSession:
    """Stand-in for requests.Session returning a scripted sequence of
    responses and exceptions, counting the HTTP calls it served."""

    def __init__(self, script):
        self._script = list(script)
        self.calls = 0

    def _next(self):
        self.calls += 1
        step = self._script.pop(0)
        if isinstance(step, Exception):
            raise step
        return step

    def post(self, *args, **kwargs):
        return self._next()

    def get(self, *args, **kwargs):
        return self._next()


@pytest.fixture
def service(monkeypatch):
    # No real sleeping between attempts
    monkeypatch.setattr(get_settings(), "sumup_retry_delay", 0)
    return SumUpService()


def _checkout_request():
    return CheckoutRequest(
        items=[{"item_type": "Food & Drink", "price": "3.50", "quantity": 1}],
        total_amount="3.50",
    )


class TestCheckoutRetries:
    def test_offline_reader_422_then_success(self, service):
        service.session = ScriptedSession([
            FakeResponse(422, {"detail": "Reader is offline"}),
            FakeResponse(201, {"data": {"client_transaction_id": "tx-123"}}),
        ])
        result = service.process_payment(_checkout_request())
        assert result.success is True
        assert service.session.calls == 2

    def test_offline_reader_retries_exhausted_then_success(self, monkeypatch, service):
        monkeypatch.setattr(get_settings(), "sumup_max_retries", 2)
        service.session = ScriptedSession([
            FakeResponse(422, {"detail": "READER_OFFLINE"}),
            FakeResponse(422, {"detail": "Reader not ready"}),
            FakeResponse(201, {"data": {"client_transaction_id": "tx-123"}}),
        ])
        result = service.process_payment(_checkout_request())
        assert result.success is True
        assert service.session.calls == 3

    def test_offline_reader_422_exhausted_reports_offline(self, monkeypatch, service):
        monkeypatch.setattr(get_settings(), "sumup_max_retries", 1)
        service.session = ScriptedSession([
            FakeResponse(422, {"detail": "Reader is offline"}),
            FakeResponse(422, {"detail": "Reader is offline"}),
        ])
        result = service.process_payment(_checkout_request())
        assert result.success is False
        assert result.status_code == 422
        assert "offline" in result.message.lower()
        assert service.session.calls == 2

    def test_non_offline_422_never_retried(self, service):
        service.session = ScriptedSession([
            FakeResponse(422, {"detail": "amount below minimum"}),
        ])
        result = service.process_payment(_checkout_request())
        assert result.success is False
        assert service.session.calls == 1

    def test_5xx_retried_then_success(self, service):
        service.session = ScriptedSession([
            FakeResponse(503, {}),
            FakeResponse(201, {"data": {"client_transaction_id": "tx-123"}}),
        ])
        result = service.process_payment(_checkout_request())
        assert result.success is True
        assert service.session.calls == 2

    def test_409_reader_busy_never_retried(self, service):
        service.session = ScriptedSession([
            FakeResponse(409, {}),
        ])
        result = service.process_payment(_checkout_request())
        assert result.success is False
        assert service.session.calls == 1

    def test_connection_errors_exhausted_returns_503(self, monkeypatch, service):
        monkeypatch.setattr(get_settings(), "sumup_max_retries", 2)
        service.session = ScriptedSession([
            requests.exceptions.ConnectionError("reset"),
            requests.exceptions.ConnectionError("reset"),
            requests.exceptions.ConnectionError("reset"),
        ])
        result = service.process_payment(_checkout_request())
        assert result.success is False
        assert result.status_code == 503
        assert service.session.calls == 3

    def test_429_retried_then_success(self, service):
        service.session = ScriptedSession([
            FakeResponse(429, {}),
            FakeResponse(201, {"data": {"client_transaction_id": "tx-123"}}),
        ])
        result = service.process_payment(_checkout_request())
        assert result.success is True
        assert service.session.calls == 2


class TestReaderStatusRetries:
    def test_connection_error_then_success(self, service):
        service.session = ScriptedSession([
            requests.exceptions.ConnectionError("reset"),
            FakeResponse(200, {"data": {"status": "ONLINE", "state": "IDLE"}}),
        ])
        status = service.check_reader_status()
        assert status["online"] is True
        assert service.session.calls == 2

    def test_no_retries_left_reports_unknown(self, monkeypatch, service):
        monkeypatch.setattr(get_settings(), "sumup_max_retries", 1)
        service.session = ScriptedSession([
            requests.exceptions.Timeout("timed out"),
            requests.exceptions.Timeout("timed out"),
        ])
        status = service.check_reader_status()
        assert status["online"] is False
        assert status["state"] == "UNKNOWN"
        assert service.session.calls == 2
