from ezrules.backend.api_v2.main import build_cors_middleware_kwargs
from ezrules.settings import Settings


def make_settings(**overrides) -> Settings:
    return Settings(
        _env_file=None,
        DB_ENDPOINT="postgresql://postgres:root@localhost:5432/test",
        APP_SECRET="test-secret",
        **overrides,
    )


def test_build_cors_defaults_to_same_origin_only() -> None:
    settings = make_settings()

    kwargs = build_cors_middleware_kwargs(settings)

    assert kwargs["allow_origins"] == []
    assert kwargs["allow_origin_regex"] is None


def test_build_cors_uses_explicit_allowed_origins() -> None:
    settings = make_settings(CORS_ALLOWED_ORIGINS="https://app.example.com, https://ops.example.com ")

    kwargs = build_cors_middleware_kwargs(settings)

    assert kwargs["allow_origins"] == ["https://app.example.com", "https://ops.example.com"]
    assert kwargs["allow_origin_regex"] is None


def test_build_cors_uses_explicit_regex_override() -> None:
    settings = make_settings(CORS_ALLOW_ORIGIN_REGEX=r"^https://.*\.example\.com$")

    kwargs = build_cors_middleware_kwargs(settings)

    assert kwargs["allow_origins"] == []
    assert kwargs["allow_origin_regex"] == r"^https://.*\.example\.com$"
