#!/usr/bin/env python3
from __future__ import annotations

"""Read-only audit of representative hidden artifact truth in a --debug player package."""

import argparse
from collections import Counter
import json
import math
from pathlib import Path
from typing import Any, Mapping

DEFAULT_INPUT = Path("out/player_game.json")
DEFAULT_OUTPUT = Path("out/artifact_truth_audit.json")


def walk(value: Any, path=()):
    if isinstance(value, Mapping):
        for k, v in value.items():
            p = path + (str(k),)
            yield p, v
            yield from walk(v, p)
    elif isinstance(value, list):
        for i, v in enumerate(value):
            p = path + (str(i),)
            yield p, v
            yield from walk(v, p)


def object_id(row: Mapping[str, Any]) -> str | None:
    for key in ("object_id", "artifact_id", "id"):
        v = row.get(key)
        if isinstance(v, str) and v:
            return v
    return None


def index_rows(rows: Any) -> dict[str, Mapping[str, Any]]:
    out = {}
    if isinstance(rows, list):
        for row in rows:
            if isinstance(row, Mapping):
                oid = object_id(row)
                if oid:
                    out[oid] = row
    elif isinstance(rows, Mapping):
        for k, row in rows.items():
            if isinstance(row, Mapping):
                oid = object_id(row) or (str(k) if str(k).startswith("CAR-") else None)
                if oid:
                    out[oid] = row
    return out


def find_num(root: Any, fragments: tuple[str, ...], default=0.0) -> float:
    vals = []
    for path, value in walk(root):
        key = path[-1].lower() if path else ""
        if all(f in key for f in fragments) and isinstance(value, (int, float)) and not isinstance(value, bool):
            x = float(value)
            if math.isfinite(x):
                vals.append(x)
    return max(vals, key=abs) if vals else default


def find_map(root: Any, fragment: str) -> Mapping[str, Any] | None:
    for path, value in walk(root):
        if path and fragment in path[-1].lower() and isinstance(value, Mapping):
            return value
    return None


def cls(public: Mapping[str, Any], truth: Mapping[str, Any]) -> str:
    artifact = truth.get("artifact_truth") if isinstance(truth.get("artifact_truth"), Mapping) else {}
    for row in (public, truth, artifact):
        for key in ("class", "object_class", "artifact_class"):
            v = row.get(key) if isinstance(row, Mapping) else None
            if isinstance(v, str) and v:
                return v
    return "unknown"


def regime(public: Mapping[str, Any]) -> str:
    acq = public.get("acquisition")
    return str(acq.get("regime", "")) if isinstance(acq, Mapping) else ""


def metrics(public: Mapping[str, Any], truth: Mapping[str, Any]) -> dict[str, Any]:
    artifact = truth.get("artifact_truth") if isinstance(truth.get("artifact_truth"), Mapping) else truth
    manufacture = artifact.get("manufacture") if isinstance(artifact, Mapping) else None
    corrosion = artifact.get("corrosion") if isinstance(artifact, Mapping) else None
    guilds = manufacture.get("guild_affinities", {}) if isinstance(manufacture, Mapping) else {}
    guild_max = max((float(v) for v in guilds.values() if isinstance(v, (int, float))), default=0.0)
    integrity = float(corrosion.get("integrity_fraction", 1.0)) if isinstance(corrosion, Mapping) else 1.0
    coverage = float(corrosion.get("surface_coverage_fraction", 0.0)) if isinstance(corrosion, Mapping) else 0.0
    source_mix = find_map(artifact, "source_mix") or find_map(truth, "source_mix") or {}
    weights = [max(0.0, float(v)) for v in source_mix.values() if isinstance(v, (int, float)) and float(v) > 0]
    ent = 0.0
    if len(weights) > 1:
        s = sum(weights)
        p = [w/s for w in weights]
        ent = -sum(x*math.log(x) for x in p) / math.log(len(p))
    return {
        "object_class": cls(public, truth),
        "regime": regime(public),
        "route_km": max(find_num(truth, ("route", "km")), find_num(truth, ("distance", "km"))),
        "physical_crossings": find_num(truth, ("physical", "cross")),
        "field_crossings": find_num(truth, ("field", "cross")),
        "repair_count": find_num(artifact, ("repair", "count")),
        "recycle_count": find_num(artifact, ("recycl", "count")),
        "guild_max_affinity": guild_max,
        "primary_guild_id": manufacture.get("primary_guild_id") if isinstance(manufacture, Mapping) else None,
        "corrosion_integrity_fraction": integrity,
        "corrosion_surface_coverage_fraction": coverage,
        "source_entropy_normalized": ent,
        "source_component_count": len(source_mix),
        "has_bulk_alloy": bool(find_map(artifact, "alloy") or find_map(artifact, "composition")),
        "has_microstructure": bool(find_map(artifact, "microstructure")),
        "has_manufacture": isinstance(manufacture, Mapping),
        "has_corrosion": isinstance(corrosion, Mapping),
        "has_provenance": bool(find_map(artifact, "provenance") or source_mix),
    }


