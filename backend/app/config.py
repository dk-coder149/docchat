"""App settings. Saari values environment variables / .env file se aati hain.

API keys aur secrets kabhi code mein nahi likhte.
"""
from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

LLM_PROVIDERS = ("groq", "anthropic", "openai_compatible")


class Settings(BaseSettings):
    # backend/.env ya project root ki .env, dono padhi jati hain
    model_config = SettingsConfigDict(env_file=(".env", "../.env"), extra="ignore")

    # ---- required: ye na mile to app start hote hi error dega ----
    secret_key: str  # JWT sign karne ke liye

    # ---- database ----
    database_url: str = "sqlite:///./docchat.db"

    # ---- auth ----
    access_token_minutes: int = 60

    # ---- LLM ----
    # groq (default) | anthropic | openai_compatible (Gemini, Ollama, OpenRouter, Cerebras...)
    llm_provider: str = "groq"
    llm_model: str = ""  # khali = provider ka default model
    llm_max_tokens: int = 1500
    groq_api_key: str = ""
    anthropic_api_key: str = ""
    # sirf openai_compatible ke liye:
    llm_base_url: str = ""
    llm_api_key: str = ""

    # ---- vector DB (ChromaDB) ----
    chroma_path: str = "./chroma_db"

    # ---- RAG tuning ----
    chunk_size: int = 800
    chunk_overlap: int = 100
    top_k: int = 4
    history_messages: int = 4  # LLM ko pichle kitne messages dikhane hain (kam = kam tokens)

    # ---- uploads ----
    max_upload_mb: int = 10

    # ---- CORS: comma-separated frontend addresses ----
    cors_origins: str = "http://localhost:3000"

    # ---- rate limits ----
    rate_limit_chat: str = "20/minute"
    rate_limit_auth: str = "10/minute"

    @field_validator("secret_key")
    @classmethod
    def secret_key_must_be_long(cls, value: str) -> str:
        if len(value) < 32:
            raise ValueError(
                "SECRET_KEY must be at least 32 characters. Generate one with: "
                'python -c "import secrets; print(secrets.token_hex(32))"'
            )
        return value

    @field_validator("llm_provider")
    @classmethod
    def provider_must_be_known(cls, value: str) -> str:
        value = value.strip().lower()
        if value not in LLM_PROVIDERS:
            raise ValueError(f"LLM_PROVIDER must be one of: {', '.join(LLM_PROVIDERS)}")
        return value

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
