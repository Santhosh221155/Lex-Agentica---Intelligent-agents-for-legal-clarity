try:
    # pydantic v2+ moves BaseSettings to pydantic-settings package
    from pydantic_settings import BaseSettings
    from pydantic import Field, AnyHttpUrl
except Exception:
    from pydantic import BaseSettings, Field, AnyHttpUrl
from typing import Optional


class Settings(BaseSettings):
    PROJECT_NAME: str = "Enterprise Agentic RAG Platform"
    DEBUG: bool = False

    DATABASE_URL: str = Field(..., env="DATABASE_URL")
    REDIS_URL: str = Field("redis://localhost:6379/0", env="REDIS_URL")
    QDRANT_URL: Optional[AnyHttpUrl] = Field(None, env="QDRANT_URL")

    SECRET_KEY: str = Field(..., env="SECRET_KEY")
    ALGORITHM: str = Field("HS256", env="ALGORITHM")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(60, env="ACCESS_TOKEN_EXPIRE_MINUTES")

    # Model endpoints (placeholders)
    EMBEDDING_MODEL: str = Field("bge-m3", env="EMBEDDING_MODEL")
    RERANKER_MODEL: str = Field("bge-reranker-large", env="RERANKER_MODEL")
    PRIMARY_LLM: str = Field("gemini-2.5-pro", env="PRIMARY_LLM")

    class Config:
        env_file = "..\.env"
        env_file_encoding = 'utf-8'


settings = Settings()
