from __future__ import annotations

import argparse
import json
import math
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Sequence, Tuple

import numpy as np

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import provenance_field as base
import provenance_field_mediterranean as med


@dataclass
class ArtifactSlot:
    index: int
    title: str
    level: int
    object_class: str
    material_family: str
    start_bc: int
    end_bc: int
    region_hint: str | None = None
    source_hint: str | None = None
    process_hints: Tuple[str, ...] = ()
    prestige: float = 0.0
    destructive_sampling_allowed: bool = True


MATERIAL_RULES: Sequence[Tuple[re.Pattern[str], str]] = [
    (re.compile(r"\b(gold|gilded|gold-foil|electrum|solidus)\b", re.I), "gold_precious"),
    (re.compile(r"\b(silver|billon|drachm|denarius|phiale|niello)\b", re.I), "silver_precious"),
    (re.compile(r"\b(iron|steel|seax|martens|pearlit|ferrit|bloom|forge-weld|carburi|quench)\b", re.I), "iron_steel"),
    (re.compile(r"\b(lead|litharge)\b", re.I), "lead"),
    (re.compile(r"\b(tin ingot|pewter|tin-lead)\b", re.I), "tin_pewter"),
    (re.compile(r"\b(brass|gunmetal|zinc)\b", re.I), "copper_zinc"),
    (re.compile(r"\b(bronze|tin-bronze|bell-bronze|high-tin)\b", re.I), "bronze"),
    (re.compile(r"\b(copper|malachite|chalcopyrite|matte|slag|smelting|prill|crucible|ore)\b", re.I), "copper"),
]

CLASS_RULES: Sequence[Tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bawl\b", re.I), "awl"),
    (re.compile(r"\bbead\b", re.I), "bead"),
    (re.compile(r"\bpin\b", re.I), "pin"),
    (re.compile(r"\bring\b|torque|bracelet", re.I), "ring"),
    (re.compile(r"\baxe\b|palstave|adze", re.I), "axe"),
    (re.compile(r"spear|arrowhead", re.I), "spearhead"),
    (re.compile(r"\bdagger\b", re.I), "dagger"),
    (re.compile(r"\bsword\b|seax", re.I), "sword"),
    (re.compile(r"\bknife\b|blade|razor|saw", re.I), "knife"),
    (re.compile(r"sickle", re.I), "sickle"),
    (re.compile(r"chisel|punch", re.I), "chisel"),
    (re.compile(r"vessel|cauldron|bowl|basin|bucket|plate|spoon|phiale|reliquary|cuirass|helmet", re.I), "vessel"),
    (re.compile(r"figurine", re.I), "figurine"),
    (re.compile(r"fibula|brooch|diadem|pendant|earring|mount|ornament|pommel|signet", re.I), "ornament"),
    (re.compile(r"ingot|casting cake|bar stock|billet|charge", re.I), "ingot"),
    (re.compile(r"slag|matte|prill|sprue|runner|crucible|accretion|ore fragment|nugget", re.I), "scrap"),
    (re.compile(r"rivet|fitting|clamp|chain|pipe|seal|tablet|weight|wire|tube|solder", re.I), "fitting"),
]

PROCESS_WORDS = {
    "cast": "casting", "mould": "moulding", "lost-wax": "lost_wax", "hammer": "hammering",
    "anneal": "annealing", "forge": "forging", "weld": "welding", "quench": "quenching",
    "carburi": "carburizing", "solder": "soldering", "braz": "brazing", "tinned": "tinning",
    "gild": "gilding", "inlaid": "inlay", "inlay": "inlay", "granulat": "granulation",
    "filigree": "filigree", "repouss": "repousse", "chased": "chasing", "planish": "planishing",
    "raised": "raising", "drawn": "drawing", "riveted": "riveting", "repair": "repair",
    "recycled": "recycling", "recast": "recycling", "metallograph": "metallography",
}

