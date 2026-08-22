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
import artifact_manifest_temporal as temporal
import provenance_field_mediterranean as med


class DistributionalManifestCompiler(temporal.TemporalManifestCompiler):
    """Bind named artifact slots while preserving the latent world's distribution.

    Explicit slot requirements (class/material/region/source) take priority.
    Otherwise the selected direct Bronze-Age objects are pressure-matched toward
    the catalogue's region/bundle/guild/source proportions rather than flattened
    into equal representation.
    """

    def compile(self, slots: Sequence[manifest.ArtifactSlot]) -> list[Dict[str, Any]]:
        slots = [temporal.improved_slot(slot) for slot in slots]
        pool = list(self.world.catalogue_truth)
        if not pool:
            raise RuntimeError("Generate archaeological catalogue before manifest compilation.")

        direct_slots = [slot for slot in slots if temporal.relation_to_network(slot) == "direct_copper_network"]
        shell_slots = [slot for slot in slots if temporal.relation_to_network(slot) != "direct_copper_network"]
        targets = self._distribution_targets(pool, len(direct_slots))
        unused = set(range(len(pool)))
        selected_by_index: Dict[int, Dict[str, Any]] = {}
        used_region = Counter()
        used_bundle = Counter()
        used_guild = Counter()
        used_source = Counter()

        # Reserve scarce/explicit slots before generic ones consume their candidates.
        ordered_direct = sorted(direct_slots, key=self._specificity, reverse=True)
        for slot in ordered_direct:
            idx = self._choose_distributional_candidate(
                slot, pool, unused, targets,
                used_region, used_bundle, used_guild, used_source,
            )
            row = pool[idx]
            unused.discard(idx)
            record = self._project_direct(slot, row, max(0.16, manifest.bronze_network_overlap(slot)))
            record["truth"]["temporal_relation"] = "direct_copper_network"
            selected_by_index[slot.index] = record
            truth = record["truth"]
            used_region[truth.get("macro_region", "other")] += 1
            used_bundle[truth.get("bundle_id", "none")] += 1
            if truth.get("guild_id"):
                used_guild[truth["guild_id"]] += 1
            used_source[self._dominant_source(truth)] += 1

        # Pre-/post-network objects are attached only to comparative or descendant
        # technical anchors. Their selection does not alter Bronze flux quotas.
        for slot in sorted(shell_slots, key=lambda s: s.index):
            idx = self._choose_shell_anchor(slot, pool, unused, used_guild, used_region)
            row = pool[idx]
            relation = temporal.relation_to_network(slot)
            selected_by_index[slot.index] = self._project_temporal_shell(slot, row, relation)

        records = [selected_by_index[slot.index] for slot in sorted(slots, key=lambda s: s.index)]
        self._rebalance_temporal_regions(records, sorted(slots, key=lambda s: s.index), pool)
        return records

    @staticmethod
    def _specificity(slot: manifest.ArtifactSlot) -> float:
        score = 0.0
        score += 5.0 if slot.source_hint else 0.0
        score += 4.0 if slot.region_hint else 0.0
        score += min(3.0, 0.6 * len(slot.process_hints))
        score += 1.5 * slot.prestige
        # Rare/heavy categories get reserved before generic pins/beads.
        score += 1.2 if slot.object_class in {"ingot", "vessel", "figurine", "sword"} else 0.0
        return score

    def _distribution_targets(self, pool: Sequence[Mapping[str, Any]], n: int) -> Dict[str, Dict[str, float]]:
        counters = {
            "region": Counter(), "bundle": Counter(), "guild": Counter(), "source": Counter(),
        }
        for row in pool:
            truth = row["truth"]
            counters["region"][truth.get("macro_region", "other")] += 1
            counters["bundle"][truth.get("bundle_id", "none")] += 1
            if truth.get("guild_id"):
                counters["guild"][truth["guild_id"]] += 1
            counters["source"][self._dominant_source(truth)] += 1
        targets: Dict[str, Dict[str, float]] = {}
        for key, counter in counters.items():
            total = max(1, sum(counter.values()))
            targets[key] = {name: n * count / total for name, count in counter.items()}
        return targets

    @staticmethod
    def _dominant_source(truth: Mapping[str, Any]) -> str:
        mix = truth.get("source_mix") or {}
        return max(mix, key=mix.get) if mix else "unknown"

    @staticmethod
    def _deficit_bonus(target: float, used: int) -> float:
        if target <= 0:
            return -0.15 * used
        deficit = target - used
        return float(np.clip(deficit / max(1.0, target), -1.2, 1.2))

    def _choose_distributional_candidate(
        self, slot, pool, unused, targets,
        used_region, used_bundle, used_guild, used_source,
    ) -> int:
        trial = list(unused)
        # Random subset is sampled from the observed catalogue itself, so the
        # catalogue's frequency distribution remains the proposal distribution.
        if len(trial) > 1800:
            trial = list(self.rng.choice(trial, size=1800, replace=False))
        best_i, best_score = None, -1e18
        for raw_i in trial:
            i = int(raw_i)
            row = pool[i]
            truth = row["truth"]
            region = truth.get("macro_region", "other")
            bundle = truth.get("bundle_id", "none")
            guild = truth.get("guild_id")
            source = self._dominant_source(truth)

            score = 3.5 * manifest.class_compatibility(slot, row)
            score += 3.0 * manifest.material_compatibility(slot, row)
            score += 2.2 * manifest.chronology_overlap(slot, int(row["date_center_bc"]))
            if slot.region_hint:
                score += 4.2 if region == slot.region_hint else -1.6
            if slot.source_hint:
                score += 4.6 * float(truth.get("source_mix", {}).get(slot.source_hint, 0.0))
            score += 0.62 * self._deficit_bonus(targets["region"].get(region, 0.0), used_region[region])
            score += 0.52 * self._deficit_bonus(targets["bundle"].get(bundle, 0.0), used_bundle[bundle])
            if guild:
                score += 0.24 * self._deficit_bonus(targets["guild"].get(guild, 0.0), used_guild[guild])
            score += 0.35 * self._deficit_bonus(targets["source"].get(source, 0.0), used_source[source])
            score += self.rng.normal(0, 0.035)
            if score > best_score:
                best_i, best_score = i, float(score)
        if best_i is None:
            raise RuntimeError(f"No compatible catalogue candidate for slot {slot.index}: {slot.title}")
        return best_i

    def _choose_shell_anchor(self, slot, pool, unused, used_guild, used_region) -> int:
        trial = list(unused) if unused else list(range(len(pool)))
        if len(trial) > 1300:
            trial = list(self.rng.choice(trial, size=1300, replace=False))
        best_i, best_score = None, -1e18
        for raw_i in trial:
            i = int(raw_i)
            row = pool[i]
            truth = row["truth"]
            region = truth.get("macro_region", "other")
            guild = truth.get("guild_id")
            score = 1.6 * manifest.class_compatibility(slot, row)
            if slot.region_hint:
                score += 3.2 if region == slot.region_hint else -0.4
            if guild:
                score += 0.8 / (1 + used_guild[guild])
            score += 0.25 / (1 + used_region[region])
            score += self.rng.normal(0, 0.04)
            if score > best_score:
                best_i, best_score = i, float(score)
        if best_i is None:
            raise RuntimeError(f"No temporal anchor for slot {slot.index}: {slot.title}")
        return best_i


