import os
from typing import Optional
from pydantic import validator
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

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
    
    # Security
    api_key_header: str = "X-API-Key"
    request_timeout: int = 30
    max_request_size: int = 1024 * 1024  # 1MB
    
    @validator('sumup_api_token')
    def validate_api_token(cls, v):
        if not v or not v.startswith('sup_sk_'):
            raise ValueError('Invalid SumUp API token format')
        return v
    
    @validator('sumup_merchant_code')
    def validate_merchant_code(cls, v):
        if not v or len(v) < 5:
            raise ValueError('Invalid merchant code')
        return v
    
    @validator('sumup_reader_id')
    def validate_reader_id(cls, v):
        if not v or not v.startswith('rdr_'):
            raise ValueError('Invalid reader ID format')
        return v
    
    class Config:
        env_file = ".env"
        case_sensitive = False

# Global settings instance
settings = Settings()

def get_settings() -> Settings:
    """Get application settings"""
    return settings
