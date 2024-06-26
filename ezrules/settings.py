from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="EZRULES_", env_file="settings.env")

    DB_ENDPOINT: str
    APP_SECRET: str
    ORG_ID: int
    EVALUATOR_ENDPOINT: Optional[str] = "localhost:9999"
    TESTING: Optional[bool] = False


app_settings = Settings()
