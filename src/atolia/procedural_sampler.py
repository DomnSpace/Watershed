from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from collections import Counter, defaultdict
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Sequence, Tuple

import numpy as np

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import artifact_manifest as manifest
import artifact_manifest_temporal as temporal
import curriculum_contract_v1 as contract_v1
import guild_model
import provenance_field_mediterranean as med


GENERATOR_VERSION = "archaeometallurgy-procedural-v1"


@dataclass(frozen=True)
class SeedBundle:
    world_seed: int
    archaeology_seed: int
    career_seed: int
    measurement_seed: int

    @classmethod
    def from_master(cls, master_seed: int) -> "SeedBundle":
        def derive(label: str) -> int:
            digest = hashlib.sha256(f"{master_seed}:{label}".encode("utf-8")).digest()
            return int.from_bytes(digest[:8], "big") & 0x7FFFFFFF
        return cls(
            world_seed=derive("world"),
            archaeology_seed=derive("archaeology"),
            career_seed=derive("career"),
            measurement_seed=derive("measurement"),
        )


@dataclass
class Candidate:
    row: Dict[str, Any]
    object_id: str
    object_class: str
    material_family: str
    difficulty: float
    spoiler: float
    network_information: float
    background: bool
    region: str
    bundle_id: str | None
    dominant_source: str
    guild_vector: Dict[str, float]
    guild_events: List[Dict[str, Any]]
    observability: Dict[str, float]
    hoard_id: str | None


