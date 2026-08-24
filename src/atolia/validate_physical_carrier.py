#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter, defaultdict, deque
from pathlib import Path
from typing import Any, Dict, Mapping

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import provenance_field_mediterranean as med


def validate(data: Mapping[str, Any], expected_total_nodes: int | None = None) -> Dict[str, Any]:
    nodes = list(data.get("nodes", [])); edges = list(data.get("edges", []))
    ids = [str(n["id"]) for n in nodes]
    errors = []
    if len(ids) != len(set(ids)):
        errors.append("duplicate derived node ids")
    known = set(ids)
    # Canonical IDs are not duplicated in carrier nodes; they are installed by the world first.
    canonical_ids = set()
    for e in edges:
        a, b = str(e["a"]), str(e["b"])
        if a not in known: canonical_ids.add(a)
        if b not in known: canonical_ids.add(b)
        if a == b: errors.append(f"self edge {a}")
        if float(e.get("cost", 0)) <= 0: errors.append(f"non-positive edge cost {a}->{b}")

    target = int(data.get("target_nodes", 0) or 0)
    canonical_count = int(data.get("canonical_node_count", len(canonical_ids)) or 0)
    total = len(nodes) + canonical_count
    if target and total != target:
        errors.append(f"node budget mismatch total={total} target={target}")
    if expected_total_nodes is not None and total != expected_total_nodes:
        errors.append(f"expected {expected_total_nodes} total nodes, got {total}")

    kind_counts = Counter(str(n.get("kind", "unknown")) for n in nodes)
    region_counts = Counter(str(n.get("region", "other")) for n in nodes)
    mode_counts = Counter(str(e.get("mode", "unknown")) for e in edges)

    # Derived-only component report; canonical attachments intentionally bridge components later.
    adj = defaultdict(set)
    all_ids = set(ids) | canonical_ids
    for e in edges:
        a, b = str(e["a"]), str(e["b"])
        adj[a].add(b); adj[b].add(a)
    components = []
    unseen = set(all_ids)
    while unseen:
        root = min(unseen); q = deque([root]); unseen.remove(root); n = 0
        while q:
            cur = q.popleft(); n += 1
            for nxt in adj[cur]:
                if nxt in unseen:
                    unseen.remove(nxt); q.append(nxt)
        components.append(n)
    components.sort(reverse=True)

    # Sanity checks for the intended physical carrier, not archaeological output.
    if kind_counts.get("river", 0) < 250:
        errors.append("too few river nodes for continental carrier")
    if kind_counts.get("coast", 0) < 100:
        errors.append("too few coast nodes for Mediterranean/Atlantic carrier")
    if not any(m in mode_counts for m in ("pass", "portage")):
        errors.append("no pass/portage cross-watershed edges")
    if not any(m in mode_counts for m in ("sea", "coast", "coastal_transfer")):
        errors.append("no maritime carrier edges")

    return {
        "ok": not errors, "errors": errors,
        "schema": data.get("schema"), "target_nodes": target, "derived_nodes": len(nodes),
        "canonical_node_count": canonical_count, "total_nodes": total, "edges": len(edges),
        "kind_counts": dict(kind_counts), "region_counts": dict(region_counts),
        "mode_counts": dict(mode_counts), "components": components[:20],
        "largest_component_fraction": (components[0] / max(1, len(all_ids))) if components else 0.0,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("carrier", type=Path, nargs="?", default=HERE / "data" / "physical_carrier_1000.json")
    ap.add_argument("--expected-total", type=int, default=1000)
    args = ap.parse_args()
    report = validate(json.loads(args.carrier.read_text(encoding="utf-8")), args.expected_total)
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if report["ok"] else 2)


if __name__ == "__main__":
    main()
