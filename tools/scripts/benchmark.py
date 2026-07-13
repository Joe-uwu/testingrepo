#!/usr/bin/env python3
"""Micro-benchmark the hot paths — scoring, reasoning, retrieval — over the in-memory
pipeline. No infrastructure required.

    python tools/scripts/benchmark.py
"""

from __future__ import annotations

import time
from collections.abc import Callable


def _bench(name: str, fn: Callable[[], object], iters: int) -> None:
    fn()  # warm up
    start = time.perf_counter()
    for _ in range(iters):
        fn()
    elapsed = time.perf_counter() - start
    print(f"{name:<26} {iters / elapsed:>10,.0f} ops/s   ({elapsed / iters * 1e6:7.1f} µs/op)")


def main() -> None:
    from cortex.services.llm.graph import GraphReasoner
    from cortex.services.ranking.scoring import UrgencyScorer
    from cortex.tools.synthetic.scenario import ORG_ID, deploy_will_fail_scenario
    from cortex.tools.wiring import build_pipeline

    pipeline = build_pipeline(ORG_ID)
    pipeline.run_scenario(deploy_will_fail_scenario())

    top = pipeline.repo.top_by_urgency(org_id=ORG_ID, limit=1)[0]
    nodes, edges = pipeline.repo.neighborhood(org_id=ORG_ID, node_id=top.id, hops=3)
    evidence = pipeline.retrieval.gather_evidence(org_id=ORG_ID, node_id=top.id, hops=3)

    scorer = UrgencyScorer()
    reasoner = GraphReasoner()

    print(f"scenario: {len(pipeline.repo.all_nodes(org_id=ORG_ID))} nodes\n")
    _bench("urgency_scorer.score", lambda: scorer.score(top, nodes, edges), 20_000)
    _bench("graph_reasoner.reason", lambda: reasoner.reason(evidence, 0.9), 5_000)
    _bench(
        "retrieval.search",
        lambda: pipeline.retrieval.search(org_id=ORG_ID, query="billing", limit=10),
        5_000,
    )


if __name__ == "__main__":
    main()
