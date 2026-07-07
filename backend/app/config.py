import os
from pydantic_settings import BaseSettings
from pydantic import field_validator
from typing import Optional

# Resolve the absolute path to the .env file in the parent folder (backend/.env)
current_dir = os.path.dirname(os.path.abspath(__file__))
env_file_path = os.path.abspath(os.path.join(current_dir, "..", ".env"))

class Settings(BaseSettings):
    # Database Settings
    DB_HOST: str = "localhost"
    DB_PORT: int = 3306
    DB_USER: str = "mcp_readonly"
    DB_PASSWORD: str = "mcp_secure_pass123"
    DB_NAME: str = "mcp_poc_db"

    # LLM Settings
    GEMINI_API_KEY: Optional[str] = None
    OLLAMA_MODEL: str = "qwen2.5-coder:7b"
    OLLAMA_HOST: str = "http://localhost:11434"

    # API Settings
    PORT: int = 8000
    HOST: str = "0.0.0.0"

    @field_validator("DB_HOST", "DB_USER", "DB_PASSWORD", "DB_NAME", "GEMINI_API_KEY", "OLLAMA_MODEL", "OLLAMA_HOST", "HOST", mode="before")
    @classmethod
    def strip_quotes(cls, v):
        if isinstance(v, str):
            return v.strip("'\"")
        return v

    class Config:
        env_file = env_file_path
        env_file_encoding = "utf-8"

settings = Settings()
