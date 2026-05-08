from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List
import json


class Settings(BaseSettings):
    # App
    APP_NAME: str = "Munch"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False

    # Database
    # Pydantic will look for an environment variable named DATABASE_URL
    DATABASE_URL: str = "postgresql+asyncpg://munch_user:munch_password@localhost:5432/munch_db"
    DATABASE_URL_SYNC: str = "postgresql://munch_user:munch_password@localhost:5432/munch_db"

    # Security
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # University Auth
    ALLOWED_EMAIL_DOMAIN: str = "university.edu"

    # Redis
    REDIS_URL: str = "redis://localhost:6379"

    # CORS
    CORS_ORIGINS: str = '["http://localhost:3000","http://localhost:5173"]'

    # AI
    MIN_ORDERS_FOR_RECOMMENDATION: int = 3
    RECOMMENDATION_CACHE_TTL: int = 300

    @property
    def cors_origins_list(self) -> List[str]:
        try:
            return json.loads(self.CORS_ORIGINS)
        except json.JSONDecodeError:
            return [self.CORS_ORIGINS]

    # Pydantic V2 uses SettingsConfigDict instead of class Config
    model_config = SettingsConfigDict(
        env_file=".env", 
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore" # Good practice to ignore extra env vars on Render
    )


settings = Settings()