"""Unit tests for scripts/bombard_evaluator.py helpers."""

import importlib
from types import SimpleNamespace


bombard = importlib.import_module("scripts.bombard_evaluator")


class _DummyResponse:
    def __init__(self, status_code: int, payload: dict | None = None, text: str = ""):
        self.status_code = status_code
        self._payload = payload or {}
        self._text = text

    def json(self) -> dict:
        return self._payload

    @property
    def text(self) -> str:
        return self._text


def test_build_evaluate_headers_prefers_token():
    headers = bombard.build_evaluate_headers("token-123", "api-key-123")
    assert headers == {"Authorization": "Bearer token-123"}


def test_build_evaluate_headers_uses_api_key_when_no_token():
    headers = bombard.build_evaluate_headers(None, "api-key-123")
    assert headers == {"X-API-Key": "api-key-123"}


def test_pick_fraud_event_ids_rate_zero():
    selected = bombard.pick_fraud_event_ids(["e1", "e2"], fraud_rate=0.0)
    assert selected == []


def test_pick_fraud_event_ids_uses_probability(monkeypatch):
    draws = iter([0.005, 0.5, 0.009, 0.2])

    def fake_uniform(_a: float, _b: float) -> float:
        return next(draws)

    monkeypatch.setattr(bombard, "uniform", fake_uniform)

    selected = bombard.pick_fraud_event_ids(["e1", "e2", "e3", "e4"], fraud_rate=0.01)
    assert selected == ["e1", "e3"]


def test_ensure_label_exists_returns_true_when_label_already_exists(monkeypatch):
    def fake_get(*_args, **_kwargs):
        return _DummyResponse(200, payload={"labels": [{"label": "FRAUD"}]})

    def fake_post(*_args, **_kwargs):
        raise AssertionError("POST /labels should not be called when label already exists")

    monkeypatch.setattr(bombard.httpx, "get", fake_get)
    monkeypatch.setattr(bombard.httpx, "post", fake_post)

    assert bombard.ensure_label_exists("http://localhost:8888", "FRAUD", "token") is True


def test_ensure_label_exists_creates_missing_label(monkeypatch):
    calls: dict[str, int] = {"post": 0}

    def fake_get(*_args, **_kwargs):
        return _DummyResponse(200, payload={"labels": [{"label": "NORMAL"}]})

    def fake_post(*_args, **kwargs):
        calls["post"] += 1
        assert kwargs["json"] == {"label_name": "FRAUD"}
        return _DummyResponse(201)

    monkeypatch.setattr(bombard.httpx, "get", fake_get)
    monkeypatch.setattr(bombard.httpx, "post", fake_post)

    assert bombard.ensure_label_exists("http://localhost:8888", "FRAUD", "token") is True
    assert calls["post"] == 1


def test_run_finite_labels_successful_transactions(monkeypatch):
    marked: dict[str, object] = {}
    events = [
        {"transaction_id": "txn-1", "effective_at": 1700000001, "event_data": {"amount": 100}},
        {"transaction_id": "txn-2", "effective_at": 1700000002, "event_data": {"amount": 200}},
    ]

    monkeypatch.setattr(bombard, "randint", lambda _lower, _upper: 2)
    monkeypatch.setattr(bombard, "build_bombard_events", lambda n: events[:n])
    monkeypatch.setattr(
        bombard,
        "send_one",
        lambda _url, event, _headers: {
            "ok": True,
            "status": 200,
            "elapsed": 0.01,
            "transaction_id": event["transaction_id"],
            "outcome_set": ["HOLD"],
        },
    )
    monkeypatch.setattr(bombard, "pick_fraud_event_ids", lambda transaction_ids, _rate: transaction_ids)

    def fake_mark_events(url, transaction_ids, label_name, token, concurrency):  # noqa: ANN001
        marked["url"] = url
        marked["transaction_ids"] = transaction_ids
        marked["label_name"] = label_name
        marked["token"] = token
        marked["concurrency"] = concurrency
        return [{"ok": True, "status": 200, "elapsed": 0.01, "transaction_id": item} for item in transaction_ids]

    monkeypatch.setattr(bombard, "mark_events", fake_mark_events)
    monkeypatch.setattr(bombard, "print_summary", lambda *_args, **_kwargs: None)

    args = SimpleNamespace(
        n=2,
        url="http://localhost:8888",
        concurrency=1,
        token="token",
        fraud_rate=1.0,
        fraud_label="FRAUD",
    )

    bombard.run_finite(args, evaluate_headers={"Authorization": "Bearer token"}, label_enabled=True)

    assert marked == {
        "url": "http://localhost:8888",
        "transaction_ids": ["txn-1", "txn-2"],
        "label_name": "FRAUD",
        "token": "token",
        "concurrency": 1,
    }
