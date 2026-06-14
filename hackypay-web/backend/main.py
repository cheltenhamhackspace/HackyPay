from fastapi import FastAPI, HTTPException, Depends, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
import logging
import time
from collections import defaultdict

from config import get_settings
from models import (
    CheckoutRequest, PaymentResponse, HealthCheck,
    ErrorResponse, ReaderStatus, CartItem, TransactionStatusResponse
)
from services.sumup_service import get_sumup_service, SumUpService
from services.items_service import get_items_service, ItemsService
from security import (
    get_secure_logger, create_safe_error_response,
    sanitize_request_for_logging, add_security_headers,
    validate_environment_security
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = get_secure_logger(__name__)

settings = get_settings()

request_counts = defaultdict(list)


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
    version="1.0.0",
    lifespan=lifespan,
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins.split(','),
    allow_credentials=True,
    allow_methods=["GET", "POST"],  # Restrict to only needed methods
    allow_headers=["Content-Type", "Accept"],  # Restrict headers
)

# Simple rate limiting storage (in production, use Redis or similar)
request_counts = defaultdict(list)

@app.middleware("http")
async def security_middleware(request: Request, call_next):
    """Add security headers and basic rate limiting"""
    start_time = time.time()
    
    # Basic rate limiting (100 requests per minute per IP)
    client_ip = request.client.host if request.client else "unknown"
    current_time = time.time()
    
    # Clean old requests (older than 1 minute)
    request_counts[client_ip] = [
        req_time for req_time in request_counts[client_ip] 
        if current_time - req_time < 60
    ]
    
    # Check rate limit
    if len(request_counts[client_ip]) >= 100:
        logger.warning(f"Rate limit exceeded for IP: {client_ip}")
        return create_safe_error_response(
            status_code=429,
            error_type="Rate Limit Exceeded",
            user_message="Too many requests. Please try again later."
        )
    
    # Add current request
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

FRONTEND_DIR = Path(__file__).parent.parent / "frontend"

app.mount("/css", StaticFiles(directory=FRONTEND_DIR / "css"), name="css")
app.mount("/js", StaticFiles(directory=FRONTEND_DIR / "js"), name="js")


@app.get("/", response_class=HTMLResponse)
async def serve_index():
    index_path = FRONTEND_DIR / "index.html"
    return HTMLResponse(content=index_path.read_text())


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
    sumup_service: SumUpService = Depends(get_sumup_service)
):
    """Process payment through SumUp reader"""
    try:
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
    # Basic protection: only allow from localhost
    client_ip = request.client.host if request.client else "unknown"
    if client_ip not in ["127.0.0.1", "localhost", "::1"]:
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
        "main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        log_level="info"
    )
