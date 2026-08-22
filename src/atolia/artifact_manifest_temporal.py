from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Mapping, Sequence

import numpy as np

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import artifact_manifest as manifest
import provenance_field_mediterranean as med

NETWORK_OLD_BC = 1800
NETWORK_YOUNG_BC = 1000
DIRECT_METALS = {"copper", "bronze", "lead", "tin_pewter"}


def relation_to_network(slot: manifest.ArtifactSlot) -> str:
    old = max(slot.start_bc, slot.end_bc)
    young = min(slot.start_bc, slot.end_bc)
    if young >= NETWORK_OLD_BC:
        return "pre_network_precursor"
    if old <= NETWORK_YOUNG_BC:
        return "post_network_descendant"
    if slot.material_family in DIRECT_METALS:
        return "direct_copper_network"
    return "coeval_parallel_craft"


def time_distance_from_network(slot: manifest.ArtifactSlot) -> float:
    mid = 0.5 * (slot.start_bc + slot.end_bc)
    if NETWORK_YOUNG_BC <= mid <= NETWORK_OLD_BC:
        return 0.0
    return min(abs(mid - NETWORK_OLD_BC), abs(mid - NETWORK_YOUNG_BC))


def heritage_strength(slot: manifest.ArtifactSlot, tau_years: float = 720.0) -> float:
    relation = relation_to_network(slot)
    if relation == "direct_copper_network":
        return 1.0
    d = time_distance_from_network(slot)
    base = math.exp(-d / tau_years)
    if relation == "coeval_parallel_craft":
        base = max(base, 0.58)
    return float(np.clip(base, 0.015, 0.95))


def improved_slot(slot: manifest.ArtifactSlot) -> manifest.ArtifactSlot:
    """Correct broad chronology where a generic title would otherwise inherit index fallback."""
    s = slot.title.lower()
    start, end = slot.start_bc, slot.end_bc
    if any(k in s for k in ("brass fibula", "high-zinc brass", "leaded brass", "gunmetal", "red-brass")):
        start, end = 600, -500
    elif any(k in s for k in ("mercury-gilded", "fire-gilded", "niello", "enamel-inlaid")):
        start, end = 500, -900
    elif any(k in s for k in ("certosa-type",)):
        start, end = 700, 400
    elif any(k in s for k in ("la tène-type",)):
        start, end = 500, -50
    elif any(k in s for k in ("natural-electrum", "electrum pendant")):
        start, end = 1800, 400
    elif any(k in s for k in ("lead sling bullet", "inscribed lead tablet", "lead pipe", "pewter")):
        start, end = 700, -700
    elif any(k in s for k in ("pattern-welded", "piled-construction seax", "trilobate iron arrowhead")):
        start, end = 400, -1000
    elif any(k in s for k in ("martensitic", "tempered-martensitic", "differentially hardened")):
        start, end = 700, -1200
    elif any(k in s for k in ("bloomery", "wrought-iron", "iron sickle", "iron spearhead", "iron axe", "iron chisel")):
        start, end = 1200, -800
    elif any(k in s for k in ("silver drachm", "denarius", "fourrée", "potin", "solidus")):
        # Specific names can be placed more narrowly than generic `coin`.
        if "solidus" in s:
            start, end = -300, -800
        elif "denarius" in s or "fourrée" in s:
            start, end = 250, -300
        elif "drachm" in s:
            start, end = 600, -200
        else:
            start, end = 300, -300
    return manifest.ArtifactSlot(
        index=slot.index, title=slot.title, level=slot.level, object_class=slot.object_class,
        material_family=slot.material_family, start_bc=start, end_bc=end,
        region_hint=slot.region_hint, source_hint=slot.source_hint,
        process_hints=slot.process_hints, prestige=slot.prestige,
        destructive_sampling_allowed=slot.destructive_sampling_allowed,
    )


