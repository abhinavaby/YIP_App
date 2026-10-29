import secrets

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "sqlite:///./foodbridge.db"
    secret_key: str = secrets.token_urlsafe(48)
    access_token_minutes: int = 60
    ollama_url: str = "http://localhost:11434"
    ollama_text_model: str = "llama3:8b"
    ollama_vision_model: str = "moondream"
    cors_origins: str = "http://localhost:5173"
    upload_dir: str = "./uploads"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


settings = Settings()
