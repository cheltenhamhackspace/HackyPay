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

logger = logging.getLogger(__name__)

class SumUpService:
    def __init__(self):
        self.settings = get_settings()
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {self.settings.sumup_api_token}",
            "Content-Type": "application/json"
        })
    
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
            logger.debug(f"Payload: {payload}")
            
            # Make API request to SumUp
            response = self.session.post(
                self._get_checkout_url(),
                json=payload,
                timeout=self.settings.request_timeout
            )
            
            logger.info(f"SumUp API response: {response.status_code}")
            
            # Handle successful responses
            if response.status_code in [200, 201]:
                try:
                    response_data = response.json()
                    transaction_id = response_data.get('id', 'unknown')
                except:
                    # Some successful responses might not have JSON body
                    transaction_id = None
                
                if response.status_code == 201:
                    message = "Payment sent to reader successfully. Please follow instructions on card reader."
                else:
                    message = "Payment processed successfully!"
                
                logger.info(f"Payment successful - Transaction ID: {transaction_id}")
                
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
                    error_detail = error_data.get('message', error_data.get('error', str(error_data)))
                except:
                    error_detail = response.text or f"HTTP {response.status_code}"
                
                logger.error(f"Payment failed - Status: {response.status_code}, Error: {error_detail}")
                
                return PaymentResponse(
                    success=False,
                    message=f"Payment failed: {error_detail}",
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
            logger.error(f"Request exception during payment: {e}")
            return PaymentResponse(
                success=False,
                message="Payment request failed. Please try again.",
                status_code=500
            )
        
        except Exception as e:
            logger.error(f"Unexpected error during payment: {e}")
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
            logger.error(f"Error checking reader status: {e}")
            return {
                "reader_id": self.settings.sumup_reader_id,
                "online": False,
                "error": str(e),
                "last_checked": datetime.now().isoformat()
            }

# Global service instance
sumup_service = SumUpService()

def get_sumup_service() -> SumUpService:
    """Get SumUp service instance"""
    return sumup_service