class TemporalManifestCompiler(manifest.ManifestCompiler):
    def compile(self, slots: Sequence[manifest.ArtifactSlot]) -> list[Dict[str, Any]]:
        slots = [improved_slot(slot) for slot in slots]
        if not self.world.catalogue_truth:
            raise RuntimeError("Generate archaeological catalogue before manifest compilation.")
        pool = list(self.world.catalogue_truth)
        unused = set(range(len(pool)))
        records: list[Dict[str, Any]] = []
        guild_usage = Counter()
        region_usage = Counter()
        bundle_usage = Counter()

        for slot in slots:
            relation = relation_to_network(slot)
            if relation == "direct_copper_network":
                idx = self._choose_candidate(slot, pool, unused, guild_usage, region_usage, bundle_usage)
                row = pool[idx]
                unused.discard(idx)
                record = self._project_direct(slot, row, max(0.16, manifest.bronze_network_overlap(slot)))
                record["truth"]["temporal_relation"] = relation
            else:
                idx = self._choose_descendant_anchor(slot, pool, unused, guild_usage, region_usage)
                row = pool[idx]
                record = self._project_temporal_shell(slot, row, relation)
            records.append(record)
            truth = record["truth"]
            if truth.get("guild_id"):
                guild_usage[truth["guild_id"]] += 1
            region_usage[truth.get("macro_region", "other")] += 1
            if truth.get("bundle_id"):
                bundle_usage[truth["bundle_id"]] += 1

        self._rebalance_temporal_regions(records, slots, pool)
        return records

    def _project_temporal_shell(self, slot: manifest.ArtifactSlot, row: Mapping[str, Any], relation: str) -> Dict[str, Any]:
        result = json.loads(json.dumps(row))
        requested_region = slot.region_hint or row["truth"].get("macro_region", "other")
        strength = heritage_strength(slot)
        anchor_guild = row["truth"].get("guild_id")
        midpoint = int(round((slot.start_bc + slot.end_bc) / 2.0))
        result["manifest_index"] = slot.index
        result["curriculum_level"] = slot.level
        result["display_name"] = slot.title
        result["class"] = slot.object_class
        result["catalogue_material"] = slot.material_family
        result["date_center_bc"] = midpoint
        result["date_uncertainty_years"] = max(30, int(abs(slot.start_bc - slot.end_bc) * 0.10))
        result["manifest"] = self._manifest_public(slot)
        result["tests"] = self._adapt_tests_for_material(slot, result.get("tests", {}))

        if relation == "pre_network_precursor":
            truth = {
                "manifest_binding": relation,
                "comparative_future_anchor_object_id": row["object_id"],
                "proto_guild_affinity": anchor_guild,
                "proto_guild_affinity_strength": round(strength, 4),
                "guild_id": None,
                "guild_strength": 0.0,
                "macro_region": requested_region,
                "bronze_network_coupling": 0.0,
                "direct_atesis_flux_relation": False,
                "historical_scope_note": "Predates the hidden 1800–1000 BC copper-flow model. Similarity is a precursor/comparative technical affinity, never direct guild membership or corridor flux.",
                "material_family_requested": slot.material_family,
            }
        else:
            truth = {
                "manifest_binding": relation,
                "ancestral_bronze_anchor_object_id": row["object_id"],
                "guild_id": anchor_guild if strength >= 0.12 else None,
                "guild_strength": round(float(row["truth"].get("guild_strength", 0.0)) * strength, 4),
                "macro_region": requested_region,
                "lineage_id": row["truth"].get("lineage_id"),
                "technical_vector": row["truth"].get("technical_vector"),
                "heritage_strength": round(strength, 4),
                "bronze_network_coupling": 0.0,
                "direct_atesis_flux_relation": False,
                "historical_scope_note": (
                    "Coeval but materially parallel craft network; no direct copper-flux membership."
                    if relation == "coeval_parallel_craft"
                    else "Later descendant/analogue technical network with time-decayed affinity; no direct Bronze-Age copper-flux membership."
                ),
                "material_family_requested": slot.material_family,
            }
        result["truth"] = truth
        return result

    def _rebalance_temporal_regions(self, records, slots, pool) -> None:
        by_region = {}
        for row in pool:
            by_region.setdefault(row["truth"].get("macro_region", "other"), []).append(row)
        for i, slot in enumerate(slots):
            if not slot.region_hint or records[i]["truth"].get("macro_region") == slot.region_hint:
                continue
            candidates = by_region.get(slot.region_hint, [])
            if not candidates:
                continue
            anchor = candidates[int(self.rng.integers(0, len(candidates)))]
            relation = relation_to_network(slot)
            if relation == "direct_copper_network":
                records[i] = self._project_direct(slot, anchor, max(.16, manifest.bronze_network_overlap(slot)))
                records[i]["truth"]["temporal_relation"] = relation
            else:
                records[i] = self._project_temporal_shell(slot, anchor, relation)


