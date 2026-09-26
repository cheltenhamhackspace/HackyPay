import os
import logging
from typing import Optional
from pydantic import field_validator
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Configure logging to never log sensitive configuration values
class SecureFormatter(logging.Formatter):
    """Custom formatter that masks sensitive data"""
    
    def format(self, record):
        # Get the original formatted message
        msg = super().format(record)
        
        # Mask any potential API tokens or sensitive data
        sensitive_patterns = [
            (r'sup_sk_[a-zA-Z0-9]+', 'sup_sk_***MASKED***'),
            (r'rdr_[a-zA-Z0-9]+', 'rdr_***MASKED***'),
            (r'Bearer\s+[a-zA-Z0-9_\-\.]+', 'Bearer ***MASKED***'),
        ]
        
        for pattern, replacement in sensitive_patterns:
            import re
            msg = re.sub(pattern, replacement, msg, flags=re.IGNORECASE)
        
        return msg

class Settings(BaseSettings):
    # SumUp API Configuration
    sumup_api_token: str
    sumup_merchant_code: str
    sumup_reader_id: str
    sumup_api_base_url: str = "https://api.sumup.com/v0.1"
    
    # Server Configuration
    host: str = "127.0.0.1"
    port: int = 8000
    debug: bool = False
    
    # CORS Configuration
    allowed_origins: str = "http://localhost:3000,http://127.0.0.1:3000,http://localhost:8080,http://127.0.0.1:8080"
    
    # Security Configuration
    api_key_header: str = "X-API-Key"
    request_timeout: int = 30
    max_request_size: int = 1024 * 1024  # 1MB
    rate_limit_requests: int = 100  # requests per minute per IP
    rate_limit_window: int = 60  # seconds
    
    # Additional Security Settings
    enable_security_headers: bool = True
    log_requests: bool = True
    mask_sensitive_logs: bool = True
    
    @field_validator('sumup_api_token')
    @classmethod
    def validate_api_token(cls, v):
        if not v or not v.startswith('sup_sk_'):
            raise ValueError('Invalid SumUp API token format')
        if len(v) < 20:
            raise ValueError('SumUp API token appears to be too short')
        return v

    @field_validator('sumup_merchant_code')
    @classmethod
    def validate_merchant_code(cls, v):
        if not v or len(v) < 5:
            raise ValueError('Invalid merchant code')
        return v

    @field_validator('sumup_reader_id')
    @classmethod
    def validate_reader_id(cls, v):
        if not v or not v.startswith('rdr_'):
            raise ValueError('Invalid reader ID format')
        return v

    @field_validator('debug')
    @classmethod
    def validate_debug_mode(cls, v):
        if v:
            import warnings
            warnings.warn(
                "Debug mode is enabled. This should be disabled in production.",
                UserWarning
            )
        return v

    @field_validator('allowed_origins')
    @classmethod
    def validate_cors_origins(cls, v):
        if '*' in v:
            import warnings
            warnings.warn(
                "Wildcard CORS origins detected. This should be restricted in production.",
                UserWarning
            )
        return v
    
    def get_masked_token(self) -> str:
        """Get a masked version of the API token for logging"""
        if not self.sumup_api_token:
            return "NOT_SET"
        return f"{self.sumup_api_token[:10]}***MASKED***"
    
    def get_masked_reader_id(self) -> str:
        """Get a masked version of the reader ID for logging"""
        if not self.sumup_reader_id:
            return "NOT_SET"
        return f"{self.sumup_reader_id[:6]}***MASKED***"
    
    class Config:
        env_file = ".env"
        case_sensitive = False

# Global settings instance
settings = Settings()

def get_settings() -> Settings:
    """Get application settings"""
    return settings

def validate_production_config() -> list[str]:
    """Validate configuration for production deployment"""
    issues = []
    
    if settings.debug:
        issues.append("Debug mode should be disabled in production")
    
    if settings.host == "0.0.0.0":
        issues.append("Host should not be 0.0.0.0 in production without proper firewall")
    
    if '*' in settings.allowed_origins:
        issues.append("CORS origins should not include wildcards in production")
    
    if not settings.sumup_api_token or len(settings.sumup_api_token) < 20:
        issues.append("SumUp API token appears to be invalid or not set")
    
    return issues

def get_safe_config_summary() -> dict:
    """Get a safe summary of configuration for logging (no secrets)"""
    return {
        "host": settings.host,
        "port": settings.port,
        "debug": settings.debug,
        "api_base_url": settings.sumup_api_base_url,
        "request_timeout": settings.request_timeout,
        "rate_limit_requests": settings.rate_limit_requests,
        "security_headers_enabled": settings.enable_security_headers,
        "token_configured": bool(settings.sumup_api_token),
        "merchant_code_configured": bool(settings.sumup_merchant_code),
        "reader_id_configured": bool(settings.sumup_reader_id),
    }