class ProceduralCareerSampler:
    def __init__(
        self,
        world: med.MediterraneanProvenanceWorld,
        seeds: SeedBundle,
        slots: Sequence[contract_v1.CurriculumSlot] | None = None,
    ):
        self.world = world
        self.seeds = seeds
        self.slots = list(slots or contract_v1.build_contract())
        self.rng = np.random.default_rng(seeds.career_seed)
        self.measurement_rng = np.random.default_rng(seeds.measurement_seed)
        self.candidates: List[Candidate] = []
        self.selected: List[Candidate] = []
        self.selected_by_slot: Dict[int, Candidate] = {}
        self._candidate_by_id: Dict[str, Candidate] = {}
        self._career_targets: Dict[str, Dict[str, float]] = {}
        self._selected_counts: Dict[str, Counter] = {
            "region": Counter(), "bundle": Counter(), "source": Counter(), "guild": Counter(), "class": Counter(), "hoard": Counter(),
        }
        self._recurrence_anchors: Dict[str, Candidate] = {}

    def prepare_candidates(self) -> None:
        if not self.world.catalogue_truth:
            raise RuntimeError("World has no archaeological catalogue. Generate it before sampling a career.")
        self.candidates = [self._candidate_from_row(row) for row in self.world.catalogue_truth]
        self._candidate_by_id = {candidate.object_id: candidate for candidate in self.candidates}
        self._career_targets = self._draw_distribution_targets(self.candidates, len(self.slots))

    def _candidate_from_row(self, source_row: Mapping[str, Any]) -> Candidate:
        row = deepcopy(source_row)
        truth = row.setdefault("truth", {})
        workshop = self._workshop_by_id(truth.get("workshop_id"))
        if workshop is not None:
            affinities = guild_model.workshop_affinities(self.world, workshop)
        else:
            affinities = {guild_id: 0.0 for guild_id in guild_model.GUILD_PROFILES}
            guild_id = truth.get("guild_id")
            if guild_id in affinities:
                affinities[guild_id] = max(.25, float(truth.get("guild_strength", .35)))

        sequence = row.get("tests", {}).get("manufacturing_sequence", [])
        recycle = float(truth.get("recycle_fraction", 0.0))
        repair_count = int(truth.get("repair_count", 0))
        events = guild_model.build_event_biography(
            affinities=affinities,
            sequence=sequence,
            object_class=str(row.get("class", "fitting")),
            date_bc=int(row.get("date_center_bc", 1300)),
            relation="direct_copper_network",
            recycle_fraction=recycle,
            repair_count=repair_count,
            rng=self.rng,
        )
        guild_vector = guild_model.guild_vector_from_events(events)
        observability = guild_model.observability(events)
        truth["guild_affinity_vector"] = {k: round(float(v), 4) for k, v in affinities.items()}
        truth["guild_events"] = events
        truth["guild_event_vector"] = {k: round(float(v), 4) for k, v in guild_vector.items()}
        truth["guild_observability"] = observability

        material_family = self._material_family(row)
        dominant_source = self._dominant_source(truth)
        region = str(truth.get("macro_region", "other"))
        bundle_id = truth.get("bundle_id")
        background = self._is_background_candidate(row, guild_vector)
        difficulty = self._difficulty(row, guild_vector, observability)
        network_information = self._network_information(row, guild_vector)
        spoiler = self._spoiler_score(row, guild_vector, network_information)
        return Candidate(
            row=row,
            object_id=str(row["object_id"]),
            object_class=str(row.get("class", "fitting")),
            material_family=material_family,
            difficulty=difficulty,
            spoiler=spoiler,
            network_information=network_information,
            background=background,
            region=region,
            bundle_id=str(bundle_id) if bundle_id else None,
            dominant_source=dominant_source,
            guild_vector=guild_vector,
            guild_events=events,
            observability=observability,
            hoard_id=row.get("hoard_id"),
        )

    def _workshop_by_id(self, workshop_id: str | None):
        if not workshop_id:
            return None
        for workshop in self.world.workshops:
            if workshop.id == workshop_id:
                return workshop
        return None

    @staticmethod
    def _material_family(row: Mapping[str, Any]) -> str:
        cat = str(row.get("catalogue_material", "")).lower()
        if "bronze" in cat:
            return "bronze"
        if "brass" in cat or "gunmetal" in cat:
            return "copper_zinc"
        if "copper" in cat:
            return "copper"
        if "lead" in cat:
            return "lead"
        if "pewter" in cat or "tin" in cat:
            return "tin_pewter"
        return "copper"

    @staticmethod
    def _dominant_source(truth: Mapping[str, Any]) -> str:
        mix = truth.get("source_mix") or {}
        return max(mix, key=mix.get) if mix else "unknown"

    def _is_background_candidate(self, row: Mapping[str, Any], guild_vector: Mapping[str, float]) -> bool:
        truth = row.get("truth", {})
        source_entropy = float(truth.get("source_entropy", 0.0))
        complexity = float(truth.get("complexity", 0.0))
        recurrence_strength = max(guild_vector.values(), default=0.0)
        long_tail = bool(truth.get("long_distance_tail", False))
        score = 0.52 * complexity + 0.22 * source_entropy + 0.18 * recurrence_strength + 0.08 * float(long_tail)
        return score < .32

    @staticmethod
    def _difficulty(row: Mapping[str, Any], guild_vector: Mapping[str, float], observability: Mapping[str, float]) -> float:
        truth = row.get("truth", {})
        complexity = float(truth.get("complexity", 0.0))
        source_entropy = float(truth.get("source_entropy", 0.0))
        repair = min(1.0, float(truth.get("repair_count", 0)) / 2.0)
        guild_entropy = _normalized_entropy(list(guild_vector.values()))
        visible = max(observability.values(), default=.15)
        ambiguity = 1.0 - min(1.0, visible)
        score = .35 * complexity + .22 * source_entropy + .16 * repair + .17 * guild_entropy + .10 * ambiguity
        return float(np.clip(score, .01, .99))

    @staticmethod
    def _network_information(row: Mapping[str, Any], guild_vector: Mapping[str, float]) -> float:
        truth = row.get("truth", {})
        tail = float(bool(truth.get("long_distance_tail", False)))
        region = str(truth.get("macro_region", "other"))
        region_rarity = 0.0 if region == "atolia_core" else .35
        source_entropy = float(truth.get("source_entropy", 0.0))
        guild_strength = max(guild_vector.values(), default=0.0)
        recycle = float(truth.get("recycle_fraction", 0.0))
        return float(np.clip(.22 * source_entropy + .28 * guild_strength + .23 * tail + .14 * region_rarity + .13 * recycle, 0.0, 1.0))

    @staticmethod
    def _spoiler_score(row: Mapping[str, Any], guild_vector: Mapping[str, float], network_information: float) -> float:
        truth = row.get("truth", {})
        mix = truth.get("source_mix") or {}
        dominant = max(mix.values(), default=0.0)
        rare_region = .30 if truth.get("macro_region") not in {None, "atolia_core"} else 0.0
        bundle_specificity = .16 if truth.get("long_distance_tail") else .05
        guild_specificity = .22 * max(guild_vector.values(), default=0.0)
        return float(np.clip(.32 * network_information + .20 * dominant + rare_region + bundle_specificity + guild_specificity, 0.0, 1.0))

    def _draw_distribution_targets(self, candidates: Sequence[Candidate], n: int) -> Dict[str, Dict[str, float]]:
        out: Dict[str, Dict[str, float]] = {}
        mappings = {
            "region": [c.region for c in candidates],
            "bundle": [c.bundle_id or "none" for c in candidates],
            "source": [c.dominant_source for c in candidates],
            "class": [c.object_class for c in candidates],
        }
        for key, values in mappings.items():
            counts = Counter(values)
            names = sorted(counts)
            empirical = np.array([counts[name] for name in names], dtype=float)
            empirical /= empirical.sum()
            # Dirichlet perturbation preserves incidence while allowing each career
            # to look like a real sample rather than an exact miniature catalogue.
            concentration = 85.0 if key == "region" else 55.0 if key == "source" else 35.0
            alpha = np.maximum(.08, empirical * concentration)
            sample = self.rng.dirichlet(alpha)
            out[key] = {name: float(n * p) for name, p in zip(names, sample)}
        return out

    def sample(self) -> List[Dict[str, Any]]:
        if not self.candidates:
            self.prepare_candidates()
        unused = {candidate.object_id for candidate in self.candidates}
        for slot in self.slots:
            candidate = self._select_for_slot(slot, unused)
            self.selected.append(candidate)
            self.selected_by_slot[slot.index] = candidate
            unused.discard(candidate.object_id)
            self._register(candidate)
            self._update_recurrence_anchor(slot, candidate)
        return [self._project_player_object(slot, self.selected_by_slot[slot.index]) for slot in self.slots]

    def _select_for_slot(self, slot: contract_v1.CurriculumSlot, unused: set[str]) -> Candidate:
        candidates = [c for c in self.candidates if c.object_id in unused]
        if not candidates:
            candidates = list(self.candidates)
        # Proposal is drawn from the archaeological catalogue itself, preserving
        # the latent distribution before scoring constraints.
        if len(candidates) > 2200:
            indices = self.rng.choice(len(candidates), size=2200, replace=False)
            candidates = [candidates[int(i)] for i in indices]

        best, best_score = None, -1e18
        for candidate in candidates:
            score = self._slot_score(slot, candidate)
            if score > best_score:
                best, best_score = candidate, score
        if best is None:
            raise RuntimeError(f"No candidate for curriculum slot {slot.index}")
        return best

    def _slot_score(self, slot: contract_v1.CurriculumSlot, c: Candidate) -> float:
        score = 0.0
        score += 2.8 if c.object_class in slot.allowed_classes else -0.8
        score += 2.2 if c.material_family in slot.allowed_materials else -0.45
        score -= 3.2 * abs(c.difficulty - slot.target_difficulty)
        if c.spoiler > slot.max_spoiler:
            score -= 7.0 * (c.spoiler - slot.max_spoiler)
        if c.network_information < slot.min_network_information:
            score -= 2.8 * (slot.min_network_information - c.network_information)
        if c.network_information > slot.max_network_information:
            score -= 3.0 * (c.network_information - slot.max_network_information)

        background_target = slot.background_probability
        if c.background:
            score += 0.65 * background_target
        else:
            score += 0.25 * (1.0 - background_target)

        score += self._distribution_pressure("region", c.region, .52)
        score += self._distribution_pressure("bundle", c.bundle_id or "none", .38)
        score += self._distribution_pressure("source", c.dominant_source, .31)
        score += self._distribution_pressure("class", c.object_class, .21)
        score += self._recurrence_score(slot, c)
        score += self._hoard_score(slot, c)
        score += float(self.rng.normal(0.0, .025))
        return score

    def _distribution_pressure(self, kind: str, value: str, weight: float) -> float:
        target = self._career_targets.get(kind, {}).get(value, 0.0)
        used = self._selected_counts[kind][value]
        if target <= .05:
            return -weight * .12 * used
        deficit = (target - used) / max(1.0, target)
        return weight * float(np.clip(deficit, -1.2, 1.2))

    def _recurrence_score(self, slot: contract_v1.CurriculumSlot, c: Candidate) -> float:
        role = slot.recurrence_role
        if role in {"independent", "background"}:
            if not self._recurrence_anchors:
                return 0.0
            strongest = max((guild_model.guild_overlap(c.guild_events, anchor.guild_events) for anchor in self._recurrence_anchors.values()), default=0.0)
            return -0.30 * strongest

        key = "easy" if role == "easy_recurrence" else "medium" if role == "medium_recurrence" else "hard" if role == "hard_recurrence" else "false"
        anchor = self._recurrence_anchors.get(key)
        if anchor is None:
            return 0.15
        overlap = guild_model.guild_overlap(c.guild_events, anchor.guild_events)
        spatial_difference = 1.0 if c.region != anchor.region else 0.0
        source_difference = 1.0 if c.dominant_source != anchor.dominant_source else 0.0
        if role == "easy_recurrence":
            return 1.5 * overlap + .20 * spatial_difference
        if role == "medium_recurrence":
            return 1.2 * overlap + .42 * spatial_difference + .30 * source_difference
        if role == "hard_recurrence":
            return .90 * overlap + .65 * spatial_difference + .48 * source_difference - .22 * max(c.observability.values(), default=0.0)
        # false_friend: visual/morphometric resemblance but weak true guild overlap.
        if role == "false_friend":
            morph = _morphometric_similarity(c.row, anchor.row)
            return 1.25 * morph - 1.10 * overlap + .22 * spatial_difference
        return 0.0

    def _hoard_score(self, slot: contract_v1.CurriculumSlot, c: Candidate) -> float:
        if not c.hoard_id:
            return 0.0
        already = self._selected_counts["hoard"][c.hoard_id]
        if slot.level < 18:
            return -.12 * already
        if slot.level in {21, 26, 27}:
            return .38 if 0 < already < 5 else .05
        return .12 if already == 1 else -.05 * max(0, already - 3)

    def _register(self, c: Candidate) -> None:
        self._selected_counts["region"][c.region] += 1
        self._selected_counts["bundle"][c.bundle_id or "none"] += 1
        self._selected_counts["source"][c.dominant_source] += 1
        self._selected_counts["class"][c.object_class] += 1
        if c.hoard_id:
            self._selected_counts["hoard"][c.hoard_id] += 1
        for guild_id, strength in c.guild_vector.items():
            if strength >= .32:
                self._selected_counts["guild"][guild_id] += 1

    def _update_recurrence_anchor(self, slot: contract_v1.CurriculumSlot, c: Candidate) -> None:
        role = slot.recurrence_role
        if role == "easy_recurrence" and "easy" not in self._recurrence_anchors:
            self._recurrence_anchors["easy"] = c
        elif role == "medium_recurrence" and "medium" not in self._recurrence_anchors:
            self._recurrence_anchors["medium"] = c
        elif role == "hard_recurrence" and "hard" not in self._recurrence_anchors:
            self._recurrence_anchors["hard"] = c
        elif role == "false_friend" and "false" not in self._recurrence_anchors:
            self._recurrence_anchors["false"] = c

    def _project_player_object(self, slot: contract_v1.CurriculumSlot, c: Candidate) -> Dict[str, Any]:
        row = deepcopy(c.row)
        title = self._catalogue_title(slot, c)
        center = int(row["date_center_bc"])
        uncertainty = int(row.get("date_uncertainty_years", 60))
        return {
            "career_index": slot.index,
            "level": slot.level,
            "slot_in_level": slot.slot_in_level,
            "competency": slot.competency,
            "object_id": c.object_id,
            "display_name": title,
            "class": c.object_class,
            "catalogue_material": row.get("catalogue_material"),
            "mass_kg": row.get("mass_kg"),
            "date_range": {
                "older": temporal.human_year(center + uncertainty),
                "younger": temporal.human_year(center - uncertainty),
            },
            "findspot": row.get("findspot"),
            "hoard_id": row.get("hoard_id"),
            "preservation": row.get("preservation"),
            "sampling_policy": slot.destructive_sampling_policy,
            "available_tests": self._available_tests(slot, c),
        }

    def _catalogue_title(self, slot: contract_v1.CurriculumSlot, c: Candidate) -> str:
        base_name = str(c.row.get("display_name", c.object_class)).strip()
        # Early objects stay mundane. Later catalogue labels can carry cautious
        # descriptors, but never hidden network/guild terminology.
        if slot.level <= 4:
            simple = {
                "awl": "Copper-alloy awl",
                "bead": "Small copper-alloy bead",
                "pin": "Copper-alloy pin",
                "ring": "Simple copper-alloy ring",
                "fitting": "Small copper-alloy fitting",
            }
            return simple.get(c.object_class, base_name)
        qualifiers = []
        if c.row.get("preservation", "").startswith("fragmentary"):
            qualifiers.append("fragmentary")
        if slot.level >= 16 and int(c.row.get("truth", {}).get("repair_count", 0)) > 0:
            qualifiers.append("repaired")
        if slot.level >= 22 and c.row.get("truth", {}).get("surface_complexity", 0.0) > .65:
            qualifiers.append("surface-treated")
        if qualifiers:
            return f"{', '.join(qualifiers).capitalize()} {base_name}"
        return base_name

    def _available_tests(self, slot: contract_v1.CurriculumSlot, c: Candidate) -> List[str]:
        available = set(c.row.get("tests", {}).keys())
        available.update(slot.required_tests)
        if slot.destructive_sampling_policy == "forbidden":
            available.discard("destructive_section")
        return sorted(available)

    def player_analyses(self) -> List[Dict[str, Any]]:
        if not self.selected:
            raise RuntimeError("Sample career first.")
        return [self._measurement_payload(slot, self.selected_by_slot[slot.index]) for slot in self.slots]

    def _measurement_payload(self, slot: contract_v1.CurriculumSlot, c: Candidate) -> Dict[str, Any]:
        tests = deepcopy(c.row.get("tests", {}))
        rng = np.random.default_rng(_stable_subseed(self.seeds.measurement_seed, c.object_id))
        # Measurements are stable noisy observations of hidden truth, not a fresh
        # random reroll every time the player presses the same instrument button.
        if "xrf" in tests:
            xrf = dict(tests["xrf"])
            for key, value in list(xrf.items()):
                if isinstance(value, (int, float)):
                    rel_sigma = .018 if key.endswith("_pct") else .055
                    xrf[key] = round(max(0.0, float(value) * rng.normal(1.0, rel_sigma)), 4 if key.endswith("_pct") else 1)
            xrf["measurement_note"] = "Stable simulated surface measurement; systematic corrosion effects are not removed by rerunning the same test."
            tests["xrf"] = xrf
        if "lead_isotopes" in tests:
            iso = dict(tests["lead_isotopes"])
            for key, value in list(iso.items()):
                if isinstance(value, (int, float)):
                    iso[key] = round(float(value) + rng.normal(0.0, .0035), 5)
            tests["lead_isotopes"] = iso
        return {
            "career_index": slot.index,
            "object_id": c.object_id,
            "tests": tests,
        }

    def debug_truth(self) -> List[Dict[str, Any]]:
        if not self.selected:
            raise RuntimeError("Sample career first.")
        out = []
        for slot in self.slots:
            c = self.selected_by_slot[slot.index]
            truth = deepcopy(c.row.get("truth", {}))
            truth["guild_events"] = c.guild_events
            truth["guild_event_vector"] = c.guild_vector
            truth["guild_observability"] = c.observability
            truth["difficulty"] = round(c.difficulty, 4)
            truth["spoiler_score"] = round(c.spoiler, 4)
            truth["network_information"] = round(c.network_information, 4)
            truth["background_case"] = c.background
            truth["recurrence_role"] = slot.recurrence_role
            out.append({"career_index": slot.index, "object_id": c.object_id, "truth": truth})
        return out

    def career_report(self) -> Dict[str, Any]:
        if not self.selected:
            raise RuntimeError("Sample career first.")
        regions = Counter(c.region for c in self.selected)
        bundles = Counter(c.bundle_id or "none" for c in self.selected)
        sources = Counter(c.dominant_source for c in self.selected)
        classes = Counter(c.object_class for c in self.selected)
        background = sum(c.background for c in self.selected)
        recurrence_pairs = _recurrence_diagnostics(self.slots, self.selected_by_slot)
        return {
            "generator_version": GENERATOR_VERSION,
            "seeds": {
                "world_seed": self.seeds.world_seed,
                "archaeology_seed": self.seeds.archaeology_seed,
                "career_seed": self.seeds.career_seed,
                "measurement_seed": self.seeds.measurement_seed,
            },
            "objects": len(self.selected),
            "levels": len({slot.level for slot in self.slots}),
            "background_cases": int(background),
            "background_share": round(background / max(1, len(self.selected)), 4),
            "regions_truth": dict(sorted(regions.items())),
            "bundle_count_truth": len(bundles),
            "source_counts_truth": dict(sorted(sources.items())),
            "class_counts": dict(sorted(classes.items())),
            "guilds_represented_truth": len({g for c in self.selected for g, strength in c.guild_vector.items() if strength >= .32}),
            "recurrence_diagnostics_truth": recurrence_pairs,
            "anti_spoiler": {
                "player_export_contains_hidden_checkpoint_target": False,
                "player_export_contains_true_bundle": False,
                "player_export_contains_true_guild": False,
                "player_export_contains_true_source_mix": False,
                "level_1_max_spoiler_observed": round(max(c.spoiler for slot, c in zip(self.slots, self.selected) if slot.level == 1), 4),
            },
        }