def human_year(year_bc: int) -> Dict[str, Any]:
    if year_bc > 0:
        return {"era": "BC", "year": year_bc}
    return {"era": "AD", "year": abs(year_bc)}


def player_record(record: Mapping[str, Any]) -> Dict[str, Any]:
    uncertainty = int(record["date_uncertainty_years"])
    center = int(record["date_center_bc"])
    old = center + uncertainty
    young = center - uncertainty
    return {
        "object_id": record["object_id"],
        "manifest_index": record["manifest_index"],
        "curriculum_level": record["curriculum_level"],
        "display_name": record["display_name"],
        "class": record["class"],
        "mass_kg": record.get("mass_kg"),
        "date_range": {"older": human_year(old), "younger": human_year(young)},
        "findspot": record.get("findspot"),
        "hoard_id": record.get("hoard_id"),
        "preservation": record.get("preservation"),
        "catalogue_material": record.get("catalogue_material"),
        "manifest": record.get("manifest"),
        "available_tests": list(record.get("tests", {}).keys()),
    }


def compile_manifest(manifest_path: Path, hypothesis_path: Path, out_dir: Path, seed: int = 1300, workshops: int = 3200, catalogue_cap: int = 30000) -> Dict[str, Any]:
    slots = [improved_slot(slot) for slot in manifest.parse_manifest(manifest_path)]
    if not slots:
        raise ValueError("Manifest contains no artifacts.")
    hypothesis = json.loads(hypothesis_path.read_text(encoding="utf-8"))
    world = med.MediterraneanProvenanceWorld(hypothesis, seed=seed)
    world.build(workshop_count=workshops)
    generation = world.generate_archaeological_catalogue(max_materialized=catalogue_cap)
    compiler = TemporalManifestCompiler(world, seed=seed)
    records = compiler.compile(slots)

    player = [player_record(row) for row in records]
    analyses = [{"object_id": row["object_id"], "manifest_index": row["manifest_index"], "tests": row["tests"]} for row in records]
    truth = [{"object_id": row["object_id"], "manifest_index": row["manifest_index"], "truth": row["truth"]} for row in records]

    (out_dir / "player").mkdir(parents=True, exist_ok=True)
    (out_dir / "debug").mkdir(parents=True, exist_ok=True)
    (out_dir / "player" / "objects_manifest.json").write_text(json.dumps(player, indent=2, ensure_ascii=False), encoding="utf-8")
    (out_dir / "player" / "analyses_manifest.json").write_text(json.dumps(analyses, indent=2, ensure_ascii=False), encoding="utf-8")
    (out_dir / "debug" / "truth_manifest.json").write_text(json.dumps(truth, indent=2, ensure_ascii=False), encoding="utf-8")

    relation_counts = Counter(row["truth"]["manifest_binding"] for row in records)
    region_counts = Counter(row["truth"].get("macro_region", "other") for row in records)
    guild_counts = Counter(row["truth"].get("guild_id") for row in records if row["truth"].get("guild_id"))
    report = {
        "seed": seed,
        "manifest_count": len(slots),
        "compiled_count": len(records),
        "levels": len({slot.level for slot in slots}),
        "temporal_binding_counts": dict(relation_counts),
        "region_counts_truth": dict(region_counts),
        "guilds_represented_truth": len(guild_counts),
        "hidden_manufacture_use_events_est": generation["hidden_manufacture_use_events_est"],
        "catalogued_objects": generation["catalogued_objects"],
        "anti_spoiler": {
            "player_export_contains_hidden_target": False,
            "player_export_contains_bundle_truth": False,
            "player_export_contains_guild_truth": False,
            "pre_network_objects_carry_direct_flux_truth": False,
            "post_network_objects_carry_direct_flux_truth": False,
        },
    }
    (out_dir / "debug" / "manifest_validation.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Compile an arbitrary artifact list onto the temporally layered Atolia provenance world.")
    parser.add_argument("manifest")
    parser.add_argument("--hypothesis", default="hypotheses/atolia_atesis_1800_1000_v0.json")
    parser.add_argument("--out-dir", default="out/atolia_manifest_temporal_v0")
    parser.add_argument("--seed", type=int, default=1300)
    parser.add_argument("--workshops", type=int, default=3200)
    parser.add_argument("--catalogue-cap", type=int, default=30000)
    args = parser.parse_args()
    report = compile_manifest(Path(args.manifest), Path(args.hypothesis), Path(args.out_dir), args.seed, args.workshops, args.catalogue_cap)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
