from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="EZRULES_", env_file="settings.env", extra="ignore")

    DB_ENDPOINT: str
    APP_SECRET: str
    EVALUATOR_ENDPOINT: str | None = "localhost:9999"
    CELERY_BROKER_URL: str = "redis://localhost:6379"
    TESTING: bool | None = False
    MAX_BODY_SIZE_KB: int = 1024
    CORS_ALLOWED_ORIGINS: str | None = None
    CORS_ALLOW_ORIGIN_REGEX: str | None = None
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
    OBSERVATION_QUEUE_REDIS_URL: str | None = None
    OBSERVATION_QUEUE_KEY: str = "ezrules:field_observation_queue"
    OBSERVATION_QUEUE_LOCK_KEY: str = "ezrules:field_observation_queue:lock"
    OBSERVATION_QUEUE_DRAIN_BATCH_SIZE: int = 1000
    OBSERVATION_QUEUE_MAX_BATCHES_PER_DRAIN: int = 10
    OBSERVATION_QUEUE_LOCK_TIMEOUT_SECONDS: int = 30
    OBSERVATION_QUEUE_DRAIN_INTERVAL_SECONDS: int = 5
    SHADOW_EVALUATION_QUEUE_REDIS_URL: str | None = None
    SHADOW_EVALUATION_QUEUE_KEY: str = "ezrules:shadow_evaluation_queue"
    SHADOW_EVALUATION_QUEUE_LOCK_KEY: str = "ezrules:shadow_evaluation_queue:lock"
    SHADOW_EVALUATION_QUEUE_DRAIN_BATCH_SIZE: int = 100
    SHADOW_EVALUATION_QUEUE_MAX_BATCHES_PER_DRAIN: int = 10
    SHADOW_EVALUATION_QUEUE_LOCK_TIMEOUT_SECONDS: int = 30
    SHADOW_EVALUATION_QUEUE_DRAIN_INTERVAL_SECONDS: int = 5

    @property
    def cors_allowed_origins(self) -> list[str]:
        raw_value = self.CORS_ALLOWED_ORIGINS
        if not raw_value:
            return []
        return [origin.strip() for origin in raw_value.split(",") if origin.strip()]


app_settings = Settings()  # type: ignore[missing-argument]
