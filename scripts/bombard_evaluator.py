#!/usr/bin/env python3
"""
Bombard the evaluator endpoint with synthetic events.

Usage:
    uv run python scripts/bombard_evaluator.py --token <access-token>
    uv run python scripts/bombard_evaluator.py --n 200 --api-key <api-key>
    uv run python scripts/bombard_evaluator.py --continuous --token <access-token>
    uv run python scripts/bombard_evaluator.py --fraud-rate 0.01 --token <access-token>
"""

import argparse
import signal
import sys
import time
import uuid
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from random import randint, uniform

import httpx

DEFAULT_URL = "http://localhost:8888"
DEFAULT_N = 100
DEFAULT_CONCURRENCY = 1
DEFAULT_BATCH_SIZE = 10
DEFAULT_MAX_DELAY = 5.0
DEFAULT_FRAUD_RATE = 0.01
DEFAULT_FRAUD_LABEL = "FRAUD"

# Matches the test_attributes used by `uv run ezrules generate-random-data`
_ATTRS: dict = {
    "amount": float,
    "send_country": str,
    "receive_country": str,
    "score": float,
    "is_verified": int,
}


def random_event() -> dict:
    event_data = {}
    for attr, attr_type in _ATTRS.items():
        if attr_type is float:
            event_data[attr] = round(uniform(0, 1000), 2)
        elif attr_type is str:
            event_data[attr] = f"{attr}_value_{randint(1, 10)}"
        elif attr_type is int:
            event_data[attr] = randint(0, 1)

    return {
        "event_id": f"bombard_{uuid.uuid4().hex[:12]}",
        "event_timestamp": int(time.time()),
        "event_data": event_data,
    }


def build_evaluate_headers(token: str | None, api_key: str | None) -> dict[str, str]:
    """Build auth headers for /api/v2/evaluate."""
    if token:
        return {"Authorization": f"Bearer {token}"}
    if api_key:
        return {"X-API-Key": api_key}
    return {}


def pick_fraud_event_ids(event_ids: list[str], fraud_rate: float) -> list[str]:
    """Select events to mark as fraud using Bernoulli sampling."""
    if fraud_rate <= 0:
        return []
    return [event_id for event_id in event_ids if uniform(0, 1) < fraud_rate]


def ensure_label_exists(url: str, label_name: str, token: str) -> bool:
    """Ensure a label exists so mark-event calls do not fail."""
    headers = {"Authorization": f"Bearer {token}"}

    try:
        list_resp = httpx.get(f"{url}/api/v2/labels", headers=headers, timeout=10)
        if list_resp.status_code != 200:
            print(f"Warning: failed to list labels ({list_resp.status_code}); fraud labeling disabled.")
            return False

        existing = {item.get("label", "") for item in list_resp.json().get("labels", [])}
        if label_name in existing:
            return True

        create_resp = httpx.post(
            f"{url}/api/v2/labels",
            headers=headers,
            json={"label_name": label_name},
            timeout=10,
        )
        if create_resp.status_code in (200, 201):
            return True

        detail = create_resp.text.strip()
        print(
            f"Warning: failed to create label '{label_name}' ({create_resp.status_code}) {detail}; fraud labeling disabled."
        )
        return False
    except Exception as exc:
        print(f"Warning: could not ensure label '{label_name}' exists ({exc}); fraud labeling disabled.")
        return False


def send_one(url: str, event: dict, headers: dict[str, str]) -> dict:
    t0 = time.perf_counter()
    try:
        response = httpx.post(f"{url}/api/v2/evaluate", json=event, headers=headers, timeout=10)
        elapsed = time.perf_counter() - t0
        return {
            "ok": response.status_code == 200,
            "status": response.status_code,
            "elapsed": elapsed,
            "event_id": event["event_id"],
            "outcome_set": response.json().get("outcome_set", []) if response.status_code == 200 else [],
        }
    except Exception as exc:
        return {
            "ok": False,
            "status": -1,
            "elapsed": time.perf_counter() - t0,
            "event_id": event["event_id"],
            "outcome_set": [],
            "error": str(exc),
        }


def send_batch(url: str, batch: list[dict], concurrency: int, headers: dict[str, str]) -> list[dict]:
    results = []
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = {pool.submit(send_one, url, e, headers): e for e in batch}
        for future in as_completed(futures):
            results.append(future.result())
    return results


