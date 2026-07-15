from typing import Any


class ReliableRedisQueue:
    """Reserve Redis list items until their database side effects are durable."""

    def __init__(self, client: Any, ready_key: str):
        self.client = client
        self.ready_key = ready_key
        self.processing_key = f"{ready_key}:processing"
        self._supports_processing = all(
            callable(getattr(client, command, None)) for command in ("lmove", "lrem", "rpoplpush")
        )

    def recover(self) -> int:
        """Return entries orphaned by an interrupted consumer to the ready list."""
        if not self._supports_processing:
            return 0

        recovered = 0
        while self.client.lmove(self.processing_key, self.ready_key, "LEFT", "RIGHT") is not None:
            recovered += 1
        return recovered

    def reserve(self, limit: int) -> list[str]:
        if not self._supports_processing:
            raw_batch = self.client.rpop(self.ready_key, limit)
            if raw_batch is None:
                return []
            return raw_batch if isinstance(raw_batch, list) else [raw_batch]

        payloads: list[str] = []
        for _ in range(limit):
            payload = self.client.rpoplpush(self.ready_key, self.processing_key)
            if payload is None:
                break
            payloads.append(str(payload))
        return payloads

    def acknowledge(self, payloads: list[str]) -> None:
        if not self._supports_processing:
            return
        for payload in payloads:
            self.client.lrem(self.processing_key, 1, payload)

    def restore(self, payloads: list[str]) -> None:
        if not payloads:
            return
        if self._supports_processing:
            self.recover()
            return
        self.client.rpush(self.ready_key, *reversed(payloads))
