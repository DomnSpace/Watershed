#!/usr/bin/env python3
from __future__ import annotations

"""Empirically audit the eight archaeology career regimes from one --debug package.

Read-only.  This answers what the regimes actually produced, not merely what the
constants say they should produce.  It does not regenerate the career.
"""

import argparse
from collections import Counter, defaultdict
import json
import math
from pathlib import Path
from statistics import mean
from typing import Any, Mapping

DEFAULT_INPUT = Path("out/player_game.json")
DEFAULT_OUTPUT = Path("out/career_regime_audit.json")

REGIME_ORDER = (
    "stray_tail",
    "context_followup",
    "random_hoard",
    "post_hoard_comparison",
    "exploratory_dig",
    "discriminating_dig",
    "network_reconstruction",
    "falsification_probe",
)


def _oid(row: Mapping[str, Any]) -> str | None:
    for key in ("object_id", "artifact_id", "id"):
        value = row.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _index(rows: Any) -> dict[str, Mapping[str, Any]]:
    out: dict[str, Mapping[str, Any]] = {}
    if isinstance(rows, list):
        for row in rows:
            if isinstance(row, Mapping):
                oid = _oid(row)
                if oid:
                    out[oid] = row
    elif isinstance(rows, Mapping):
        for key, row in rows.items():
            if isinstance(row, Mapping):
                oid = _oid(row) or (str(key) if str(key).startswith("CAR-") else None)
                if oid:
                    out[oid] = row
    return out


def _dig(root: Any, *path: str, default: Any = None) -> Any:
    cur = root
    for key in path:
        if not isinstance(cur, Mapping) or key not in cur:
            return default
        cur = cur[key]
    return cur


def _first(root: Any, paths: tuple[tuple[str, ...], ...], default: Any = None) -> Any:
    for path in paths:
        value = _dig(root, *path, default=None)
        if value is not None:
            return value
    return default


def _num(value: Any, default: float = 0.0) -> float:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        x = float(value)
        if math.isfinite(x):
            return x
    return default


def _quantiles(values: list[float]) -> dict[str, float]:
    if not values:
        return {}
    xs = sorted(values)
    def q(p: float) -> float:
        if len(xs) == 1:
            return xs[0]
        i = p * (len(xs) - 1)
        lo, hi = int(math.floor(i)), int(math.ceil(i))
        if lo == hi:
            return xs[lo]
        f = i - lo
        return xs[lo] * (1 - f) + xs[hi] * f
    return {"min": xs[0], "q10": q(.10), "q25": q(.25), "median": q(.50), "q75": q(.75), "q90": q(.90), "max": xs[-1], "mean": mean(xs)}