def mark_one(url: str, event_id: str, label_name: str, token: str) -> dict:
    """Mark a single event with a label through the labels API."""
    t0 = time.perf_counter()
    headers = {"Authorization": f"Bearer {token}"}
    payload = {"event_id": event_id, "label_name": label_name}

    try:
        response = httpx.post(f"{url}/api/v2/labels/mark-event", json=payload, headers=headers, timeout=10)
        return {
            "ok": response.status_code == 200,
            "status": response.status_code,
            "elapsed": time.perf_counter() - t0,
            "event_id": event_id,
        }
    except Exception as exc:
        return {
            "ok": False,
            "status": -1,
            "elapsed": time.perf_counter() - t0,
            "event_id": event_id,
            "error": str(exc),
        }


def mark_events(url: str, event_ids: list[str], label_name: str, token: str, concurrency: int) -> list[dict]:
    """Mark many events concurrently."""
    results = []
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = {pool.submit(mark_one, url, event_id, label_name, token): event_id for event_id in event_ids}
        for future in as_completed(futures):
            results.append(future.result())
    return results


def print_summary(
    results: list[dict],
    total_elapsed: float,
    label_results: list[dict] | None = None,
    label_name: str | None = None,
) -> None:
    ok = sum(1 for r in results if r["ok"])
    failed = len(results) - ok
    outcome_counter: Counter = Counter()
    for r in results:
        for o in r["outcome_set"]:
            outcome_counter[o] += 1

    print(f"\n\n{'=' * 50}")
    print(f"Results: {ok} ok, {failed} failed, {len(results)} total")
    print(f"Total time: {total_elapsed:.2f}s  ({len(results) / total_elapsed:.1f} req/s)")

    latencies = sorted(r["elapsed"] for r in results if r["ok"])
    if latencies:
        print(
            "Latency (ok): "
            f"min={latencies[0] * 1000:.0f}ms  "
            f"p50={latencies[len(latencies) // 2] * 1000:.0f}ms  "
            f"p95={latencies[int(len(latencies) * 0.95)] * 1000:.0f}ms  "
            f"max={latencies[-1] * 1000:.0f}ms"
        )

    if outcome_counter:
        print("\nOutcome distribution:")
        for outcome, count in outcome_counter.most_common():
            pct = count / ok * 100 if ok else 0
            print(f"  {outcome:<20} {count:>5}  ({pct:.1f}%)")
    else:
        print("\nNo outcomes returned (no active rules or failed authentication?)")

    if label_results is not None and label_name:
        label_ok = sum(1 for r in label_results if r["ok"])
        label_failed = len(label_results) - label_ok
        print(f"\n{label_name} labeling: {label_ok} ok, {label_failed} failed, {len(label_results)} attempted")
        if label_failed:
            print(f"First labeling failure: {next(r for r in label_results if not r['ok'])}")

    if failed:
        print(f"\nFirst evaluation failure: {next(r for r in results if not r['ok'])}")


def run_finite(args: argparse.Namespace, evaluate_headers: dict[str, str], label_enabled: bool) -> None:
    n = randint(1, args.n)
    events = [random_event() for _ in range(n)]
    print(f"Sending {n} events (random up to {args.n}) to {args.url} …\n")

    results = []
    t_start = time.perf_counter()

    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        futures = {pool.submit(send_one, args.url, e, evaluate_headers): e for e in events}
        for i, future in enumerate(as_completed(futures), 1):
            res = future.result()
            results.append(res)
            print("." if res["ok"] else "x", end="", flush=True)
            if i % 50 == 0:
                print(f"  {i}/{n}")

    label_results: list[dict] | None = None
    if label_enabled and args.token:
        successful_event_ids = [result["event_id"] for result in results if result["ok"]]
        label_targets = pick_fraud_event_ids(successful_event_ids, args.fraud_rate)
        if label_targets:
            print(f"\nLabeling {len(label_targets)} events as {args.fraud_label} …")
            label_results = mark_events(args.url, label_targets, args.fraud_label, args.token, args.concurrency)
        else:
            label_results = []

    print_summary(results, time.perf_counter() - t_start, label_results=label_results, label_name=args.fraud_label)


