import requests
import logging
from typing import Dict, Any, Optional
from decimal import Decimal
from datetime import datetime

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import get_settings
from models import CheckoutRequest, PaymentResponse
from security import get_secure_logger, security_filter

logger = get_secure_logger(__name__)

class SumUpService:
    def __init__(self):
        self.settings = get_settings()
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {self.settings.sumup_api_token}",
            "Content-Type": "application/json"
        })
        
        # Validate that we have the required credentials
        if not self.settings.sumup_api_token or not self.settings.sumup_merchant_code:
            logger.error("Missing required SumUp credentials")
            raise ValueError("SumUp service not properly configured")
    
    def _get_checkout_url(self) -> str:
        """Get the SumUp checkout URL for the configured reader"""
        return (f"{self.settings.sumup_api_base_url}/merchants/"
                f"{self.settings.sumup_merchant_code}/readers/"
                f"{self.settings.sumup_reader_id}/checkout")
    
    def _create_description(self, checkout_request: CheckoutRequest) -> str:
        """Create a description for the transaction"""
        if checkout_request.description:
            return checkout_request.description
        
        # Create description from cart items
        item_summary = []
        for item in checkout_request.items:
            if item.quantity > 1:
                item_summary.append(f"{item.item_type} x{item.quantity} (£{item.price * item.quantity:.2f})")
            else:
                item_summary.append(f"{item.item_type} (£{item.price:.2f})")
        
        return f"Self Checkout: {', '.join(item_summary)}"
    
    def process_payment(self, checkout_request: CheckoutRequest) -> PaymentResponse:
        """
        Process payment through SumUp reader
        
        Args:
            checkout_request: The checkout request with items and total
            
        Returns:
            PaymentResponse with success status and details
        """
        try:
            # Convert total to pence (SumUp expects minor units)
            amount_in_pence = int(checkout_request.total_amount * 100)
            
            # Create transaction description
            description = self._create_description(checkout_request)
            
            # Prepare API request payload
            payload = {
                "description": description,
                "total_amount": {
                    "value": str(amount_in_pence),
                    "currency": "GBP",
                    "minor_unit": 2
                }
            }
            
            logger.info(f"Processing payment for £{checkout_request.total_amount:.2f} ({amount_in_pence} pence)")
            # Log sanitized payload (never log the full request which might contain sensitive data)
            safe_payload = {
                "description": payload["description"],
                "total_amount": payload["total_amount"]
            }
            logger.debug(f"Payment payload: {safe_payload}")
            
            # Make API request to SumUp
            response = self.session.post(
                self._get_checkout_url(),
                json=payload,
                timeout=self.settings.request_timeout
            )
            
            logger.info(f"SumUp API response: {response.status_code}")
            
            # Never log the full response as it might contain sensitive data
            if response.status_code not in [200, 201]:
                # Only log safe error information
                logger.warning(f"Payment request failed with status {response.status_code}")
            
            # Handle successful responses
            if response.status_code in [200, 201]:
                try:
                    response_data = response.json()
                    transaction_id = response_data.get('id', 'unknown')
                    
                    # Sanitize response data before any potential logging
                    safe_response_data = security_filter.sanitize_dict(response_data)
                    
                except Exception as e:
                    # Some successful responses might not have JSON body
                    transaction_id = None
                    logger.debug("Response body could not be parsed as JSON")
                
                if response.status_code == 201:
                    message = "Payment sent to reader successfully. Please follow instructions on card reader."
                else:
                    message = "Payment processed successfully!"
                
                # Only log the transaction ID, never the full response
                safe_transaction_id = transaction_id if transaction_id and transaction_id != 'unknown' else 'generated'
                logger.info(f"Payment successful - Transaction ID: {safe_transaction_id}")
                
                return PaymentResponse(
                    success=True,
                    transaction_id=transaction_id,
                    message=message,
                    status_code=response.status_code
                )
            
            # Handle error responses
            else:
                error_detail = "Unknown error"
                try:
                    error_data = response.json()
                    # Sanitize error data to prevent sensitive information leakage
                    safe_error_data = security_filter.sanitize_dict(error_data)
                    error_detail = safe_error_data.get('message', safe_error_data.get('error', 'API error'))
                except Exception:
                    error_detail = f"HTTP {response.status_code}"
                
                # Log sanitized error information
                logger.error(f"Payment failed - Status: {response.status_code}")
                
                # Return generic error message to prevent information disclosure
                user_message = "Payment could not be processed. Please try again or contact support."
                if response.status_code == 400:
                    user_message = "Invalid payment request. Please check your cart and try again."
                elif response.status_code == 402:
                    user_message = "Payment was declined. Please try a different payment method."
                elif response.status_code >= 500:
                    user_message = "Payment service temporarily unavailable. Please try again later."
                
                return PaymentResponse(
                    success=False,
                    message=user_message,
                    status_code=response.status_code
                )
        
        except requests.exceptions.Timeout:
            logger.error("Payment request timed out")
            return PaymentResponse(
                success=False,
                message="Payment request timed out. Please try again.",
                status_code=408
            )
        
        except requests.exceptions.ConnectionError:
            logger.error("Connection error during payment")
            return PaymentResponse(
                success=False,
                message="Connection failed. Please check network and try again.",
                status_code=503
            )
        
        except requests.exceptions.RequestException as e:
            # Log sanitized error information
            safe_error = security_filter.sanitize_string(str(e))
            logger.error(f"Request exception during payment: {safe_error}")
            return PaymentResponse(
                success=False,
                message="Payment request failed. Please try again.",
                status_code=500
            )
        
        except Exception as e:
            # Log sanitized error information
            safe_error = security_filter.sanitize_string(str(e))
            logger.error(f"Unexpected error during payment: {safe_error}")
            return PaymentResponse(
                success=False,
                message="System error occurred. Please contact support.",
                status_code=500
            )
    
    def check_reader_status(self) -> Dict[str, Any]:
        """
        Check if the SumUp reader is online and available
        
        Returns:
            Dictionary with reader status information
        """
        try:
            # Note: SumUp API doesn't have a direct reader status endpoint
            # This is a placeholder for future implementation or alternative checking method
            return {
                "reader_id": self.settings.sumup_reader_id,
                "online": True,  # Assume online unless we can verify otherwise
                "last_checked": datetime.now().isoformat()
            }
        except Exception as e:
            # Log sanitized error information
            safe_error = security_filter.sanitize_string(str(e))
            logger.error(f"Error checking reader status: {safe_error}")
            return {
                "reader_id": "***MASKED***",  # Don't expose reader ID in error responses
                "online": False,
                "error": "Unable to check reader status",
                "last_checked": datetime.now().isoformat()
            }

# Global service instance
sumup_service = SumUpService()

def get_sumup_service() -> SumUpService:
    """Get SumUp service instance"""
    return sumup_service
