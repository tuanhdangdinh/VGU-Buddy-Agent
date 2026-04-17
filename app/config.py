import os
from dataclasses import dataclass, field
from dotenv import load_dotenv

load_dotenv(".env.local")
load_dotenv(".env")


@dataclass
class Settings:
    host: str = field(default_factory=lambda: os.getenv("HOST", "0.0.0.0"))
    port: int = field(default_factory=lambda: int(os.getenv("PORT", "8000")))
    environment: str = field(default_factory=lambda: os.getenv("ENVIRONMENT", "development"))
    debug: bool = field(default_factory=lambda: os.getenv("DEBUG", "false").lower() == "true")

    app_name: str = field(default_factory=lambda: os.getenv("APP_NAME", "Study Buddy - VGU"))
    app_version: str = field(default_factory=lambda: os.getenv("APP_VERSION", "1.0.0"))

    agent_api_key: str = field(default_factory=lambda: os.getenv("AGENT_API_KEY", "dev-key-change-me"))
    allowed_origins: list = field(default_factory=lambda: os.getenv("ALLOWED_ORIGINS", "*").split(","))

    rate_limit_per_minute: int = field(default_factory=lambda: int(os.getenv("RATE_LIMIT_PER_MINUTE", "10")))
    monthly_budget_usd: float = field(default_factory=lambda: float(os.getenv("MONTHLY_BUDGET_USD", "10.0")))

    redis_url: str = field(default_factory=lambda: os.getenv("REDIS_URL", ""))

    # Gemini / LLM
    gemini_api_key: str = field(default_factory=lambda: os.getenv("GEMINI_API_KEY", ""))
    llm_model: str = field(default_factory=lambda: os.getenv("LLM_MODEL", "gemini-2.0-flash"))


settings = Settings()
