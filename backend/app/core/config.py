import os
from pydantic_settings import BaseSettings
from pydantic import Field

class Settings(BaseSettings):
    PROJECT_NAME: str = "AtlasLM"
    API_V1_STR: str = "/api/v1"
    
    # Database
    DATABASE_URL: str = Field(
        default="postgresql://atlaslm:atlaspass@localhost:5435/atlaslm_db",
        env="DATABASE_URL"
    )
    REDIS_URL: str = Field(
        default="redis://redis:6379/0",
        env="REDIS_URL"
    )
    
    # JWT Fallback Settings
    JWT_SECRET: str = Field(..., env="JWT_SECRET")  # required, no default
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 days
    
    # Supabase (mainly for frontend, but backend can verify tokens if needed)
    SUPABASE_URL: str = Field(default="", env="SUPABASE_URL")
    SUPABASE_ANON_KEY: str = Field(default="", env="SUPABASE_ANON_KEY")
    
    # Model APIs
    LANGDOCK_API_KEY: str = Field(default="", env="LANGDOCK_API_KEY")
    LANGDOCK_API_CODE: str = Field(default="", env="LANGDOCK_API_CODE")
    LANGDOCK_ENDPOINT_URL: str = Field(
        default="https://api.langdock.com/openai/eu/v1",
        env="LANGDOCK_ENDPOINT_URL"
    )
    LANGDOCK_WORKSPACE_ID: str = Field(default="", env="LANGDOCK_WORKSPACE_ID")
    LANGDOCK_MODEL: str = Field(default="gpt-5-mini", env="LANGDOCK_MODEL")
    MODEL: str = Field(default="", env="MODEL")
    
    BLACKBOX_API_KEY: str = Field(default="", env="BLACKBOX_API_KEY")
    
    OPENROUTER_API_KEY: str = Field(default="", env="OPENROUTER_API_KEY")
    OPENROUTER_ENDPOINT_URL: str = Field(
        default="https://openrouter.ai/api/v1",
        env="OPENROUTER_ENDPOINT_URL"
    )
    OPENROUTER_MODEL: str = Field(default="openrouter/auto", env="OPENROUTER_MODEL")
    
    OLLAMA_ENDPOINT_URL: str = Field(
        default="http://localhost:11434",
        env="OLLAMA_ENDPOINT_URL"
    )
    
    OPENAI_API_KEY: str = Field(default="", env="OPENAI_API_KEY")
    GEMINI_API_KEY: str = Field(default="", env="GEMINI_API_KEY")
    
    # RAG Settings
    DEFAULT_CHUNK_SIZE: int = 800
    DEFAULT_CHUNK_OVERLAP: int = 150
    
    # Active engine routing (server-side only; never exposed to clients)
    ATLAS_ACTIVE_PROVIDER: str = Field(default="langdock", env="ATLAS_ACTIVE_PROVIDER")
    
    # Billing & Supabase Admin Gating (Patch 008)
    STRIPE_WEBHOOK_SECRET: str = Field(default="", env="STRIPE_WEBHOOK_SECRET")
    SUPABASE_SERVICE_ROLE_KEY: str = Field(default="", env="SUPABASE_SERVICE_ROLE_KEY")

    class Config:
        case_sensitive = True
        env_file = None if os.getenv("VERCEL") else ".env"
        extra = "ignore"

settings = Settings()
