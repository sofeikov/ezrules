from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="EZRULES_", env_file="settings.env")

    DB_ENDPOINT: str
    APP_SECRET: str
    ORG_ID: int
    EVALUATOR_ENDPOINT: str | None = "localhost:9999"
    CELERY_BROKER_URL: str = "redis://localhost:6379"
    TESTING: bool | None = False
    MAX_BODY_SIZE_KB: int = 1024
    SMTP_HOST: str | None = None
    SMTP_PORT: int = 587
    SMTP_USER: str | None = None
    SMTP_PASSWORD: str | None = None
    FROM_EMAIL: str | None = None
    APP_BASE_URL: str = "http://localhost:4200"
    INVITE_TOKEN_EXPIRY_HOURS: int = 72
    PASSWORD_RESET_TOKEN_EXPIRY_HOURS: int = 1
    RULE_QUALITY_LOOKBACK_DAYS: int = 30
    RULE_QUALITY_REPORT_SYNC_FALLBACK: bool = True


app_settings = Settings()  # type: ignore[missing-argument]
