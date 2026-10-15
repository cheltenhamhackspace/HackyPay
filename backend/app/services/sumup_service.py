import time
import requests
import logging
from typing import Callable, Dict, Any, Optional
from datetime import datetime

from ..config import get_settings
from ..models import CheckoutRequest, PaymentResponse
from ..security import get_secure_logger, security_filter

logger = get_secure_logger(__name__)


class SumUpService:
    def __init__(self):
        self.settings = get_settings()
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {self.settings.sumup_api_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        })

        if not self.settings.sumup_api_token or not self.settings.sumup_merchant_code:
            logger.error("Missing required SumUp credentials")
            raise ValueError("SumUp service not properly configured")

    def _api_url(self, path: str) -> str:
        return f"{self.settings.sumup_api_base_url}{path}"

    # ----------------------------------------------------------------
    #  Transient-failure retry
    #  When the reader has been asleep, the first request to SumUp
    #  often fails (reader-offline 422, connection reset or 5xx) and
    #  succeeds when repeated seconds later. Retry those cases
    #  automatically with backoff so the kiosk user doesn't have to
    #  tap "Try again". Non-transient errors (validation, declined,
    #  reader busy) are never retried — a retry cannot double-charge
    #  because the reader takes one transaction at a time and a
    #  still-active earlier session answers 409, which we keep.
    # ----------------------------------------------------------------
    _RETRYABLE_STATUS_CODES = frozenset({429, 500, 502, 503, 504})

    @staticmethod
    def _offline_reader_body(response) -> bool:
        """True when a 422 is the transient 'reader asleep/waking' case."""
        try:
            detail = response.json().get("detail", "")
        except Exception:
            return False
        text = detail if isinstance(detail, str) else str(detail)
        text = text.lower()
        return "offline" in text or "not ready" in text

    def _backoff(self, attempt: int) -> None:
        time.sleep(self.settings.sumup_retry_delay * (2 ** attempt))

    def _send_with_retries(
        self,
        send: Callable[[], requests.Response],
        label: str,
        retry_offline_reader: bool,
    ) -> requests.Response:
        """Run a request, retrying transient failures with backoff.

        Retries connection errors/timeouts and 429/5xx always, plus a
        422 whose body says the reader was offline/not ready when
        retry_offline_reader is set. Raises the final transport error
        once retries are exhausted; otherwise returns the last
        response.
        """
        max_retries = max(0, self.settings.sumup_max_retries)
        for attempt in range(max_retries + 1):
            try:
                response = send()
            except (requests.exceptions.ConnectionError,
                    requests.exceptions.Timeout) as e:
                if attempt >= max_retries:
                    raise
                logger.warning(
                    f"{label}: transient {type(e).__name__}, "
                    f"retrying ({attempt + 1}/{max_retries})"
                )
                self._backoff(attempt)
                continue

            retryable = response.status_code in self._RETRYABLE_STATUS_CODES or (
                retry_offline_reader
                and response.status_code == 422
                and self._offline_reader_body(response)
            )
            if retryable and attempt < max_retries:
                logger.warning(
                    f"{label}: transient HTTP {response.status_code}, "
                    f"retrying ({attempt + 1}/{max_retries})"
                )
                self._backoff(attempt)
                continue

            return response

    def _merchant_path(self, suffix: str) -> str:
        return f"/merchants/{self.settings.sumup_merchant_code}{suffix}"

    def _reader_url(self, suffix: str) -> str:
        return self._api_url(
            f"/merchants/{self.settings.sumup_merchant_code}"
            f"/readers/{self.settings.sumup_reader_id}{suffix}"
        )

    def _create_description(self, checkout_request: CheckoutRequest) -> str:
        if checkout_request.description:
            return checkout_request.description

        item_summary = []
        for item in checkout_request.items:
            if item.quantity > 1:
                item_summary.append(
                    f"{item.item_type} x{item.quantity} (£{item.price * item.quantity:.2f})"
                )
            else:
                item_summary.append(f"{item.item_type} (£{item.price:.2f})")

        return f"Self Checkout: {', '.join(item_summary)}"[:500]

    # ----------------------------------------------------------------
    #  Checkout
    # ----------------------------------------------------------------
    def process_payment(self, checkout_request: CheckoutRequest) -> PaymentResponse:
        amount_in_pence = int(checkout_request.total_amount * 100)
        description = self._create_description(checkout_request)

        payload = {
            "description": description,
            "total_amount": {
                "value": str(amount_in_pence),
                "currency": "GBP",
                "minor_unit": 2,
            },
        }

        logger.info(
            f"Processing payment for £{checkout_request.total_amount:.2f} "
            f"({amount_in_pence} pence)"
        )

        try:
            response = self._send_with_retries(
                lambda: self.session.post(
                    self._reader_url("/checkout"),
                    json=payload,
                    timeout=self.settings.request_timeout,
                ),
                label="Checkout request",
                retry_offline_reader=True,
            )

            logger.info(f"SumUp checkout response: HTTP {response.status_code}")

            if response.status_code in (200, 201):
                try:
                    data = response.json()
                    client_tx_id = data.get("data", {}).get("client_transaction_id")
                except Exception:
                    client_tx_id = None

                message = (
                    "Payment sent to reader. Follow instructions on the card reader."
                    if response.status_code == 201
                    else "Payment processed successfully!"
                )

                return PaymentResponse(
                    success=True,
                    client_transaction_id=client_tx_id,
                    message=message,
                    status_code=response.status_code,
                )

            return self._handle_checkout_error(response)

        except requests.exceptions.Timeout:
            logger.error("Checkout request timed out")
            return PaymentResponse(
                success=False,
                message="Payment request timed out. Please try again.",
                status_code=408,
            )
        except requests.exceptions.ConnectionError:
            logger.error("Connection error during checkout")
            return PaymentResponse(
                success=False,
                message="Connection failed. Check network and try again.",
                status_code=503,
            )
        except requests.exceptions.RequestException as e:
            safe_error = security_filter.sanitize_string(str(e))
            logger.error(f"Request exception during checkout: {safe_error}")
            return PaymentResponse(
                success=False,
                message="Payment request failed. Please try again.",
                status_code=500,
            )
        except Exception as e:
            safe_error = security_filter.sanitize_string(str(e))
            logger.error(f"Unexpected error during checkout: {safe_error}")
            return PaymentResponse(
                success=False,
                message="System error. Please contact support.",
                status_code=500,
            )

    def _handle_checkout_error(self, response) -> PaymentResponse:
        status = response.status_code

        user_message = "Payment could not be processed. Try again or contact support."

        if status == 422:
            try:
                detail = response.json().get("detail", "")
            except Exception:
                detail = ""
            if "offline" in detail.lower():
                user_message = "Card reader is offline. Check the reader and try again."
            else:
                user_message = "Card reader not ready. Ensure it is online and idle."
        elif status == 400:
            user_message = "Invalid payment request. Check your cart and try again."
        elif status == 402:
            user_message = "Payment declined. Try a different payment method."
        elif status == 409:
            user_message = "Reader is busy with another transaction. Please wait."
        elif status >= 500:
            user_message = "Payment service temporarily unavailable. Try again later."

        return PaymentResponse(
            success=False,
            message=user_message,
            status_code=status,
        )

    # ----------------------------------------------------------------
    #  Reader status (real API call)
    # ----------------------------------------------------------------
    def check_reader_status(self) -> Dict[str, Any]:
        try:
            response = self._send_with_retries(
                lambda: self.session.get(
                    self._reader_url("/status"),
                    timeout=10,
                ),
                label="Reader status",
                retry_offline_reader=False,
            )

            if response.status_code == 200:
                data = response.json().get("data", {})
                return {
                    "reader_id": self.settings.sumup_reader_id,
                    "online": data.get("status", "").upper() == "ONLINE",
                    "state": data.get("state", "IDLE"),
                    "battery_level": data.get("battery_level"),
                    "connection_type": data.get("connection_type"),
                    "last_checked": datetime.now().isoformat(),
                }

            logger.warning(f"Reader status returned HTTP {response.status_code}")
            return {
                "reader_id": "***MASKED***",
                "online": False,
                "state": "UNKNOWN",
                "last_checked": datetime.now().isoformat(),
            }

        except Exception:
            logger.warning("Could not reach reader status endpoint")
            return {
                "reader_id": "***MASKED***",
                "online": False,
                "state": "UNKNOWN",
                "last_checked": datetime.now().isoformat(),
            }

    # ----------------------------------------------------------------
    #  Transaction lookup
    # ----------------------------------------------------------------
    def find_transaction_status(
        self, client_transaction_id: str
    ) -> Dict[str, Any]:
        if not client_transaction_id:
            return {
                "found": False,
                "status": None,
                "transaction_id": None,
                "amount": None,
            }

        try:
            url = (
                f"https://api.sumup.com/v2.1"
                f"/merchants/{self.settings.sumup_merchant_code}"
                f"/transactions"
            )
            params = {"client_transaction_id": client_transaction_id}

            response = self._send_with_retries(
                lambda: self.session.get(url, params=params, timeout=10),
                label="Transaction lookup",
                retry_offline_reader=False,
            )

            if response.status_code == 404:
                logger.info(
                    f"No transaction found for client_tx_id (cancelled or not yet created)"
                )
                return {
                    "found": False,
                    "status": "NOT_FOUND",
                    "transaction_id": None,
                    "amount": None,
                }

            if response.status_code != 200:
                logger.warning(
                    f"Transaction lookup returned HTTP {response.status_code}"
                )
                return {
                    "found": False,
                    "status": "UNKNOWN",
                    "transaction_id": None,
                    "amount": None,
                }

            data = response.json()

            if isinstance(data, dict):
                returned_id = data.get("client_transaction_id")
                if returned_id != client_transaction_id:
                    logger.warning(
                        "Transaction lookup returned mismatched record; ignoring"
                    )
                    return {
                        "found": False,
                        "status": "NOT_FOUND",
                        "transaction_id": None,
                        "amount": None,
                    }
                return {
                    "found": True,
                    "status": data.get("status"),
                    "transaction_id": data.get("id") or data.get("transaction_id"),
                    "amount": data.get("amount"),
                }

            transactions = data if isinstance(data, list) else []
            for tx in transactions:
                if tx.get("client_transaction_id") == client_transaction_id:
                    return {
                        "found": True,
                        "status": tx.get("status"),
                        "transaction_id": tx.get("id") or tx.get("transaction_id"),
                        "amount": tx.get("amount"),
                    }

            logger.info(f"No matching transaction for: {client_transaction_id}")
            return {
                "found": False,
                "status": "NOT_FOUND",
                "transaction_id": None,
                "amount": None,
            }

        except Exception as e:
            safe_error = security_filter.sanitize_string(str(e))
            logger.error(f"Error looking up transaction: {safe_error}")
            return {
                "found": False,
                "status": None,
                "transaction_id": None,
                "amount": None,
            }


sumup_service = SumUpService()


def get_sumup_service() -> SumUpService:
    return sumup_service
