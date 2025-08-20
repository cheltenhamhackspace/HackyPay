from pydantic import BaseModel, Field, validator
from typing import List, Optional
from decimal import Decimal

class ItemTypeConfig(BaseModel):
    id: str
    name: str
    icon: str
    description: str
    enabled: bool

class ItemsConfig(BaseModel):
    item_types: List[ItemTypeConfig]
    settings: dict

class CartItem(BaseModel):
    item_type: str  # Changed from enum to string for flexibility
    price: Decimal = Field(..., gt=0, le=999.99, description="Price in GBP")
    quantity: int = Field(default=1, gt=0, le=100)
    
    @validator('price')
    def validate_price(cls, v):
        # Ensure price has at most 2 decimal places
        if v.as_tuple().exponent < -2:
            raise ValueError('Price cannot have more than 2 decimal places')
        return v

class CheckoutRequest(BaseModel):
    items: List[CartItem] = Field(..., min_items=1, max_items=50)
    total_amount: Decimal = Field(..., gt=0, le=9999.99)
    description: Optional[str] = Field(None, max_length=500)
    
    @validator('total_amount')
    def validate_total(cls, v, values):
        if 'items' in values:
            calculated_total = sum(item.price * item.quantity for item in values['items'])
            if abs(calculated_total - v) > Decimal('0.01'):
                raise ValueError('Total amount does not match sum of items')
        return v

class PaymentResponse(BaseModel):
    success: bool
    transaction_id: Optional[str] = None
    message: str
    status_code: int

class ReaderStatus(BaseModel):
    reader_id: str
    online: bool
    last_seen: Optional[str] = None

class HealthCheck(BaseModel):
    status: str
    timestamp: str
    version: str = "1.0.0"

class ErrorResponse(BaseModel):
    error: str
    detail: Optional[str] = None
    timestamp: str
