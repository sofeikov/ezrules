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


app_settings = Settings()  # type: ignore[missing-argument]