def player_record(record: Mapping[str, Any]) -> Dict[str, Any]:
    return temporal.player_record(record)


def _distribution_report(records: Sequence[Mapping[str, Any]], catalogue: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    direct = [row for row in records if row["truth"].get("manifest_binding") == "direct_copper_network"]
    cat_regions = Counter(row["truth"].get("macro_region", "other") for row in catalogue)
    sample_regions = Counter(row["truth"].get("macro_region", "other") for row in direct)
    total_cat = max(1, sum(cat_regions.values()))
    total_sample = max(1, sum(sample_regions.values()))
    region_error_l1 = sum(
        abs(sample_regions.get(region, 0) / total_sample - cat_regions.get(region, 0) / total_cat)
        for region in set(cat_regions) | set(sample_regions)
    )
    return {
        "direct_network_objects": len(direct),
        "catalogue_region_share": {k: round(v / total_cat, 5) for k, v in sorted(cat_regions.items())},
        "sample_region_share": {k: round(v / total_sample, 5) for k, v in sorted(sample_regions.items())},
        "region_distribution_l1_error": round(float(region_error_l1), 5),
    }


def build_dataset(
    manifest_path: Path,
    hypothesis_path: Path,
    out_dir: Path,
    seed: int = 1300,
    workshops: int = 3200,
    catalogue_cap: int = 30000,
) -> Dict[str, Any]:
    slots = [temporal.improved_slot(slot) for slot in manifest.parse_manifest(manifest_path)]
    if not slots:
        raise ValueError("Artifact manifest is empty.")
    hypothesis = json.loads(hypothesis_path.read_text(encoding="utf-8"))
    world = med.MediterraneanProvenanceWorld(hypothesis, seed=seed)
    world.build(workshop_count=workshops)
    generation = world.generate_archaeological_catalogue(max_materialized=catalogue_cap)
    compiler = DistributionalManifestCompiler(world, seed=seed)
    records = compiler.compile(slots)

    player = [player_record(row) for row in records]
    analyses = [{"object_id": row["object_id"], "manifest_index": row["manifest_index"], "tests": row["tests"]} for row in records]
    truth = [{"object_id": row["object_id"], "manifest_index": row["manifest_index"], "truth": row["truth"]} for row in records]
    findspots = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [row["findspot"]["lon"], row["findspot"]["lat"]]},
                "properties": {
                    "object_id": row["object_id"], "manifest_index": row["manifest_index"],
                    "name": row["display_name"], "level": row["curriculum_level"],
                },
            }
            for row in records
        ],
    }

    (out_dir / "player").mkdir(parents=True, exist_ok=True)
    (out_dir / "debug").mkdir(parents=True, exist_ok=True)
    (out_dir / "player" / "objects_300.json").write_text(json.dumps(player, indent=2, ensure_ascii=False), encoding="utf-8")
    (out_dir / "player" / "analyses_300.json").write_text(json.dumps(analyses, indent=2, ensure_ascii=False), encoding="utf-8")
    (out_dir / "player" / "findspots_300.geojson").write_text(json.dumps(findspots, indent=2, ensure_ascii=False), encoding="utf-8")
    (out_dir / "debug" / "truth_300.json").write_text(json.dumps(truth, indent=2, ensure_ascii=False), encoding="utf-8")
    (out_dir / "debug" / "jetbundles_truth.geojson").write_text(json.dumps(world.jetbundle_geojson(), indent=2), encoding="utf-8")
    (out_dir / "debug" / "guilds_truth.json").write_text(json.dumps(world.guild_truth(), indent=2), encoding="utf-8")

    relations = Counter(row["truth"].get("manifest_binding") for row in records)
    report = {
        "manifest": str(manifest_path),
        "seed": seed,
        "objects": len(records),
        "levels": len({row["curriculum_level"] for row in records}),
        "hidden_manufacture_use_events_est": generation["hidden_manufacture_use_events_est"],
        "catalogued_objects": generation["catalogued_objects"],
        "temporal_bindings": dict(relations),
        "distribution": _distribution_report(records, world.catalogue_truth),
        "anti_spoiler": {
            "hidden_checkpoint_target_exported": False,
            "true_jetbundle_exported": False,
            "true_guild_exported": False,
            "true_source_mix_exported": False,
        },
    }
    (out_dir / "debug" / "build_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a player-safe artifact dataset from any named manifest over the hidden Atolia provenance world.")
    parser.add_argument("--manifest", default="catalogues/archaeometallurgy_300_v0.txt")
    parser.add_argument("--hypothesis", default="hypotheses/atolia_atesis_1800_1000_v0.json")
    parser.add_argument("--out-dir", default="out/atolia_artifacts_v0")
    parser.add_argument("--seed", type=int, default=1300)
    parser.add_argument("--workshops", type=int, default=3200)
    parser.add_argument("--catalogue-cap", type=int, default=30000)
    args = parser.parse_args()
    report = build_dataset(Path(args.manifest), Path(args.hypothesis), Path(args.out_dir), args.seed, args.workshops, args.catalogue_cap)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