def role_score(role: str, m: Mapping[str, Any]) -> float:
    c, r = str(m["object_class"]), str(m["regime"])
    if role in {"sword", "axe", "bead", "scrap"}:
        return 1e6 if c == role else -1e9
    if role == "hoard":
        return 1e6 if r == "random_hoard" else -1e9
    if role == "remote_tail":
        return float(m["route_km"]) + 250*float(m["physical_crossings"]) + 800*float(m["field_crossings"]) + (500 if r == "stray_tail" else 0)
    if role == "repair_recycle":
        return 600*float(m["repair_count"]) + 350*float(m["recycle_count"]) + 50*float(m["source_entropy_normalized"])
    if role == "guild_signal":
        return 1000*float(m["guild_max_affinity"])
    if role == "corroded":
        return 700*(1-float(m["corrosion_integrity_fraction"])) + 300*float(m["corrosion_surface_coverage_fraction"])
    if role == "ordinary_control":
        return -(float(m["route_km"])/20 + 40*float(m["physical_crossings"]) + 120*float(m["field_crossings"]) + 80*float(m["repair_count"]) + 50*float(m["recycle_count"]))
    return -1e9


def build(payload: Mapping[str, Any]) -> dict[str, Any]:
    debug = payload.get("debug")
    if not isinstance(debug, Mapping):
        raise ValueError("player package has no debug block; generate once with --debug")
    truths = index_rows(debug.get("truth"))
    publics = index_rows(payload.get("objects"))
    analyses = index_rows(payload.get("analyses"))
    joined = {}
    for oid, public in publics.items():
        truth = truths.get(oid)
        if isinstance(truth, Mapping):
            joined[oid] = {"public": public, "truth": truth, "analysis": analyses.get(oid), "metrics": metrics(public, truth)}
    if not joined:
        raise ValueError("could not join public objects to debug.truth by object_id")

    completeness = Counter()
    for row in joined.values():
        for k in ("has_bulk_alloy", "has_microstructure", "has_manufacture", "has_corrosion", "has_provenance"):
            completeness[k] += int(bool(row["metrics"][k]))

    roles = ("sword", "axe", "bead", "scrap", "hoard", "remote_tail", "repair_recycle", "guild_signal", "corroded", "ordinary_control")
    selected, used = [], set()
    for role in roles:
        ranked = sorted(((oid, role_score(role, row["metrics"])) for oid, row in joined.items() if oid not in used), key=lambda x: (-x[1], x[0]))
        if not ranked:
            break
        if ranked[0][1] <= -1e8:
            ranked = sorted(((oid, float(row["metrics"]["route_km"]) + 100*float(row["metrics"]["source_entropy_normalized"])) for oid, row in joined.items() if oid not in used), key=lambda x: (-x[1], x[0]))
        oid, score = ranked[0]
        used.add(oid)
        row = joined[oid]
        selected.append({
            "audit_role": role,
            "selection_score": score,
            "object_id": oid,
            "metrics": row["metrics"],
            "public_player_projection": row["public"],
            "player_analysis": row["analysis"],
            "hidden_debug_truth": row["truth"],
            "artifact_truth": row["truth"].get("artifact_truth"),
        })

    return {
        "schema": "atolia.generated-artifact-truth-audit.v1",
        "package_meta": payload.get("meta"),
        "objects_joined_to_hidden_truth": len(joined),
        "truth_completeness_across_300": dict(completeness),
        "selected": selected,
        "warning": "Developer truth audit; do not ship this output to players.",
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUTPUT)
    args = ap.parse_args()
    payload = json.loads(args.input.read_text(encoding="utf-8"))
    audit = build(payload)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(audit, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({
        "schema": audit["schema"],
        "objects_joined_to_hidden_truth": audit["objects_joined_to_hidden_truth"],
        "truth_completeness_across_300": audit["truth_completeness_across_300"],
        "selected": [{"role": x["audit_role"], "object_id": x["object_id"], **x["metrics"]} for x in audit["selected"]],
        "output": str(args.out),
    }, indent=2))


if __name__ == "__main__":
    main()