def run_continuous(args: argparse.Namespace, evaluate_headers: dict[str, str], label_enabled: bool) -> None:
    print(
        f"Continuous mode — batches of {args.batch_size} events, "
        f"random delay 0–{args.max_delay}s between batches. "
        "Ctrl-C to stop.\n"
    )

    all_results: list[dict] = []
    all_label_results: list[dict] | None = [] if label_enabled else None
    batch_num = 0
    t_start = time.perf_counter()

    def _stop(sig, frame):  # noqa: ANN001
        print_summary(
            all_results,
            time.perf_counter() - t_start,
            label_results=all_label_results,
            label_name=args.fraud_label if label_enabled else None,
        )
        sys.exit(0)

    signal.signal(signal.SIGINT, _stop)

    while True:
        batch_num += 1
        batch = [random_event() for _ in range(randint(1, args.batch_size))]
        results = send_batch(args.url, batch, args.concurrency, evaluate_headers)
        all_results.extend(results)

        batch_labels_ok = 0
        if label_enabled and args.token and all_label_results is not None:
            successful_event_ids = [result["event_id"] for result in results if result["ok"]]
            label_targets = pick_fraud_event_ids(successful_event_ids, args.fraud_rate)
            label_results = mark_events(args.url, label_targets, args.fraud_label, args.token, args.concurrency)
            batch_labels_ok = sum(1 for result in label_results if result["ok"])
            all_label_results.extend(label_results)

        ok = sum(1 for result in results if result["ok"])
        total = len(all_results)
        delay = uniform(0, args.max_delay)
        label_suffix = f"  fraud-labeled: {batch_labels_ok}" if label_enabled else ""
        print(
            f"Batch {batch_num:>4}  {ok}/{len(batch)} ok  (total sent: {total}){label_suffix}  sleeping {delay:.1f}s …",
            flush=True,
        )
        time.sleep(delay)


def main() -> None:
    parser = argparse.ArgumentParser(description="Bombard the ezrules evaluator with synthetic events.")
    parser.add_argument("--n", type=int, default=DEFAULT_N, help=f"Events to send in finite mode (default {DEFAULT_N})")
    parser.add_argument("--url", default=DEFAULT_URL, help=f"Base API URL (default {DEFAULT_URL})")
    parser.add_argument(
        "--concurrency",
        type=int,
        default=DEFAULT_CONCURRENCY,
        help=f"Parallel workers per batch (default {DEFAULT_CONCURRENCY})",
    )
    parser.add_argument("--continuous", action="store_true", help="Run forever in batches until Ctrl-C")
    parser.add_argument(
        "--batch-size",
        type=int,
        default=DEFAULT_BATCH_SIZE,
        help=f"Events per batch in continuous mode (default {DEFAULT_BATCH_SIZE})",
    )
    parser.add_argument(
        "--max-delay",
        type=float,
        default=DEFAULT_MAX_DELAY,
        help=f"Max random delay in seconds between batches (default {DEFAULT_MAX_DELAY})",
    )
    parser.add_argument("--token", help="Bearer token used for evaluate and labels endpoints")
    parser.add_argument("--api-key", help="X-API-Key value used for evaluate endpoint")
    parser.add_argument(
        "--fraud-rate",
        type=float,
        default=DEFAULT_FRAUD_RATE,
        help=f"Probability of labeling a successful event as fraud (default {DEFAULT_FRAUD_RATE})",
    )
    parser.add_argument(
        "--fraud-label",
        default=DEFAULT_FRAUD_LABEL,
        help=f"Label name used for fraud marking (default {DEFAULT_FRAUD_LABEL})",
    )
    args = parser.parse_args()

    if args.n < 1:
        parser.error("--n must be >= 1")
    if args.batch_size < 1:
        parser.error("--batch-size must be >= 1")
    if args.concurrency < 1:
        parser.error("--concurrency must be >= 1")
    if args.fraud_rate < 0 or args.fraud_rate > 1:
        parser.error("--fraud-rate must be between 0 and 1")
    if not args.token and not args.api_key:
        parser.error("Provide either --token or --api-key for evaluate endpoint authentication")

    args.fraud_label = args.fraud_label.strip().upper()

    label_enabled = args.fraud_rate > 0
    if label_enabled and not args.token:
        print("Warning: --fraud-rate > 0 but no --token was provided. Fraud labeling disabled.")
        label_enabled = False

    if label_enabled and args.token:
        label_enabled = ensure_label_exists(args.url, args.fraud_label, args.token)

    evaluate_headers = build_evaluate_headers(args.token, args.api_key)

    if args.continuous:
        run_continuous(args, evaluate_headers, label_enabled)
    else:
        run_finite(args, evaluate_headers, label_enabled)


if __name__ == "__main__":
    main()
