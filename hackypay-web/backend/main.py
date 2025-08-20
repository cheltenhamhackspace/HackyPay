from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from datetime import datetime
import logging

from config import get_settings
from models import (
    CheckoutRequest, PaymentResponse, HealthCheck, 
    ErrorResponse, ReaderStatus, CartItem
)
from services.sumup_service import get_sumup_service, SumUpService
from services.items_service import get_items_service, ItemsService

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="HackyPay Self Checkout API",
    description="Secure SumUp-based self checkout system",
    version="1.0.0"
)

# Get settings
settings = get_settings()

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins.split(','),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)

@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """Global exception handler to prevent sensitive data leakage"""
    logger.error(f"Unhandled exception: {exc}")
    return JSONResponse(
        status_code=500,
        content=ErrorResponse(
            error="Internal server error",
            detail="An unexpected error occurred. Please contact support.",
            timestamp=datetime.now().isoformat()
        ).dict()
    )

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
            reader_id=status_data["reader_id"],
            online=status_data["online"],
            last_seen=status_data.get("last_checked")
        )
    except Exception as e:
        logger.error(f"Error getting reader status: {e}")
        raise HTTPException(
            status_code=503,
            detail="Unable to check reader status"
        )

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

@app.get("/api/config/reload")
async def reload_config(items_service: ItemsService = Depends(get_items_service)):
    """Reload items configuration from file"""
    try:
        items_service.reload_config()
        logger.info("Items configuration reloaded successfully")
        return {"message": "Configuration reloaded successfully"}
    except Exception as e:
        logger.error(f"Error reloading configuration: {e}")
        raise HTTPException(
            status_code=500,
            detail="Error reloading configuration"
        )

# Startup event
@app.on_event("startup")
async def startup_event():
    """Application startup"""
    logger.info("HackyPay Self Checkout API starting up...")
    logger.info(f"Debug mode: {settings.debug}")
    logger.info(f"Allowed origins: {settings.allowed_origins}")
    
    # Validate configuration
    try:
        _ = get_sumup_service()
        logger.info("SumUp service initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize SumUp service: {e}")
        raise

# Shutdown event
@app.on_event("shutdown")
async def shutdown_event():
    """Application shutdown"""
    logger.info("HackyPay Self Checkout API shutting down...")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        log_level="info"
    )
