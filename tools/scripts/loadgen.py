#!/usr/bin/env python3
"""Synthetic load generator for api-service.

Fires a mix of read requests (risk/top + search) at a running gateway and reports throughput
and latency percentiles. Standard library only, so it runs anywhere.

    python tools/scripts/loadgen.py --base http://localhost:8000 --requests 1000 --concurrency 32
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import time
import urllib.request


def _call(base: str, method: str, path: str, org: str, body: dict | None) -> tuple[float, bool]:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        base + path, data=data, method=method,
        headers={"x-org-id": org, "content-type": "application/json"},
    )
    start = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            resp.read()
            ok = resp.status < 400
    except Exception:  # noqa: BLE001 - a failed request is a data point, not a crash
        ok = False
    return time.perf_counter() - start, ok


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Load-test api-service.")
    ap.add_argument("--base", default="http://localhost:8000")
    ap.add_argument("--org", default="org_demo")
    ap.add_argument("--requests", type=int, default=1000)
    ap.add_argument("--concurrency", type=int, default=32)
    args = ap.parse_args(argv)

    plan: list[tuple[str, str, dict | None]] = []
    for i in range(args.requests):
        if i % 2:
            plan.append(("GET", "/api/v1/risk/top?limit=20", None))
        else:
            plan.append(("POST", "/api/v1/search", {"query": "billing", "limit": 10}))

    latencies: list[float] = []
    ok_count = 0
    started = time.perf_counter()
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        futures = [pool.submit(_call, args.base, m, p, args.org, b) for m, p, b in plan]
        for fut in concurrent.futures.as_completed(futures):
            dur, ok = fut.result()
            latencies.append(dur)
            ok_count += int(ok)
    elapsed = time.perf_counter() - started

    latencies.sort()
    n = len(latencies)

    def pct(p: float) -> float:
        return latencies[min(n - 1, int(n * p))] * 1000.0

    print(f"requests={n}  ok={ok_count}  errors={n - ok_count}")
    print(f"throughput={n / elapsed:,.1f} req/s over {elapsed:.2f}s (concurrency={args.concurrency})")
    print(f"latency ms  p50={pct(0.50):.1f}  p95={pct(0.95):.1f}  p99={pct(0.99):.1f}  "
          f"max={latencies[-1] * 1000:.1f}")
    return 0 if ok_count == n else 1


if __name__ == "__main__":
    raise SystemExit(main())
