from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="EZRULES_", env_file="settings.env")

    DB_ENDPOINT: str
    APP_SECRET: str
    ORG_ID: int
    EVALUATOR_ENDPOINT: str | None = "localhost:9999"
    TESTING: bool | None = False


app_settings = Settings()  # type: ignore[missing-argument]
