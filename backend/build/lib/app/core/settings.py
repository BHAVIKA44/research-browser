from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Research Browser"
    env: str = "dev"
    debug: bool = False
    database_url: str = "postgresql+asyncpg://postgres:postgres@db:5432/research_browser"
    cors_origins: list[str] = ["http://localhost:5173"]
    request_timeout_seconds: int = 90
    semantic_cache_enabled: bool = False

    openai_api_key: str | None = None
    groq_api_key: str | None = None
    ollama_base_url: str = "http://ollama:11434"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()
