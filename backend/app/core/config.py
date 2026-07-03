from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://outreach:outreach@localhost:5432/outreach"
    redis_url: str = "redis://localhost:6379/0"
    secret_key: str = "dev-only-secret"
    encryption_key: str = ""  # base64 32 bytes，AES-GCM 加密 OAuth/BYOK/SMTP 凭据

    # 免费数据源（留空 = 适配器停用）
    google_pse_api_key: str = ""
    google_pse_cx: str = ""
    google_maps_api_key: str = ""
    companies_house_api_key: str = ""

    reacher_base_url: str = ""

    # 对外基址（退订链接等）与 OAuth 应用凭据（Gmail / Microsoft Graph 通道）
    app_base_url: str = "http://localhost:8000"
    google_client_id: str = ""
    google_client_secret: str = ""
    ms_client_id: str = ""
    ms_client_secret: str = ""

    # LLM 平台代付模式；BYOK 密钥存库内加密，见 ai_gateway
    anthropic_api_key: str = ""
    llm_strong_model: str = "claude-sonnet-5"
    llm_cheap_model: str = "claude-haiku-4-5-20251001"

    # 发信护栏（免费版默认，见 docs/design/04 §4）
    send_daily_limit_healthy: int = 20
    send_daily_limit_warming: int = 5
    bounce_rate_throttle: float = 0.03
    complaint_rate_pause: float = 0.001

    access_token_ttl_hours: int = 72


@lru_cache
def get_settings() -> Settings:
    return Settings()
