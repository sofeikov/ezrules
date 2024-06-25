from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="EZRULES_", env_file="settings.env")

    DB_ENDPOINT: str
    APP_SECRET: str
    ORG_ID: int
    EVALUATOR_ENDPOINT: Optional[str] = "localhost:9999"
    TESTING: Optional[bool] = False
    CELERY_RESULT_BACKEND: str = "db+postgresql://postgres:root@localhost:5432/celery"


app_settings = Settings()
