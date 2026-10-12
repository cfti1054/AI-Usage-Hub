from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/ai_usage_hub"
    jwt_secret: str
    jwt_expire_minutes: int = 60 * 24 * 7
    # Fernet 키 — 외부 서비스 API 키를 DB에 암호화 저장할 때 사용
    credentials_key: str
    admin_email: str | None = None
    admin_password: str | None = None
    scheduler_enabled: bool = True
    # 한국수출입은행 환율 API 인증키 (없으면 Frankfurter/ECB 기준환율만 사용)
    koreaexim_api_key: str | None = None
    fx_refresh_hours: int = 6

    @field_validator("database_url")
    @classmethod
    def use_psycopg_driver(cls, v: str) -> str:
        # Railway는 postgresql:// 형식으로 주입하므로 psycopg3 드라이버를 명시한다
        for prefix in ("postgres://", "postgresql://"):
            if v.startswith(prefix):
                return "postgresql+psycopg://" + v[len(prefix):]
        return v


@lru_cache
def get_settings() -> Settings:
    return Settings()
