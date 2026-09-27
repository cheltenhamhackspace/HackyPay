"""
Security utilities for HackyPay API
Handles secret sanitization, secure logging, and response filtering
"""
import re
import logging
from typing import Any, Dict, List, Union
from fastapi import Request
from fastapi.responses import JSONResponse
from datetime import datetime

# Patterns to identify sensitive data. The sensitive portion is captured in
# group 1 so _mask_sensitive_data() can replace just that group while the
# surrounding context (prefixes, keys, quotes) is preserved.
SENSITIVE_PATTERNS = [
    r'sup_sk_([a-zA-Z0-9_.\-]+)',  # SumUp API tokens (incl. separator chars)
    r'rdr_([a-zA-Z0-9_.\-]+)',     # SumUp reader IDs
    r'Bearer\s+([a-zA-Z0-9_\-\.]+)',  # Bearer tokens
    r'Authorization:\s*Bearer\s+([^\s]+)',  # Authorization headers
    r'X-API-Key:\s*([^\s]+)',  # API key headers
    r'api_token["\']?\s*[:=]\s*["\']([^"\']+)["\']',  # API token assignments
    r'token["\']?\s*[:=]\s*["\']([^"\']+)["\']',  # Generic token assignments
]

class SecurityFilter:
    """Handles sanitization of sensitive data from logs and responses"""
    
    def __init__(self):
        self.patterns = [re.compile(pattern, re.IGNORECASE) for pattern in SENSITIVE_PATTERNS]
    
    def sanitize_string(self, text: str) -> str:
        """Remove or mask sensitive data from strings"""
        if not isinstance(text, str):
            return text
            
        sanitized = text
        for pattern in self.patterns:
            # Replace the sensitive group with a masked version
            sanitized = pattern.sub(self._mask_sensitive_data, sanitized)
        
        return sanitized
    
    def _mask_sensitive_data(self, match: "re.Match[str]") -> str:
        """Replace the sensitive portion (group 1), preserving the rest of the match"""
        start = match.start(1) - match.start(0)
        end = match.end(1) - match.start(0)
        return match.group(0)[:start] + '***MASKED***' + match.group(0)[end:]
    
    def sanitize_dict(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Recursively sanitize dictionary data"""
        if not isinstance(data, dict):
            return data
            
        sanitized = {}
        for key, value in data.items():
            # Check if key suggests sensitive data
            if any(sensitive in key.lower() for sensitive in ['token', 'key', 'secret', 'password', 'auth']):
                sanitized[key] = '***MASKED***'
            elif isinstance(value, str):
                sanitized[key] = self.sanitize_string(value)
            elif isinstance(value, dict):
                sanitized[key] = self.sanitize_dict(value)
            elif isinstance(value, list):
                sanitized[key] = self.sanitize_list(value)
            else:
                sanitized[key] = value
                
        return sanitized
    
    def sanitize_list(self, data: List[Any]) -> List[Any]:
        """Recursively sanitize list data"""
        if not isinstance(data, list):
            return data
            
        sanitized = []
        for item in data:
            if isinstance(item, str):
                sanitized.append(self.sanitize_string(item))
            elif isinstance(item, dict):
                sanitized.append(self.sanitize_dict(item))
            elif isinstance(item, list):
                sanitized.append(self.sanitize_list(item))
            else:
                sanitized.append(item)
                
        return sanitized

# Global security filter instance
security_filter = SecurityFilter()

class SecureLoggerAdapter(logging.LoggerAdapter):
    """Logger adapter that automatically sanitizes log messages"""
    
    def process(self, msg, kwargs):
        # Sanitize the message; lazy %-args are masked at output by SecureFormatter
        if isinstance(msg, str):
            msg = security_filter.sanitize_string(msg)
        
        # Sanitize extra data
        if 'extra' in kwargs and isinstance(kwargs['extra'], dict):
            kwargs['extra'] = security_filter.sanitize_dict(kwargs['extra'])
            
        return msg, kwargs

def get_secure_logger(name: str) -> SecureLoggerAdapter:
    """Get a logger that automatically sanitizes sensitive data"""
    base_logger = logging.getLogger(name)
    return SecureLoggerAdapter(base_logger, {})

def create_safe_error_response(
    status_code: int = 500,
    error_type: str = "Internal Server Error",
    user_message: str = "An unexpected error occurred. Please contact support.",
    include_timestamp: bool = True
) -> JSONResponse:
    """Create a safe error response that doesn't leak sensitive information"""
    
    response_data = {
        "error": error_type,
        "message": user_message,
        "status_code": status_code
    }
    
    if include_timestamp:
        response_data["timestamp"] = datetime.now().isoformat()
    
    return JSONResponse(
        status_code=status_code,
        content=response_data
    )

def sanitize_request_for_logging(request: Request) -> Dict[str, Any]:
    """Sanitize request data for safe logging"""
    safe_request = {
        "method": request.method,
        "url": str(request.url.path),  # Don't include query params which might contain sensitive data
        "client_ip": request.client.host if request.client else "unknown",
        "user_agent": request.headers.get("user-agent", "unknown")
    }
    
    # Don't log headers as they might contain authorization tokens
    return safe_request

def validate_environment_security():
    """Validate that environment variables are properly configured for security"""
    import os
    from .config import get_settings

    settings = get_settings()
    issues = []

    # Check if sensitive environment variables are set
    required_vars = ['SUMUP_API_TOKEN', 'SUMUP_MERCHANT_CODE', 'SUMUP_READER_ID']
    for var in required_vars:
        if not os.getenv(var) and not getattr(settings, var.lower(), None):
            issues.append(f"Missing required environment variable: {var}")

    # Check debug mode via settings (pydantic reads case-insensitive env names,
    # which os.getenv('DEBUG') alone would miss)
    if settings.debug:
        issues.append("DEBUG mode should be disabled in production")

    return issues

# Middleware for additional security headers
def add_security_headers(response):
    """Add security headers to responses"""
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self'; style-src 'self'; "
        "img-src 'self'; font-src 'self'; connect-src 'self'; "
        "frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
    )
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, private"
    response.headers["Pragma"] = "no-cache"
    return response