def _object_metrics(public: Mapping[str, Any], truth_row: Mapping[str, Any]) -> dict[str, Any]:
    artifact = truth_row.get("artifact_truth") if isinstance(truth_row.get("artifact_truth"), Mapping) else {}
    hidden = truth_row.get("truth") if isinstance(truth_row.get("truth"), Mapping) else {}
    acquisition = public.get("acquisition") if isinstance(public.get("acquisition"), Mapping) else {}

    route_km = _num(_first(truth_row, (("truth", "route_km"), ("route_km",)), 0.0))
    corridor = _num(_first(truth_row, (("truth", "corridor_crossings"), ("truth", "physical_crossings"), ("corridor_crossings",)), 0.0))
    field = _num(_first(truth_row, (("truth", "field_crossings"), ("field_crossings",)), 0.0))
    exceptionality = _num(_first(truth_row, (("truth", "exceptionality"), ("exceptionality",)), 0.0))
    tail = bool(_first(public, (("acquisition", "tail_event_truth"),), False) or _first(truth_row, (("truth", "long_distance_tail"), ("long_distance_tail",)), False))

    material = artifact.get("material") if isinstance(artifact.get("material"), Mapping) else {}
    manufacture = artifact.get("manufacture") if isinstance(artifact.get("manufacture"), Mapping) else {}
    timeline = artifact.get("timeline") if isinstance(artifact.get("timeline"), Mapping) else {}
    corrosion = artifact.get("corrosion") if isinstance(artifact.get("corrosion"), Mapping) else {}

    recycled_fraction = _num(material.get("recycled_fraction_proxy"), 0.0)
    repair_events = timeline.get("repair_events") if isinstance(timeline.get("repair_events"), list) else []
    source_entropy = _num(material.get("source_entropy"), _num(hidden.get("source_entropy"), 0.0))
    guild_strength = _num(hidden.get("guild_strength"), 0.0)
    if guild_strength == 0.0 and isinstance(manufacture.get("guild_affinities"), Mapping):
        guild_strength = max((_num(v) for v in manufacture["guild_affinities"].values()), default=0.0)

    return {
        "object_id": _oid(public),
        "career_index": int(str(_oid(public) or "CAR-0").split("-")[-1]),
        "regime": str(acquisition.get("regime", "unknown")),
        "action_id": str(acquisition.get("action_id", "")),
        "site_node": str(acquisition.get("site_node", "")),
        "object_class": str(public.get("class", "unknown")),
        "deposition_mode": str(public.get("deposition_mode_truth", "")),
        "hoard_id": public.get("hoard_id"),
        "poari_p": _num(acquisition.get("poari_p"), float("nan")),
        "poari_action_score": _num(acquisition.get("poari_action_score_truth"), float("nan")),
        "tail": tail,
        "route_km": route_km,
        "corridor_crossings": corridor,
        "field_crossings": field,
        "exceptionality": exceptionality,
        "recycled_fraction_proxy": recycled_fraction,
        "repair_event_count": len(repair_events),
        "source_entropy": source_entropy,
        "guild_strength": guild_strength,
        "corrosion_integrity": _num(corrosion.get("integrity_fraction"), 0.0),
        "corrosion_surface_coverage": _num(corrosion.get("surface_coverage_fraction"), 0.0),
    }


def _regime_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    def vals(key: str) -> list[float]:
        return [float(r[key]) for r in rows if isinstance(r.get(key), (int, float)) and math.isfinite(float(r[key]))]

    actions = Counter(r["action_id"] for r in rows if r["action_id"])
    sites = Counter(r["site_node"] for r in rows if r["site_node"])
    classes = Counter(r["object_class"] for r in rows)
    dep = Counter(r["deposition_mode"] for r in rows if r["deposition_mode"])
    return {
        "objects": len(rows),
        "unique_actions": len(actions),
        "objects_per_action": dict(sorted(actions.items())),
        "unique_sites": len(sites),
        "top_sites": sites.most_common(8),
        "object_classes": dict(classes),
        "deposition_modes": dict(dep),
        "tail_count": sum(bool(r["tail"]) for r in rows),
        "tail_fraction": sum(bool(r["tail"]) for r in rows) / max(1, len(rows)),
        "route_km": _quantiles(vals("route_km")),
        "corridor_crossings": _quantiles(vals("corridor_crossings")),
        "field_crossings": _quantiles(vals("field_crossings")),
        "exceptionality": _quantiles(vals("exceptionality")),
        "recycled_fraction_proxy": _quantiles(vals("recycled_fraction_proxy")),
        "repair_event_count": _quantiles(vals("repair_event_count")),
        "objects_with_repairs": sum(int(r["repair_event_count"]) > 0 for r in rows),
        "objects_with_recycling_proxy_gt_0_10": sum(float(r["recycled_fraction_proxy"]) > .10 for r in rows),
        "objects_route_gt_500_km": sum(float(r["route_km"]) > 500 for r in rows),
        "objects_route_gt_1000_km": sum(float(r["route_km"]) > 1000 for r in rows),
        "objects_corridor_crossings_gt_0": sum(float(r["corridor_crossings"]) > 1e-12 for r in rows),
        "objects_field_crossings_ge_0_12": sum(float(r["field_crossings"]) >= .12 for r in rows),
        "source_entropy": _quantiles(vals("source_entropy")),
        "guild_strength": _quantiles(vals("guild_strength")),
        "corrosion_integrity": _quantiles(vals("corrosion_integrity")),
        "corrosion_surface_coverage": _quantiles(vals("corrosion_surface_coverage")),
        "poari_p_values": sorted(set(r["poari_p"] for r in rows if math.isfinite(float(r["poari_p"])))),
        "poari_action_score": _quantiles(vals("poari_action_score")),
    }