def _normalized_entropy(values: Sequence[float]) -> float:
    arr = np.asarray([v for v in values if v > 0], dtype=float)
    if len(arr) <= 1:
        return 0.0
    arr /= arr.sum()
    return float(-np.sum(arr * np.log(arr)) / math.log(len(arr)))


def _morphometric_similarity(a: Mapping[str, Any], b: Mapping[str, Any]) -> float:
    ma = a.get("tests", {}).get("morphometrics", {})
    mb = b.get("tests", {}).get("morphometrics", {})
    keys = sorted(set(ma) & set(mb))
    if not keys:
        return 0.0
    dist = np.mean([abs(float(ma[k]) - float(mb[k])) for k in keys if isinstance(ma[k], (int, float)) and isinstance(mb[k], (int, float))])
    return float(math.exp(-4.0 * dist))


def _stable_subseed(seed: int, key: str) -> int:
    digest = hashlib.sha256(f"{seed}:{key}".encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") & 0x7FFFFFFF


def _recurrence_diagnostics(slots: Sequence[contract_v1.CurriculumSlot], selected_by_slot: Mapping[int, Candidate]) -> Dict[str, Any]:
    groups: Dict[str, List[Tuple[int, Candidate]]] = defaultdict(list)
    for slot in slots:
        if slot.recurrence_role in {"easy_recurrence", "medium_recurrence", "hard_recurrence", "false_friend"}:
            groups[slot.recurrence_role].append((slot.index, selected_by_slot[slot.index]))
    report = {}
    for role, entries in groups.items():
        overlaps = []
        for i in range(len(entries)):
            for j in range(i + 1, len(entries)):
                overlaps.append(guild_model.guild_overlap(entries[i][1].guild_events, entries[j][1].guild_events))
        report[role] = {
            "count": len(entries),
            "mean_true_guild_overlap": round(float(np.mean(overlaps)) if overlaps else 0.0, 4),
        }
    return report


def build_procedural_career(
    *,
    hypothesis_path: Path,
    out_dir: Path,
    master_seed: int = 1300,
    workshops: int = 3200,
    catalogue_cap: int = 30000,
) -> Dict[str, Any]:
    seeds = SeedBundle.from_master(master_seed)
    hypothesis = json.loads(hypothesis_path.read_text(encoding="utf-8"))

    # World and archaeology are separated conceptually. The current world engine
    # still uses one RNG internally, so archaeology_seed perturbs the catalogue
    # generation deterministically without changing public API semantics.
    world = med.MediterraneanProvenanceWorld(hypothesis, seed=seeds.world_seed)
    world.build(workshop_count=workshops)
    world.rng = np.random.default_rng(seeds.archaeology_seed)
    generation = world.generate_archaeological_catalogue(max_materialized=catalogue_cap)

    sampler = ProceduralCareerSampler(world, seeds)
    sampler.prepare_candidates()
    player_objects = sampler.sample()
    player_analyses = sampler.player_analyses()
    truth = sampler.debug_truth()
    report = sampler.career_report()
    report["hidden_manufacture_use_events_est"] = generation["hidden_manufacture_use_events_est"]
    report["catalogued_objects"] = generation["catalogued_objects"]

    (out_dir / "player").mkdir(parents=True, exist_ok=True)
    (out_dir / "debug").mkdir(parents=True, exist_ok=True)
    (out_dir / "player" / "objects_300.json").write_text(json.dumps(player_objects, indent=2, ensure_ascii=False), encoding="utf-8")
    (out_dir / "player" / "analyses_300.json").write_text(json.dumps(player_analyses, indent=2, ensure_ascii=False), encoding="utf-8")
    (out_dir / "player" / "curriculum_contract_v1.json").write_text(json.dumps(contract_v1.as_jsonable(), indent=2), encoding="utf-8")
    (out_dir / "debug" / "truth_300.json").write_text(json.dumps(truth, indent=2, ensure_ascii=False), encoding="utf-8")
    (out_dir / "debug" / "career_report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    (out_dir / "debug" / "jetbundles_truth.geojson").write_text(json.dumps(world.jetbundle_geojson(), indent=2), encoding="utf-8")
    (out_dir / "debug" / "guilds_truth.json").write_text(json.dumps(world.guild_truth(), indent=2), encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate one unique 300-object Dr. Corrosion archaeometallurgy career.")
    parser.add_argument("--hypothesis", default="hypotheses/atolia_atesis_1800_1000_v0.json")
    parser.add_argument("--out-dir", default="out/atolia_procedural_career_v1")
    parser.add_argument("--seed", type=int, default=1300, help="Master seed. Four deterministic sub-seeds are derived from it.")
    parser.add_argument("--workshops", type=int, default=3200)
    parser.add_argument("--catalogue-cap", type=int, default=30000)
    args = parser.parse_args()
    report = build_procedural_career(
        hypothesis_path=Path(args.hypothesis),
        out_dir=Path(args.out_dir),
        master_seed=args.seed,
        workshops=args.workshops,
        catalogue_cap=args.catalogue_cap,
    )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
