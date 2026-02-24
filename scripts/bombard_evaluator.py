#!/usr/bin/env python3
"""
Bombard the evaluator endpoint with synthetic events.

Usage:
    uv run python scripts/bombard_evaluator.py
    uv run python scripts/bombard_evaluator.py --n 200
    uv run python scripts/bombard_evaluator.py --n 50 --url http://localhost:8888
    uv run python scripts/bombard_evaluator.py --continuous
    uv run python scripts/bombard_evaluator.py --continuous --batch-size 20 --max-delay 10
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


def send_one(url: str, event: dict) -> dict:
    t0 = time.perf_counter()
    try:
        r = httpx.post(f"{url}/api/v2/evaluate", json=event, timeout=10)
        elapsed = time.perf_counter() - t0
        return {
            "ok": r.status_code == 200,
            "status": r.status_code,
            "elapsed": elapsed,
            "outcome_set": r.json().get("outcome_set", []) if r.status_code == 200 else [],
        }
    except Exception as exc:
        return {"ok": False, "status": -1, "elapsed": time.perf_counter() - t0, "outcome_set": [], "error": str(exc)}


def send_batch(url: str, batch: list[dict], concurrency: int) -> list[dict]:
    results = []
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = {pool.submit(send_one, url, e): e for e in batch}
        for future in as_completed(futures):
            results.append(future.result())
    return results


def print_summary(results: list[dict], total_elapsed: float) -> None:
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
            f"Latency (ok): "
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
        print("\nNo outcomes returned (no rules in production config?)")

    if failed:
        print(f"\nFirst failure: {next(r for r in results if not r['ok'])}")


def run_finite(args: argparse.Namespace) -> None:
    n = randint(1, args.n)
    events = [random_event() for _ in range(n)]
    print(f"Sending {n} events (random up to {args.n}) to {args.url} …\n")

    results = []
    outcome_counter: Counter = Counter()
    t_start = time.perf_counter()

    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        futures = {pool.submit(send_one, args.url, e): e for e in events}
        for i, future in enumerate(as_completed(futures), 1):
            res = future.result()
            results.append(res)
            for o in res["outcome_set"]:
                outcome_counter[o] += 1
            print("." if res["ok"] else "x", end="", flush=True)
            if i % 50 == 0:
                print(f"  {i}/{args.n}")

    print_summary(results, time.perf_counter() - t_start)


def run_continuous(args: argparse.Namespace) -> None:
    print(
        f"Continuous mode — batches of {args.batch_size} events, "
        f"random delay 0–{args.max_delay}s between batches. "
        f"Ctrl-C to stop.\n"
    )

    all_results: list[dict] = []
    batch_num = 0
    t_start = time.perf_counter()

    def _stop(sig, frame):  # noqa: ANN001
        print_summary(all_results, time.perf_counter() - t_start)
        sys.exit(0)

    signal.signal(signal.SIGINT, _stop)

    while True:
        batch_num += 1
        batch = [random_event() for _ in range(randint(1, args.batch_size))]
        results = send_batch(args.url, batch, args.concurrency)
        all_results.extend(results)

        ok = sum(1 for r in results if r["ok"])
        total = len(all_results)
        delay = uniform(0, args.max_delay)
        print(
            f"Batch {batch_num:>4}  {ok}/{args.batch_size} ok  (total sent: {total})  sleeping {delay:.1f}s …",
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
    args = parser.parse_args()

    if args.continuous:
        run_continuous(args)
    else:
        run_finite(args)


if __name__ == "__main__":
    main()
