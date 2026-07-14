import os
from pydantic_settings import BaseSettings
from pydantic import field_validator
from typing import Optional

# Resolve the absolute path to the .env file in the parent folder (backend/.env)
current_dir = os.path.dirname(os.path.abspath(__file__))
env_file_path = os.path.abspath(os.path.join(current_dir, "..", ".env"))

class Settings(BaseSettings):
    # Salesforce Connection Settings
    SF_USERNAME: str = ""
    SF_PASSWORD: str = ""
    SF_SECURITY_TOKEN: str = ""
    SF_DOMAIN: str = "login"  # 'login' for production, 'test' for sandbox

    # LLM Settings
    GEMINI_API_KEY: Optional[str] = None
    OLLAMA_MODEL: str = "qwen2.5-coder:7b"
    OLLAMA_HOST: str = "http://localhost:11434"

    # API Settings
    PORT: int = 8000
    HOST: str = "0.0.0.0"

    @field_validator(
        "SF_USERNAME", "SF_PASSWORD", "SF_SECURITY_TOKEN", "SF_DOMAIN",
        "GEMINI_API_KEY", "OLLAMA_MODEL", "OLLAMA_HOST", "HOST",
        mode="before"
    )
    @classmethod
    def strip_quotes(cls, v):
        if isinstance(v, str):
            return v.strip("'\"")
        return v

    class Config:
        env_file = env_file_path
        env_file_encoding = "utf-8"

settings = Settings()
