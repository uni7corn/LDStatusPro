"""Global application settings via pydantic-settings."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Server
    host: str = "0.0.0.0"
    port: int = 8790
    environment: Literal["development", "staging", "production"] = "development"
    debug: bool = False

    # Database paths
    ldsp_database_path: str = "./data/ldsp_data.db"
    store_database_path: str = "./data/ld_store.db"
    vector_store_path: str = "./data/vector_store"

    @property
    def ldsp_database_url(self) -> str:
        return f"sqlite+aiosqlite:///{self.ldsp_database_path}"

    @property
    def store_database_url(self) -> str:
        return f"sqlite+aiosqlite:///{self.store_database_path}"

    @property
    def vector_database_url(self) -> str:
        return f"sqlite+aiosqlite:///{self.vector_store_path}"

    # JWT Auth
    jwt_secret_key: str = "change-me"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 1440

    # OAuth
    oauth_client_id: str = ""
    oauth_client_secret: str = ""
    idcflare_client_id: str = ""
    idcflare_client_secret: str = ""
    registration_paused: bool = False
    api_base_url: str = ""
    worker_url: str = ""

    # Super Admin (initial)
    super_admin_username: str = "admin"
    super_admin_password: str = "changeme"

    # OpenAI / Primary LLM
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    openai_base_url: str = "https://api.openai.com/v1"

    # Fallback LLM
    fallback_provider: str = "siliconflow"
    fallback_api_key: str = ""
    fallback_model: str = "Qwen/Qwen2.5-72B-Instruct"
    fallback_base_url: str = "https://api.siliconflow.cn/v1"

    # Fallback chain
    fallback_chain: list[str] = Field(default_factory=lambda: ["openai", "siliconflow"])

    @property
    def fallback_chain_list(self) -> list[str]:
        raw = "openai,siliconflow"  # fallback default
        return [p.strip() for p in raw.split(",") if p.strip()]

    # Embedding
    embedding_provider: str = "openai"
    embedding_model: str = "text-embedding-3-small"

    # RAG
    rag_top_k: int = 5
    rag_similarity_threshold: float = 0.75
    vector_store_type: str = "chroma"

    # Rate limits
    llm_rate_limit_per_minute: int = 60
    llm_daily_token_budget: int = 1_000_000
    llm_max_cost_per_day: float = 50.00

    # Logging
    log_level: str = "debug"
    structured_log: bool = False

    # Site configuration
    supported_sites: str = "linux.do,idcflare.com"
    api_version: str = "v1"

    # Shop maintenance mode
    shop_maintenance_mode: str = ""
    shop_maintenance_title: str = ""
    shop_maintenance_message: str = ""
    shop_maintenance_reason: str = ""
    shop_maintenance_eta: str = ""
    shop_maintenance_status_url: str = ""

    # Internal service auth
    admin_secret: str = ""
    store_internal_token: str = ""
    gateway_internal_token: str = ""
    tg_bot_internal_key: str = ""
    tg_bot_internal_token: str = ""
    image_ai_internal_key: str = ""
    backend_image_internal_key: str = ""
    backend_firewall_secret: str = ""
    encryption_key: str = ""
    tg_bot_webhook_secret: str = ""
    telegram_webhook_secret: str = ""


settings = Settings()