REGION_HINTS = {
    "cypriot": "cyprus", "cyprus": "cyprus", "cret": "crete", "aegean": "aegean",
    "anatolian": "hatti_anatolia", "hatti": "hatti_anatolia", "balkan": "lower_danube",
    "danube": "lower_danube", "sardinian": "western_mediterranean", "iberian": "western_mediterranean",
    "british": "severn_britain", "wales": "severn_britain", "rhone": "rhone", "rhine": "rhine",
    "alpine": "atolia_core", "mitterberg": "atolia_core", "trentino": "atolia_core",
    "central european": "rhine", "laurion": "aegean",
}

SOURCE_HINTS = {
    "cypriot": "cyprus_troodos", "troodos": "cyprus_troodos", "sardinian": "sardinia_westmed",
    "iberian": "iberia_westmed", "british": "british_wales", "mitterberg": "eastern_alps_external",
    "alpine": "trentino_east", "fahlore": "trentino_east", "anatolian": "anatolia_aegean",
    "balkan": "lower_danube_balkan", "danube": "lower_danube_balkan", "rhone": "western_alps_rhone",
    "rhine": "central_europe_rhine",
}


def infer_period(title: str, index: int) -> Tuple[int, int]:
    s = title.lower()
    # Explicitly later typologies first.
    if any(k in s for k in ("solidus", "reliquary", "medieval", "cloisonné sword pommel")):
        return 600, -1300  # 600 BC to AD 1300 represented with negative AD years
    if any(k in s for k in ("la tène", "certosa", "potin", "denarius", "fourrée", "stater", "drachm", "coin")):
        return 700, -400
    if any(k in s for k in ("pattern-welded", "piled-construction seax", "martensitic", "tempered-martensitic")):
        return 700, -1000
    if any(k in s for k in ("iron", "steel", "ferrite", "pearlite", "bloom", "carbur", "quench", "forge-weld")):
        return 1100, -1200
    if any(k in s for k in ("naue ii", "socketed", "urnfield", "frattesina", "rib ingot", "ösenring")):
        return 1400, 800
    if any(k in s for k in ("bronze", "tin-bronze", "palstave", "oxhide", "bell-bronze", "spearhead", "sickle")):
        return 1800, 900
    if any(k in s for k in ("arsenical", "native-copper", "malachite", "chalcopyrite", "copper awl", "copper bead")):
        return 3300, 1800
    # Curriculum index is a weak fallback only.
    if index <= 30:
        return 3300, 1800
    if index <= 150:
        return 2200, 900
    if index <= 230:
        return 1500, 300
    return 1300, -1200


def infer_slot(index: int, title: str) -> ArtifactSlot:
    material = "copper"
    for rx, value in MATERIAL_RULES:
        if rx.search(title):
            material = value
            break
    object_class = "fitting"
    for rx, value in CLASS_RULES:
        if rx.search(title):
            object_class = value
            break
    start_bc, end_bc = infer_period(title, index)
    lower = title.lower()
    process = tuple(sorted({value for key, value in PROCESS_WORDS.items() if key in lower}))
    region = next((value for key, value in REGION_HINTS.items() if key in lower), None)
    source = next((value for key, value in SOURCE_HINTS.items() if key in lower), None)
    prestige = 0.0
    for word, increment in (("gold", .35), ("silver", .22), ("ceremonial", .28), ("unique", .32),
                            ("museum", .28), ("gild", .15), ("gem", .18), ("sword", .10), ("figurine", .08)):
        if word in lower:
            prestige += increment
    no_destructive = any(k in lower for k in ("intact", "unique", "museum-grade", "no destructive", "mask", "diadem", "reliquary"))
    return ArtifactSlot(
        index=index, title=title, level=(index - 1) // 10 + 1, object_class=object_class,
        material_family=material, start_bc=start_bc, end_bc=end_bc, region_hint=region,
        source_hint=source, process_hints=process, prestige=min(1.0, prestige),
        destructive_sampling_allowed=not no_destructive,
    )


