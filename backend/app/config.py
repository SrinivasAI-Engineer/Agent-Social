from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "dev"
    app_base_url: str = "http://localhost:8000"
    frontend_base_url: str = "http://localhost:5173"

    database_url: str = "sqlite:///./agentsocials.db"

    tokens_fernet_key: str = ""

    firecrawl_api_key: str = ""
    firecrawl_api_base: str = "https://api.firecrawl.dev"

    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"

    twitter_client_id: str = ""
    twitter_client_secret: str = ""
    twitter_redirect_uri: str = "http://localhost:8000/v1/oauth/twitter/callback"

    linkedin_client_id: str = ""
    linkedin_client_secret: str = ""
    linkedin_redirect_uri: str = "http://localhost:8000/v1/oauth/linkedin/callback"


settings = Settings()