def build(payload: Mapping[str, Any]) -> dict[str, Any]:
    debug = payload.get("debug")
    if not isinstance(debug, Mapping):
        raise ValueError("package has no debug block; generate with --debug")
    public = _index(payload.get("objects"))
    truth = _index(debug.get("truth"))
    rows = []
    for oid, p in public.items():
        t = truth.get(oid)
        if isinstance(t, Mapping):
            rows.append(_object_metrics(p, t))
    rows.sort(key=lambda r: r["career_index"])
    if len(rows) != 300:
        raise ValueError(f"expected 300 joined objects, got {len(rows)}")

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[row["regime"]].append(row)

    summaries = {name: _regime_summary(grouped.get(name, [])) for name in REGIME_ORDER}
    whole = _regime_summary(rows)
    diagnostics = {
        "all_300_have_known_regime": all(r["regime"] in REGIME_ORDER for r in rows),
        "regime_counts": {name: len(grouped.get(name, [])) for name in REGIME_ORDER},
        "total_repairs": sum(int(r["repair_event_count"]) for r in rows),
        "objects_with_repairs": sum(int(r["repair_event_count"]) > 0 for r in rows),
        "objects_with_recycling_proxy_gt_0_10": sum(float(r["recycled_fraction_proxy"]) > .10 for r in rows),
        "objects_route_gt_500_km": sum(float(r["route_km"]) > 500 for r in rows),
        "objects_route_gt_1000_km": sum(float(r["route_km"]) > 1000 for r in rows),
        "objects_corridor_crossings_gt_0": sum(float(r["corridor_crossings"]) > 1e-12 for r in rows),
        "objects_field_crossings_ge_0_12": sum(float(r["field_crossings"]) >= .12 for r in rows),
    }
    return {
        "schema": "atolia.career-regime-audit.v1",
        "package_meta": payload.get("meta"),
        "diagnostics": diagnostics,
        "whole_career": whole,
        "regimes": summaries,
        "objects": rows,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="Audit empirical behavior of all eight Atolia career regimes.")
    ap.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUTPUT)
    args = ap.parse_args()
    payload = json.loads(args.input.read_text(encoding="utf-8"))
    audit = build(payload)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(audit, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({
        "schema": audit["schema"],
        "diagnostics": audit["diagnostics"],
        "regimes": {
            name: {
                "objects": row["objects"],
                "unique_actions": row["unique_actions"],
                "unique_sites": row["unique_sites"],
                "tail_fraction": row["tail_fraction"],
                "route_km": row["route_km"],
                "corridor_crossings": row["corridor_crossings"],
                "field_crossings": row["field_crossings"],
                "objects_with_repairs": row["objects_with_repairs"],
                "objects_with_recycling_proxy_gt_0_10": row["objects_with_recycling_proxy_gt_0_10"],
                "objects_route_gt_500_km": row["objects_route_gt_500_km"],
                "objects_route_gt_1000_km": row["objects_route_gt_1000_km"],
                "objects_corridor_crossings_gt_0": row["objects_corridor_crossings_gt_0"],
                "source_entropy": row["source_entropy"],
                "guild_strength": row["guild_strength"],
                "poari_p_values": row["poari_p_values"],
            }
            for name, row in audit["regimes"].items()
        },
        "output": str(args.out),
    }, indent=2))


if __name__ == "__main__":
    main()