def parse_manifest(path: Path) -> List[ArtifactSlot]:
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        raw = json.loads(text)
        if isinstance(raw, dict):
            raw = raw.get("objects") or raw.get("artifacts") or raw.get("items") or []
        entries = []
        for i, item in enumerate(raw, 1):
            if isinstance(item, str):
                title = item
                index = i
            else:
                title = str(item.get("title") or item.get("name") or item.get("label") or f"Artifact {i}")
                index = int(item.get("index", i))
            entries.append(infer_slot(index, title))
        return entries
    slots = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        m = re.match(r"^(\d+)\s*[.):-]\s*(.+)$", line)
        if m:
            slots.append(infer_slot(int(m.group(1)), m.group(2).strip()))
        else:
            slots.append(infer_slot(len(slots) + 1, line))
    slots.sort(key=lambda s: s.index)
    return slots


def chronology_overlap(slot: ArtifactSlot, object_date_bc: int) -> float:
    hi = max(slot.start_bc, slot.end_bc)
    lo = min(slot.start_bc, slot.end_bc)
    if lo <= object_date_bc <= hi:
        return 1.0
    distance = min(abs(object_date_bc - lo), abs(object_date_bc - hi))
    return math.exp(-distance / 180.0)


def bronze_network_overlap(slot: ArtifactSlot) -> float:
    hi = max(slot.start_bc, slot.end_bc)
    lo = min(slot.start_bc, slot.end_bc)
    inter = max(0, min(hi, 1800) - max(lo, 1000))
    span = max(1, hi - lo)
    return float(np.clip(inter / span, 0.0, 1.0))


def material_compatibility(slot: ArtifactSlot, row: Mapping[str, Any]) -> float:
    cat = str(row.get("catalogue_material", "")).lower()
    material = slot.material_family
    if material in {"copper", "bronze", "copper_zinc", "tin_pewter", "lead"}:
        if material == "bronze" and "bronze" in cat:
            return 1.0
        if material == "copper" and "copper" in cat:
            return 1.0
        if material == "copper_zinc" and ("bronze" in cat or "copper" in cat):
            return 0.62
        if material in {"tin_pewter", "lead"} and ("bronze" in cat or "copper" in cat):
            return 0.35
        return 0.18
    # Iron/precious materials are descendant shells, not direct copper-object matches.
    return 0.25


def class_compatibility(slot: ArtifactSlot, row: Mapping[str, Any]) -> float:
    if row.get("class") == slot.object_class:
        return 1.0
    related = {
        "knife": {"dagger", "sword", "spearhead"},
        "sword": {"dagger", "knife"},
        "vessel": {"fitting", "ornament"},
        "ornament": {"ring", "pin", "fitting"},
        "fitting": {"scrap", "ingot", "vessel"},
        "ingot": {"scrap", "fitting"},
        "scrap": {"ingot", "fitting"},
    }
    return 0.55 if row.get("class") in related.get(slot.object_class, set()) else 0.16


