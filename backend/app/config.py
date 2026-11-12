import os
from pydantic_settings import BaseSettings
from pydantic import field_validator
from typing import Optional

# Resolve the absolute path to the .env file in the parent folder (backend/.env)
current_dir = os.path.dirname(os.path.abspath(__file__))
env_file_path = os.path.abspath(os.path.join(current_dir, "..", ".env"))

class Settings(BaseSettings):
    # MySQL Connection Settings — DB 1 (Commercial / Pharma Command Centre)
    MYSQL_HOST: str = "localhost"
    MYSQL_PORT: int = 3306
    MYSQL_USER: str = ""
    MYSQL_PASSWORD: str = ""
    MYSQL_DATABASE: str = ""

    # MySQL Connection Settings — DB 2 (GPO Customer Roster Validation)
    GPO_MYSQL_HOST: str = ""
    GPO_MYSQL_PORT: int = 3306
    GPO_MYSQL_USER: str = ""
    GPO_MYSQL_PASSWORD: str = ""
    GPO_MYSQL_DATABASE: str = ""

    # MySQL Connection Settings — DB 3 (DataSure Database)
    DataSure_MYSQL_HOST: str = ""
    DataSure_MYSQL_PORT: int = 3306
    DataSure_MYSQL_USER: str = ""
    DataSure_MYSQL_PASSWORD: str = ""
    DataSure_MYSQL_DATABASE: str = "data_sure"

    # MySQL Connection Settings — DB 4 (PriceAssure Database)
    PriceAssure_MYSQL_HOST: str = ""
    PriceAssure_MYSQL_PORT: int = 3306
    PriceAssure_MYSQL_USER: str = ""
    PriceAssure_MYSQL_PASSWORD: str = ""
    PriceAssure_MYSQL_DATABASE: str = "gp"

    # LLM Settings
    GROQ_API_KEY: Optional[str] = None
    GROQ_MODEL: str = "openai/gpt-oss-120b"
    CLAUDE_API_KEY: Optional[str] = None
    CLAUDE_MODEL: str = "claude-opus-5"

    # AWS Bedrock (Claude via Bedrock instead of direct Anthropic API)
    AWS_ACCESS_KEY_ID: Optional[str] = None
    AWS_SECRET_ACCESS_KEY: Optional[str] = None
    AWS_REGION: str = "ap-south-1"
    BEDROCK_CLAUDE_MODEL: str = "global.anthropic.claude-opus-5"

    # Salesforce Connection Settings (UC3)
    SF_USERNAME: str = ""
    SF_PASSWORD: str = ""
    SF_SECURITY_TOKEN: str = ""
    SF_DOMAIN: str = "login"
    SF_SESSION_ID: Optional[str] = None
    SF_INSTANCE_URL: Optional[str] = None

    # API Settings
    PORT: int = 8000
    HOST: str = "0.0.0.0"

    @field_validator(
        "MYSQL_HOST", "MYSQL_USER", "MYSQL_PASSWORD", "MYSQL_DATABASE",
        "GPO_MYSQL_HOST", "GPO_MYSQL_USER", "GPO_MYSQL_PASSWORD", "GPO_MYSQL_DATABASE",
        "DataSure_MYSQL_HOST", "DataSure_MYSQL_USER", "DataSure_MYSQL_PASSWORD", "DataSure_MYSQL_DATABASE",
        "PriceAssure_MYSQL_HOST", "PriceAssure_MYSQL_USER", "PriceAssure_MYSQL_PASSWORD", "PriceAssure_MYSQL_DATABASE",
        "GROQ_API_KEY", "GROQ_MODEL", "CLAUDE_API_KEY", "CLAUDE_MODEL", "HOST",
        "SF_USERNAME", "SF_PASSWORD", "SF_SECURITY_TOKEN", "SF_DOMAIN", "SF_SESSION_ID", "SF_INSTANCE_URL",
        "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_REGION", "BEDROCK_CLAUDE_MODEL",
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
        extra = "ignore"

settings = Settings()
