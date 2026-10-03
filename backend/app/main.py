from __future__ import annotations

import hmac
import logging
import os
import re
import time
from collections import defaultdict
from contextlib import asynccontextmanager
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from fastapi import FastAPI, HTTPException, Depends, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from .security import (
    get_secure_logger, create_safe_error_response,
    sanitize_request_for_logging, add_security_headers,
    validate_environment_security, SecureLoggerAdapter
)
from . import __version__
from .config import get_settings, SecureFormatter
from .models import (
    CheckoutRequest, PaymentResponse, HealthCheck,
    ErrorResponse, ReaderStatus, CartItem, TransactionStatusResponse
)
from .services.sumup_service import get_sumup_service, SumUpService
from .services.items_service import get_items_service, ItemsService

_root_handler = logging.StreamHandler()
_root_handler.setFormatter(SecureFormatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
logging.basicConfig(level=logging.INFO, handlers=[_root_handler])
logger = get_secure_logger(__name__)

settings = get_settings()

request_counts = defaultdict(list)

_TX_ID_PATTERN = re.compile(r'^[A-Za-z0-9._\-]{1,64}$')


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("HackyPay Self Checkout API starting up...")
    logger.info(f"Debug mode: {settings.debug}")
    logger.info(f"Allowed origins: {settings.allowed_origins}")

    security_issues = validate_environment_security()
    if security_issues:
        for issue in security_issues:
            logger.warning(f"Security issue: {issue}")

    try:
        _ = get_sumup_service()
        logger.info("SumUp service initialized successfully")
    except Exception as e:
        logger.error("Failed to initialize SumUp service")
        raise

    yield

    logger.info("HackyPay Self Checkout API shutting down...")


app = FastAPI(
    title="HackyPay Self Checkout API",
    description="Secure SumUp-based self checkout system",
    version=__version__,
    lifespan=lifespan,
    # Don't publish the API schema to the LAN on a production kiosk
    docs_url="/docs" if settings.debug else None,
    redoc_url="/redoc" if settings.debug else None,
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins.split(','),
    allow_credentials=False,  # no cookies/sessions exist; avoids wildcard origin echo
    allow_methods=["GET", "POST"],  # Restrict to only needed methods
    allow_headers=["Content-Type", "Accept"],  # Restrict headers
)


@app.middleware("http")
async def security_middleware(request: Request, call_next):
    """Add security headers, request size limit, and basic rate limiting"""
    start_time = time.time()

    # Reject oversized bodies before reading them (max_request_size bytes)
    content_length = request.headers.get("content-length")
    if content_length and content_length.isdigit() and int(content_length) > settings.max_request_size:
        logger.warning(f"Request body too large: {content_length} bytes from {request.client.host if request.client else 'unknown'}")
        return add_security_headers(create_safe_error_response(
            status_code=413,
            error_type="Payload Too Large",
            user_message="Request body exceeds the allowed size."
        ))

    client_ip = request.client.host if request.client else "unknown"
    current_time = time.time()

    request_counts[client_ip] = [
        req_time for req_time in request_counts[client_ip]
        if current_time - req_time < settings.rate_limit_window
    ]

    # Cap memory: keys are never aged out, so evict oldest IPs beyond a bound
    if len(request_counts) > settings.rate_limit_max_keys:
        for stale_ip in list(request_counts.keys())[:len(request_counts) - settings.rate_limit_max_keys]:
            del request_counts[stale_ip]

    if len(request_counts[client_ip]) >= settings.rate_limit_requests:
        logger.warning(f"Rate limit exceeded for IP: {client_ip}")
        return add_security_headers(create_safe_error_response(
            status_code=429,
            error_type="Rate Limit Exceeded",
            user_message="Too many requests. Please try again later."
        ))

    request_counts[client_ip].append(current_time)

    # Log request (sanitized)
    safe_request = sanitize_request_for_logging(request)
    logger.info(f"Request: {safe_request['method']} {safe_request['url']} from {safe_request['client_ip']}")

    # Process request
    response = await call_next(request)

    # Add security headers
    response = add_security_headers(response)

    # Log response time
    process_time = time.time() - start_time
    logger.debug(f"Request processed in {process_time:.3f}s")

    return response

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler to prevent sensitive data leakage"""
    # Log sanitized request info and error
    safe_request = sanitize_request_for_logging(request)
    logger.error(f"Unhandled exception on {safe_request['method']} {safe_request['url']}: {type(exc).__name__}")
    
    return create_safe_error_response(
        status_code=500,
        error_type="Internal Server Error",
        user_message="An unexpected error occurred. Please contact support."
    )

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Handle HTTP exceptions securely"""
    safe_request = sanitize_request_for_logging(request)
    logger.warning(f"HTTP exception on {safe_request['method']} {safe_request['url']}: {exc.status_code}")
    
    return create_safe_error_response(
        status_code=exc.status_code,
        error_type="Request Error",
        user_message=exc.detail if exc.status_code < 500 else "An error occurred processing your request."
    )

# Resolves to repo-root/frontend in dev; FRONTEND_DIR env is set in containers (/app/frontend).
FRONTEND_DIR = Path(
    os.environ.get("FRONTEND_DIR")
    or Path(__file__).resolve().parent.parent.parent / "frontend"
)

app.mount("/css", StaticFiles(directory=FRONTEND_DIR / "css"), name="css")
app.mount("/js", StaticFiles(directory=FRONTEND_DIR / "js"), name="js")
app.mount("/assets", StaticFiles(directory=FRONTEND_DIR / "assets"), name="assets")


@app.get("/", response_class=HTMLResponse)
async def serve_index():
    index_path = FRONTEND_DIR / "index.html"
    return HTMLResponse(content=index_path.read_text(encoding="utf-8"))


@app.get("/api/health", response_model=HealthCheck)
async def health_check():
    """Health check endpoint"""
    return HealthCheck(
        status="healthy",
        timestamp=datetime.now().isoformat()
    )

@app.get("/api/reader/status", response_model=ReaderStatus)
async def get_reader_status(sumup_service: SumUpService = Depends(get_sumup_service)):
    """Get SumUp reader status"""
    try:
        status_data = sumup_service.check_reader_status()

        return ReaderStatus(
            reader_id="configured" if status_data.get("reader_id") else "not_configured",
            online=status_data["online"],
            state=status_data.get("state"),
            last_seen=status_data.get("last_checked"),
        )
    except Exception:
        logger.warning("Error getting reader status")
        raise HTTPException(status_code=503, detail="Unable to check reader status")


@app.get("/api/transaction/{client_transaction_id}/status", response_model=TransactionStatusResponse)
async def get_transaction_status(
    client_transaction_id: str,
    sumup_service: SumUpService = Depends(get_sumup_service),
):
    """Poll for transaction status by client_transaction_id"""
    # Reject control characters etc. before they reach SumUp queries or logs (log-injection fix)
    if not _TX_ID_PATTERN.match(client_transaction_id):
        raise HTTPException(status_code=400, detail="Invalid transaction id format")
    try:
        result = sumup_service.find_transaction_status(client_transaction_id)
        return TransactionStatusResponse(**result)
    except Exception:
        logger.warning("Error looking up transaction status")
        raise HTTPException(status_code=500, detail="Unable to check transaction status")

@app.post("/api/cart/validate")
async def validate_cart(items: list[CartItem]):
    """Validate cart items before checkout"""
    try:
        if not items:
            raise HTTPException(
                status_code=400,
                detail="Cart cannot be empty"
            )
        
        if len(items) > 50:
            raise HTTPException(
                status_code=400,
                detail="Too many items in cart (maximum 50)"
            )
        
        total = sum(item.price * item.quantity for item in items)
        
        if total > 9999.99:
            raise HTTPException(
                status_code=400,
                detail="Cart total exceeds maximum allowed amount"
            )
        
        return {
            "valid": True,
            "total": float(total),
            "item_count": len(items),
            "message": "Cart is valid"
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error validating cart: {e}")
        raise HTTPException(
            status_code=500,
            detail="Error validating cart"
        )

@app.post("/api/checkout", response_model=PaymentResponse)
async def process_checkout(
    checkout_request: CheckoutRequest,
    sumup_service: SumUpService = Depends(get_sumup_service),
    items_service: ItemsService = Depends(get_items_service),
):
    """Process payment through SumUp reader"""
    try:
        # Server-side enforcement of the configured price rules — the frontend
        # cap is a convenience, not a control (C1 fix)
        cfg_settings = items_service.get_settings()
        max_price = Decimal(str(cfg_settings.get("max_price", 999.99)))
        min_price = Decimal(str(cfg_settings.get("min_price", 0.01)))

        for item in checkout_request.items:
            if not items_service.validate_item_type(item.item_type):
                return PaymentResponse(
                    success=False,
                    message=f"'{item.item_type}' is not an available item.",
                    status_code=400,
                )
            if item.price > max_price:
                return PaymentResponse(
                    success=False,
                    message=f"Maximum price per item is £{max_price:.2f}.",
                    status_code=400,
                )

        if checkout_request.total_amount > max_price:
            return PaymentResponse(
                success=False,
                message=f"Maximum total price is £{max_price:.2f}.",
                status_code=400,
            )
        if checkout_request.total_amount < min_price:
            return PaymentResponse(
                success=False,
                message=f"Minimum total price is £{min_price:.2f}.",
                status_code=400,
            )

        logger.info(f"Processing checkout for £{checkout_request.total_amount:.2f}")

        # Process payment through SumUp service
        payment_result = sumup_service.process_payment(checkout_request)

        # Log the result
        if payment_result.success:
            logger.info(f"Payment successful - Transaction ID: {payment_result.transaction_id}")
        else:
            logger.warning(f"Payment failed - {payment_result.message}")

        return payment_result

    except Exception as e:
        logger.error(f"Error processing checkout: {e}")
        return PaymentResponse(
            success=False,
            message="System error occurred during checkout. Please try again.",
            status_code=500
        )

@app.get("/api/item-types")
async def get_item_types(items_service: ItemsService = Depends(get_items_service)):
    """Get available item types from configuration"""
    try:
        enabled_items = items_service.get_enabled_item_types()
        return {
            "item_types": [
                {
                    "id": item.id,
                    "name": item.name,
                    "icon": item.icon,
                    "description": item.description
                }
                for item in enabled_items
            ],
            "settings": items_service.get_settings()
        }
    except Exception as e:
        logger.error(f"Error getting item types: {e}")
        raise HTTPException(
            status_code=500,
            detail="Error loading item types"
        )

@app.post("/api/config/reload")
async def reload_config(
    request: Request,
    items_service: ItemsService = Depends(get_items_service)
):
    """Reload items configuration from file - Protected endpoint"""
    client_ip = request.client.host if request.client else "unknown"
    is_loopback = client_ip in ("127.0.0.1", "localhost", "::1")
    admin_token = settings.admin_token
    provided_token = request.headers.get("X-Admin-Token")

    if admin_token:
        # Shared-secret auth (proxy-safe); timing-safe compare
        if not provided_token or not hmac.compare_digest(provided_token, admin_token):
            logger.warning("Config reload rejected: missing or invalid admin token")
            raise HTTPException(status_code=403, detail="Access denied")
    elif not is_loopback:
        # No admin token configured: loopback-only fallback
        logger.warning(f"Config reload attempted from non-localhost IP: {client_ip}")
        raise HTTPException(
            status_code=403,
            detail="Access denied"
        )

    try:
        items_service.reload_config()
        logger.info("Items configuration reloaded successfully")
        return {"message": "Configuration reloaded successfully"}
    except Exception as e:
        logger.error("Error reloading configuration")
        raise HTTPException(
            status_code=500,
            detail="Error reloading configuration"
        )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        log_level="info",
        # Do not honor X-Forwarded-For from any peer: client IP comes from the
        # socket only (prevents XFF-based authz/rate-limit spoofing)
        proxy_headers=False,
    )
