import pytest
from decimal import Decimal
from pydantic import ValidationError

from app.models import CartItem, CheckoutRequest


class TestCartItem:
    def test_valid_cart_item(self):
        item = CartItem(item_type="Food & Drink", price=Decimal("5.50"))
        assert item.item_type == "Food & Drink"
        assert item.price == Decimal("5.50")
        assert item.quantity == 1

    def test_valid_cart_item_with_quantity(self):
        item = CartItem(item_type="Laser Time", price=Decimal("12.00"), quantity=3)
        assert item.quantity == 3

    def test_zero_price_rejected(self):
        with pytest.raises(ValidationError):
            CartItem(item_type="Test", price=Decimal("0.00"))

    def test_negative_price_rejected(self):
        with pytest.raises(ValidationError):
            CartItem(item_type="Test", price=Decimal("-5.00"))

    def test_price_too_high_rejected(self):
        with pytest.raises(ValidationError):
            CartItem(item_type="Test", price=Decimal("1000.00"))

    def test_too_many_decimal_places_rejected(self):
        with pytest.raises(ValidationError):
            CartItem(item_type="Test", price=Decimal("5.123"))

    def test_two_decimal_places_allowed(self):
        item = CartItem(item_type="Test", price=Decimal("5.12"))
        assert item.price == Decimal("5.12")

    def test_zero_quantity_rejected(self):
        with pytest.raises(ValidationError):
            CartItem(item_type="Test", price=Decimal("5.00"), quantity=0)

    def test_negative_quantity_rejected(self):
        with pytest.raises(ValidationError):
            CartItem(item_type="Test", price=Decimal("5.00"), quantity=-1)

    def test_quantity_over_100_rejected(self):
        with pytest.raises(ValidationError):
            CartItem(item_type="Test", price=Decimal("5.00"), quantity=101)

    def test_price_max_boundary(self):
        item = CartItem(item_type="Test", price=Decimal("999.99"))
        assert item.price == Decimal("999.99")


class TestCheckoutRequest:
    def test_valid_checkout(self):
        items = [CartItem(item_type="Food", price=Decimal("5.50"), quantity=2)]
        checkout = CheckoutRequest(items=items, total_amount=Decimal("11.00"))
        assert checkout.total_amount == Decimal("11.00")

    def test_total_mismatch_rejected(self):
        items = [CartItem(item_type="Food", price=Decimal("5.50"), quantity=2)]
        with pytest.raises(ValidationError):
            CheckoutRequest(items=items, total_amount=Decimal("10.00"))

    def test_total_mismatch_barely_over_rejected(self):
        items = [CartItem(item_type="Food", price=Decimal("5.50"))]
        with pytest.raises(ValidationError):
            CheckoutRequest(items=items, total_amount=Decimal("5.48"))

    def test_total_within_tolerance(self):
        items = [CartItem(item_type="Food", price=Decimal("5.50"))]
        checkout = CheckoutRequest(items=items, total_amount=Decimal("5.51"))
        assert checkout.total_amount == Decimal("5.51")

    def test_empty_items_rejected(self):
        with pytest.raises(ValidationError):
            CheckoutRequest(items=[], total_amount=Decimal("0.00"))

    def test_too_many_items_rejected(self):
        items = [CartItem(item_type=f"Item{i}", price=Decimal("1.00")) for i in range(51)]
        with pytest.raises(ValidationError):
            CheckoutRequest(items=items, total_amount=Decimal("51.00"))

    def test_max_items_allowed(self):
        items = [CartItem(item_type=f"Item{i}", price=Decimal("1.00")) for i in range(50)]
        checkout = CheckoutRequest(items=items, total_amount=Decimal("50.00"))
        assert len(checkout.items) == 50

    def test_multiple_items_total(self):
        items = [
            CartItem(item_type="Food", price=Decimal("3.50")),
            CartItem(item_type="Drink", price=Decimal("2.00")),
            CartItem(item_type="Snack", price=Decimal("1.50")),
        ]
        checkout = CheckoutRequest(items=items, total_amount=Decimal("7.00"))
        assert checkout.total_amount == Decimal("7.00")

    def test_description_optional(self):
        items = [CartItem(item_type="Food", price=Decimal("5.00"))]
        checkout = CheckoutRequest(items=items, total_amount=Decimal("5.00"))
        assert checkout.description is None

    def test_description_with_max_length(self):
        items = [CartItem(item_type="Food", price=Decimal("5.00"))]
        description = "x" * 500
        checkout = CheckoutRequest(items=items, total_amount=Decimal("5.00"), description=description)
        assert len(checkout.description) == 500

    def test_description_too_long_rejected(self):
        items = [CartItem(item_type="Food", price=Decimal("5.00"))]
        with pytest.raises(ValidationError):
            CheckoutRequest(items=items, total_amount=Decimal("5.00"), description="x" * 501)
