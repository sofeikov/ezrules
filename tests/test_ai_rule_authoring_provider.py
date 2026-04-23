import io
import json
import urllib.error

import pytest

from ezrules.backend.ai_rule_authoring import AIRuleAuthoringProviderError, OpenAIRuleAuthoringProvider


class _MockHTTPResponse:
    def __init__(self, payload: dict) -> None:
        self._payload = json.dumps(payload).encode("utf-8")

    def read(self) -> bytes:
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False


def test_openai_provider_returns_message_content(monkeypatch):
    provider = OpenAIRuleAuthoringProvider(
        base_url="http://localhost:9999/v1",
        model_name="demo-model",
        api_key="test-key",
        timeout_seconds=5,
    )

    def _urlopen(request, timeout):
        assert request.full_url == "http://localhost:9999/v1/chat/completions"
        assert timeout == 5
        body = json.loads(request.data.decode("utf-8"))
        assert body["model"] == "demo-model"
        return _MockHTTPResponse(
            {"choices": [{"message": {"content": '{"draft_logic":"return !HOLD","line_explanations":[]}'}}]}
        )

    monkeypatch.setattr("urllib.request.urlopen", _urlopen)

    response = provider.complete(system_prompt="system", user_prompt="user")

    assert response == '{"draft_logic":"return !HOLD","line_explanations":[]}'


def test_openai_provider_joins_content_parts(monkeypatch):
    provider = OpenAIRuleAuthoringProvider(
        base_url="http://localhost:9999/v1",
        model_name="demo-model",
        api_key=None,
        timeout_seconds=5,
    )

    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda request, timeout: _MockHTTPResponse(
            {
                "choices": [
                    {
                        "message": {
                            "content": [
                                {"type": "text", "text": '{"draft_logic":"return !HOLD",'},
                                {"type": "text", "text": '"line_explanations":[]}'},
                            ]
                        }
                    }
                ]
            }
        ),
    )

    response = provider.complete(system_prompt="system", user_prompt="user")

    assert response == '{"draft_logic":"return !HOLD",\n"line_explanations":[]}'


def test_openai_provider_raises_on_http_error(monkeypatch):
    provider = OpenAIRuleAuthoringProvider(
        base_url="http://localhost:9999/v1",
        model_name="demo-model",
        api_key=None,
        timeout_seconds=5,
    )

    def _raise_http_error(request, timeout):
        _ = request
        _ = timeout
        raise urllib.error.HTTPError(
            url="http://localhost:9999/v1/chat/completions",
            code=500,
            msg="Server Error",
            hdrs=None,
            fp=io.BytesIO(b'{"error":"boom"}'),
        )

    monkeypatch.setattr("urllib.request.urlopen", _raise_http_error)

    with pytest.raises(AIRuleAuthoringProviderError, match="HTTP 500"):
        provider.complete(system_prompt="system", user_prompt="user")