class ManifestCompiler:
    def __init__(self, world: med.MediterraneanProvenanceWorld, seed: int = 1300):
        self.world = world
        self.rng = np.random.default_rng(seed ^ 0xA70A)

    def compile(self, slots: Sequence[ArtifactSlot]) -> List[Dict[str, Any]]:
        if not self.world.catalogue_truth:
            raise RuntimeError("Generate archaeological catalogue before manifest compilation.")
        pool = list(self.world.catalogue_truth)
        unused = set(range(len(pool)))
        compiled: List[Dict[str, Any]] = []
        guild_usage = Counter()
        region_usage = Counter()
        bundle_usage = Counter()

        for slot in slots:
            direct_weight = bronze_network_overlap(slot)
            if direct_weight > 0.15 and slot.material_family not in {"iron_steel", "gold_precious", "silver_precious"}:
                candidate_index = self._choose_candidate(slot, pool, unused, guild_usage, region_usage, bundle_usage)
                row = pool[candidate_index]
                unused.discard(candidate_index)
                record = self._project_direct(slot, row, direct_weight)
            else:
                anchor_index = self._choose_descendant_anchor(slot, pool, unused, guild_usage, region_usage)
                row = pool[anchor_index]
                # Do not consume a Bronze anchor for a later object every time: descendants can share ancestral lineages.
                record = self._project_descendant(slot, row)
            compiled.append(record)
            truth = record["truth"]
            if truth.get("guild_id"):
                guild_usage[truth["guild_id"]] += 1
            region_usage[truth.get("macro_region", "other")] += 1
            if truth.get("bundle_id"):
                bundle_usage[truth["bundle_id"]] += 1

        self._rebalance_peripheral(compiled, slots, pool)
        return compiled

    def _choose_candidate(self, slot, pool, unused, guild_usage, region_usage, bundle_usage) -> int:
        trial = list(unused)
        if len(trial) > 1400:
            trial = list(self.rng.choice(trial, size=1400, replace=False))
        best_i, best_score = None, -1e18
        for i in trial:
            row = pool[int(i)]
            truth = row["truth"]
            score = 3.1 * class_compatibility(slot, row)
            score += 2.7 * material_compatibility(slot, row)
            score += 2.0 * chronology_overlap(slot, int(row["date_center_bc"]))
            if slot.region_hint:
                score += 2.4 if truth.get("macro_region") == slot.region_hint else -0.45
            if slot.source_hint:
                score += 2.5 * float(truth.get("source_mix", {}).get(slot.source_hint, 0.0))
            guild = truth.get("guild_id")
            score += 0.55 / (1 + guild_usage[guild]) if guild else 0.0
            score += 0.25 / (1 + region_usage[truth.get("macro_region", "other")])
            score += 0.20 / (1 + bundle_usage[truth.get("bundle_id")])
            score += self.rng.normal(0, 0.045)
            if score > best_score:
                best_i, best_score = int(i), float(score)
        if best_i is None:
            raise RuntimeError(f"No candidate for artifact slot {slot.index}: {slot.title}")
        return best_i

    def _choose_descendant_anchor(self, slot, pool, unused, guild_usage, region_usage) -> int:
        trial = list(unused) if unused else list(range(len(pool)))
        if len(trial) > 1100:
            trial = list(self.rng.choice(trial, size=1100, replace=False))
        best_i, best_score = None, -1e18
        for i in trial:
            row = pool[int(i)]
            truth = row["truth"]
            score = 1.2 * class_compatibility(slot, row)
            guild = truth.get("guild_id")
            if guild:
                score += 1.25 / (1 + guild_usage[guild])
            if slot.region_hint:
                score += 1.6 if truth.get("macro_region") == slot.region_hint else 0.0
            score += 0.25 / (1 + region_usage[truth.get("macro_region", "other")])
            score += self.rng.normal(0, 0.05)
            if score > best_score:
                best_i, best_score = int(i), float(score)
        if best_i is None:
            raise RuntimeError(f"No descendant anchor for artifact slot {slot.index}")
        return best_i

    def _project_direct(self, slot: ArtifactSlot, row: Mapping[str, Any], direct_weight: float) -> Dict[str, Any]:
        result = json.loads(json.dumps(row))
        result["manifest_index"] = slot.index
        result["curriculum_level"] = slot.level
        result["display_name"] = slot.title
        result["class"] = slot.object_class
        result["manifest"] = self._manifest_public(slot)
        result["truth"]["manifest_binding"] = "direct_bronze_network"
        result["truth"]["bronze_network_coupling"] = round(direct_weight, 4)
        result["truth"]["material_family_requested"] = slot.material_family
        return result

    def _project_descendant(self, slot: ArtifactSlot, row: Mapping[str, Any]) -> Dict[str, Any]:
        result = json.loads(json.dumps(row))
        guild_id = result["truth"].get("guild_id")
        region = slot.region_hint or result["truth"].get("macro_region", "other")
        midpoint = int(round((slot.start_bc + slot.end_bc) / 2))
        if slot.end_bc < 0:
            midpoint = int(round((slot.start_bc + slot.end_bc) / 2))
        result["manifest_index"] = slot.index
        result["curriculum_level"] = slot.level
        result["display_name"] = slot.title
        result["class"] = slot.object_class
        result["catalogue_material"] = slot.material_family
        result["date_center_bc"] = midpoint
        result["date_uncertainty_years"] = max(35, int(abs(slot.start_bc - slot.end_bc) * 0.12))
        result["manifest"] = self._manifest_public(slot)
        result["tests"] = self._adapt_tests_for_material(slot, result.get("tests", {}))
        result["truth"] = {
            "manifest_binding": "descendant_technical_network",
            "ancestral_bronze_object_id": row["object_id"],
            "guild_id": guild_id,
            "guild_strength": result["truth"].get("guild_strength", 0.0),
            "macro_region": region,
            "lineage_id": result["truth"].get("lineage_id"),
            "technical_vector": result["truth"].get("technical_vector"),
            "bronze_network_coupling": 0.0,
            "direct_atesis_flux_relation": False,
            "historical_scope_note": "Uses inherited/descendant technical-network structure only; not a direct member of the 1800–1000 BC copper-flow world.",
            "material_family_requested": slot.material_family,
        }
        return result

    def _adapt_tests_for_material(self, slot: ArtifactSlot, tests: Mapping[str, Any]) -> Dict[str, Any]:
        out = json.loads(json.dumps(tests))
        if slot.material_family == "iron_steel":
            out.pop("lead_isotopes", None)
            out["metallography"] = {
                "matrix": str(self.rng.choice(["ferritic", "ferrite-pearlite", "pearlitic", "heterogeneous wrought iron"])),
                "slag_inclusion_index": round(float(self.rng.beta(2.1, 3.4)), 3),
                "carburization_index": round(float(self.rng.beta(1.8, 2.7)), 3),
                "heat_treatment_signal": bool(any(p in slot.process_hints for p in ("quenching", "carburizing"))),
            }
            out["xrf"] = {"Fe_pct": round(float(self.rng.uniform(96.0, 99.5)), 3), "P_pct": round(float(self.rng.uniform(0.03, 0.45)), 3)}
        elif slot.material_family == "gold_precious":
            out["xrf"] = {"Au_pct": round(float(self.rng.uniform(72, 99.6)), 3), "Ag_pct": round(float(self.rng.uniform(0.2, 25)), 3), "Cu_pct": round(float(self.rng.uniform(0.1, 4.0)), 3)}
            out.pop("lead_isotopes", None)
        elif slot.material_family == "silver_precious":
            ag = float(self.rng.uniform(55, 98.5))
            out["xrf"] = {"Ag_pct": round(ag, 3), "Cu_pct": round(float(99.2 - ag), 3), "Pb_pct": round(float(self.rng.uniform(0.02, 0.8)), 3)}
        elif slot.material_family == "lead":
            out["xrf"] = {"Pb_pct": round(float(self.rng.uniform(92, 99.8)), 3), "Sn_pct": round(float(self.rng.uniform(0.0, 4.0)), 3)}
        return out

    @staticmethod
    def _manifest_public(slot: ArtifactSlot) -> Dict[str, Any]:
        return {
            "title": slot.title,
            "requested_material_family": slot.material_family,
            "requested_period_bc": [slot.start_bc, slot.end_bc],
            "process_hints": list(slot.process_hints),
            "destructive_sampling_allowed": slot.destructive_sampling_allowed,
        }

    def _rebalance_peripheral(self, records: List[Dict[str, Any]], slots: Sequence[ArtifactSlot], pool: Sequence[Mapping[str, Any]]) -> None:
        # This pass preserves explicit regional titles but does not force hidden global structure into every item.
        explicit = [i for i, slot in enumerate(slots) if slot.region_hint and slot.region_hint != "atolia_core"]
        if not explicit:
            return
        by_region = defaultdict(list)
        for row in pool:
            by_region[row["truth"].get("macro_region", "other")].append(row)
        for i in explicit:
            slot = slots[i]
            if records[i]["truth"].get("macro_region") == slot.region_hint:
                continue
            candidates = by_region.get(slot.region_hint, [])
            if not candidates:
                continue
            anchor = candidates[int(self.rng.integers(0, len(candidates)))]
            if records[i]["truth"].get("manifest_binding") == "direct_bronze_network":
                records[i] = self._project_direct(slot, anchor, bronze_network_overlap(slot))
            else:
                records[i] = self._project_descendant(slot, anchor)


