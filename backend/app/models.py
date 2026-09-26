from pydantic import BaseModel, Field, field_validator, model_validator
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
    item_type: str = Field(..., min_length=1, max_length=100)
    price: Decimal = Field(..., gt=0, le=999.99, description="Price in GBP")
    quantity: int = Field(default=1, gt=0, le=100)

    @field_validator('price')
    @classmethod
    def validate_price(cls, v):
        if v.as_tuple().exponent < -2:
            raise ValueError('Price cannot have more than 2 decimal places')
        return v

class CheckoutRequest(BaseModel):
    items: List[CartItem] = Field(..., min_length=1, max_length=50)
    total_amount: Decimal = Field(..., gt=0, le=9999.99)
    description: Optional[str] = Field(None, max_length=500)

    @field_validator('total_amount')
    @classmethod
    def validate_total_amount(cls, v):
        if v.as_tuple().exponent < -2:
            raise ValueError('Total amount cannot have more than 2 decimal places')
        return v

    @model_validator(mode='after')
    def validate_total(self):
        calculated_total = sum(item.price * item.quantity for item in self.items)
        if abs(calculated_total - self.total_amount) > Decimal('0.01'):
            raise ValueError('Total amount does not match sum of items')
        return self

class PaymentResponse(BaseModel):
    success: bool
    transaction_id: Optional[str] = None
    client_transaction_id: Optional[str] = None
    message: str
    status_code: int


class ReaderStatus(BaseModel):
    reader_id: str
    online: bool
    state: Optional[str] = None
    last_seen: Optional[str] = None


class TransactionStatusResponse(BaseModel):
    found: bool
    status: Optional[str] = None
    transaction_id: Optional[str] = None
    amount: Optional[float] = None

class HealthCheck(BaseModel):
    status: str
    timestamp: str
    version: str = "1.0.0"

class ErrorResponse(BaseModel):
    error: str
    detail: Optional[str] = None
    timestamp: str
