from __future__ import annotations

import math
from collections import Counter
from typing import Any, Dict, Mapping

import numpy as np

import poari_career_router as poari_base
import poari_career_router_strict as strict
import procedural_sampler as procedural


ROUTER_VERSION = "poari-archaeology-v2"


class ArchaeologyPOARICareerSampler(strict.StrictPOARICareerSampler):
    """POARI career router where rarity is evidence opportunity, not spoiler.

    p=-1 remains the weak-dimension-sensitive lens. The semantic change is that
    early positive coordinates now reward exceptional survival + weakly recoverable
    structure while anti-spoiler estimates actual truth leakage at the tests
    available to the career level.
    """

    def prepare_candidates(self) -> None:
        super().prepare_candidates()
        # Catalogue shape remains a prior, but flatten it mildly so a 300-object
        # information career is not forced to be a miniature random survey.
        for axis, dist in self._career_targets.items():
            if not dist:
                continue
            keys = list(dist)
            arr = np.asarray([max(1e-9, float(dist[k])) ** 0.72 for k in keys], dtype=float)
            arr /= arr.sum()
            self._career_targets[axis] = {k: float(v) for k, v in zip(keys, arr)}

    @staticmethod
    def _phase(level: int) -> str:
        if level <= 8:
            return "early_tail"
        if level <= 18:
            return "middle_bridge"
        if level <= 25:
            return "late_recurrence"
        return "integrated"

    def _truth_leakage(self, slot: Any, c: procedural.Candidate) -> float:
        truth = c.row.get("truth", {})
        guild = float(truth.get("guild_strength", 0.0))
        entropy = float(truth.get("source_entropy", 0.0))
        crossings = min(1.0, float(truth.get("corridor_crossings", 0.0)) / 4.0)
        repair = min(1.0, float(truth.get("repair_count", 0.0)) / 3.0)
        tests = set(slot.required_tests)
        measurement_power = 0.10
        measurement_power += 0.16 * ("xrf" in tests)
        measurement_power += 0.25 * ("lead_isotopes" in tests)
        measurement_power += 0.18 * ("metallography" in tests)
        measurement_power += 0.18 * ("morphometrics" in tests)
        measurement_power += 0.13 * ("manufacturing_sequence" in tests)
        latent_structure = np.clip(0.35 * guild + 0.22 * entropy + 0.20 * crossings + 0.13 * repair + 0.10 * c.network_information, 0.0, 1.0)
        return float(np.clip(measurement_power * latent_structure, 0.0, 1.0))

    def _exceptional_loss_value(self, c: procedural.Candidate) -> float:
        truth = c.row.get("truth", {})
        exceptional = float(truth.get("exceptionality", 0.0))
        loss = float(truth.get("exceptional_loss_probability", 0.0))
        ret = float(truth.get("ordinary_return_probability", 0.5))
        tail = float(bool(truth.get("long_distance_tail", False)))
        return float(np.clip(0.48 * exceptional + 0.22 * tail + 0.18 * (1.0 - ret) + 0.12 * min(1.0, loss / 0.03), 0.0, 1.0))

    def _bridge_value(self, c: procedural.Candidate) -> float:
        truth = c.row.get("truth", {})
        crossings = min(1.0, float(truth.get("corridor_crossings", 0.0)) / 4.0)
        entropy = float(truth.get("source_entropy", 0.0))
        recycle = float(truth.get("recycle_fraction", 0.0))
        repair = min(1.0, float(truth.get("repair_count", 0.0)) / 3.0)
        tail = float(bool(truth.get("long_distance_tail", False)))
        return float(np.clip(0.34 * crossings + 0.22 * entropy + 0.18 * recycle + 0.14 * repair + 0.12 * tail, 0.0, 1.0))

    def _recoverability(self, slot: Any, c: procedural.Candidate) -> float:
        truth = c.row.get("truth", {})
        guild = float(truth.get("guild_strength", 0.0))
        entropy = float(truth.get("source_entropy", 0.0))
        recurrence = poari_base._sigmoid(1.25 * self._recurrence_score(slot, c))
        latent = float(np.clip(0.42 * guild + 0.23 * entropy + 0.35 * recurrence, 0.0, 1.0))
        leak = self._truth_leakage(slot, c)
        # Early: latent structure should exist but remain hard to read. Late:
        # measurement power is allowed to convert it into explicit recoverability.
        if slot.level <= 8:
            return float(np.clip(0.62 * latent + 0.38 * (1.0 - leak), 0.08, 1.0))
        return float(np.clip(0.60 * latent + 0.40 * leak, 0.08, 1.0))

    def _coherence_dimensions(self, slot: Any, c: procedural.Candidate) -> Dict[str, float]:
        dims = super()._coherence_dimensions(slot, c)
        leak = self._truth_leakage(slot, c)
        # Replace old rarity-as-spoiler semantics. The gate now asks whether the
        # currently available measurements make hidden structure too obvious.
        leak_budget = 0.18 + 0.022 * (slot.level - 1)
        dims["anti_spoiler"] = float(np.clip(math.exp(-5.0 * max(0.0, leak - leak_budget)), 0.05, 1.0))
        dims["exceptional_loss"] = max(0.08, self._exceptional_loss_value(c))
        dims["bridge"] = max(0.08, self._bridge_value(c))
        dims["recoverability"] = self._recoverability(slot, c)
        return dims

    def _hard_gate(self, slot: Any, c: procedural.Candidate, dims: Mapping[str, float]) -> float:
        # Keep pedagogical class/material innocence, but do not ban geographic
        # rarity or tail circulation in early levels.
        if slot.level <= 5:
            if c.object_class not in slot.allowed_classes:
                return 0.0
            if c.material_family not in slot.allowed_materials:
                return 0.0
        if dims["curriculum"] < .18 or dims["anti_spoiler"] < .10:
            return 0.0
        return 1.0

    @staticmethod
    def _dimension_weights(slot: Any) -> Dict[str, float]:
        phase = ArchaeologyPOARICareerSampler._phase(slot.level)
        if phase == "early_tail":
            return {
                "curriculum": .23,
                "anti_spoiler": .17,
                "archaeological": .08,
                "world_shape": .06,
                "recurrence": .04,
                "novelty": .08,
                "exceptional_loss": .17,
                "bridge": .05,
                "recoverability": .12,
            }
        if phase == "middle_bridge":
            return {
                "curriculum": .21,
                "anti_spoiler": .12,
                "archaeological": .08,
                "world_shape": .08,
                "recurrence": .10,
                "novelty": .06,
                "exceptional_loss": .08,
                "bridge": .17,
                "recoverability": .10,
            }
        if phase == "late_recurrence":
            return {
                "curriculum": .20,
                "anti_spoiler": .07,
                "archaeological": .07,
                "world_shape": .10,
                "recurrence": .20,
                "novelty": .05,
                "exceptional_loss": .04,
                "bridge": .12,
                "recoverability": .15,
            }
        return {
            "curriculum": .18,
            "anti_spoiler": .04,
            "archaeological": .06,
            "world_shape": .14,
            "recurrence": .22,
            "novelty": .04,
            "exceptional_loss": .03,
            "bridge": .10,
            "recoverability": .19,
        }

    def _candidate_world_shape_coherence(self, c: procedural.Candidate) -> float:
        # Preserve identity/coherence, but compare against mildly flattened
        # archaeological targets prepared above rather than raw catalogue shape.
        return super()._candidate_world_shape_coherence(c)

    def career_report(self) -> Dict[str, Any]:
        report = super().career_report()
        report["router_version"] = ROUTER_VERSION
        by_phase: Dict[str, list[procedural.Candidate]] = {}
        for slot in self.slots:
            by_phase.setdefault(self._phase(slot.level), []).append(self.selected_by_slot[slot.index])
        report["career_information_phases_truth"] = {}
        for phase, rows in by_phase.items():
            report["career_information_phases_truth"][phase] = {
                "objects": len(rows),
                "tail_share": round(float(np.mean([bool(c.row.get("truth", {}).get("long_distance_tail", False)) for c in rows])), 4),
                "mean_exceptionality": round(float(np.mean([float(c.row.get("truth", {}).get("exceptionality", 0.0)) for c in rows])), 4),
                "mean_corridor_crossings": round(float(np.mean([float(c.row.get("truth", {}).get("corridor_crossings", 0.0)) for c in rows])), 4),
                "mean_guild_strength": round(float(np.mean([float(c.row.get("truth", {}).get("guild_strength", 0.0)) for c in rows])), 4),
                "mean_source_entropy": round(float(np.mean([float(c.row.get("truth", {}).get("source_entropy", 0.0)) for c in rows])), 4),
            }
        return report