def player_record(record: Mapping[str, Any]) -> Dict[str, Any]:
    uncertainty = int(record["date_uncertainty_years"])
    center = int(record["date_center_bc"])
    return {
        "object_id": record["object_id"],
        "manifest_index": record["manifest_index"],
        "curriculum_level": record["curriculum_level"],
        "display_name": record["display_name"],
        "class": record["class"],
        "mass_kg": record.get("mass_kg"),
        "date_range_bc": [center + uncertainty, center - uncertainty],
        "findspot": record.get("findspot"),
        "hoard_id": record.get("hoard_id"),
        "preservation": record.get("preservation"),
        "catalogue_material": record.get("catalogue_material"),
        "manifest": record.get("manifest"),
        "available_tests": list(record.get("tests", {}).keys()),
    }


def compile_manifest(
    manifest_path: Path,
    hypothesis_path: Path,
    out_dir: Path,
    seed: int = 1300,
    workshops: int = 3200,
    catalogue_cap: int = 30000,
) -> Dict[str, Any]:
    slots = parse_manifest(manifest_path)
    if not slots:
        raise ValueError("Manifest contains no artifacts.")
    hypothesis = json.loads(hypothesis_path.read_text(encoding="utf-8"))
    world = med.MediterraneanProvenanceWorld(hypothesis, seed=seed)
    world.build(workshop_count=workshops)
    generation = world.generate_archaeological_catalogue(max_materialized=catalogue_cap)
    compiler = ManifestCompiler(world, seed=seed)
    records = compiler.compile(slots)

    player = [player_record(row) for row in records]
    analyses = [{"object_id": row["object_id"], "manifest_index": row["manifest_index"], "tests": row["tests"]} for row in records]
    truth = [{"object_id": row["object_id"], "manifest_index": row["manifest_index"], "truth": row["truth"]} for row in records]

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "player").mkdir(parents=True, exist_ok=True)
    (out_dir / "debug").mkdir(parents=True, exist_ok=True)
    (out_dir / "player" / "objects_manifest.json").write_text(json.dumps(player, indent=2, ensure_ascii=False), encoding="utf-8")
    (out_dir / "player" / "analyses_manifest.json").write_text(json.dumps(analyses, indent=2, ensure_ascii=False), encoding="utf-8")
    (out_dir / "debug" / "truth_manifest.json").write_text(json.dumps(truth, indent=2, ensure_ascii=False), encoding="utf-8")
    (out_dir / "debug" / "manifest_slots.json").write_text(json.dumps([asdict(slot) for slot in slots], indent=2, ensure_ascii=False), encoding="utf-8")

    binding_counts = Counter(row["truth"]["manifest_binding"] for row in records)
    region_counts = Counter(row["truth"].get("macro_region", "other") for row in records)
    guild_counts = Counter(row["truth"].get("guild_id") for row in records if row["truth"].get("guild_id"))
    report = {
        "seed": seed,
        "manifest_count": len(slots),
        "compiled_count": len(records),
        "levels": len({slot.level for slot in slots}),
        "binding_counts": dict(binding_counts),
        "region_counts_truth": dict(region_counts),
        "guilds_represented_truth": len(guild_counts),
        "hidden_manufacture_use_events_est": generation["hidden_manufacture_use_events_est"],
        "catalogued_objects": generation["catalogued_objects"],
        "anti_spoiler": {
            "player_export_contains_hidden_target": False,
            "player_export_contains_bundle_truth": False,
            "player_export_contains_guild_truth": False,
        },
    }
    (out_dir / "debug" / "manifest_validation.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Compile a named artifact manifest onto the hidden Atolia provenance world.")
    parser.add_argument("manifest")
    parser.add_argument("--hypothesis", default="hypotheses/atolia_atesis_1800_1000_v0.json")
    parser.add_argument("--out-dir", default="out/atolia_manifest_v0")
    parser.add_argument("--seed", type=int, default=1300)
    parser.add_argument("--workshops", type=int, default=3200)
    parser.add_argument("--catalogue-cap", type=int, default=30000)
    args = parser.parse_args()
    report = compile_manifest(Path(args.manifest), Path(args.hypothesis), Path(args.out_dir), args.seed, args.workshops, args.catalogue_cap)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
