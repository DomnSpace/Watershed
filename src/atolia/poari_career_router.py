from __future__ import annotations

import math
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Sequence

import numpy as np

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import curriculum_contract_v1 as contract_v1
import procedural_sampler as procedural


ROUTER_VERSION = "poari-career-router-v1"


def p_mean(values: Sequence[float], weights: Sequence[float] | None = None, p: float = 1.0, eps: float = 1e-8) -> float:
    """Weighted generalized mean on positive coherence coordinates.

    p=-1: harmonic/weak-dimension drag
    p=0 : geometric/log-Euclidean overlap
    p=1 : arithmetic accumulation
    p=2 : quadratic/hotspot permissiveness
    """
    x = np.clip(np.asarray(values, dtype=float), eps, 1.0)
    if len(x) == 0:
        return 0.0
    if weights is None:
        w = np.ones(len(x), dtype=float)
    else:
        w = np.asarray(weights, dtype=float)
    w = np.clip(w, 0.0, None)
    if w.sum() <= 0:
        w = np.ones(len(x), dtype=float)
    w = w / w.sum()
    if abs(p) < 1e-12:
        return float(math.exp(float(np.sum(w * np.log(x)))))
    return float(np.clip(np.sum(w * np.power(x, p)), eps, 1.0) ** (1.0 / p))


def p_for_level(level: int) -> float:
    if level <= 8:
        return -1.0
    if level <= 18:
        return 0.0
    if level <= 25:
        return 1.0
    return 2.0


def _smooth_match(delta: float, scale: float) -> float:
    return float(math.exp(-abs(float(delta)) / max(1e-8, float(scale))))


def _range_coherence(value: float, low: float, high: float, softness: float = .12) -> float:
    if low <= value <= high:
        return 1.0
    distance = low - value if value < low else value - high
    return float(math.exp(-distance / max(softness, 1e-6)))


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-max(-24.0, min(24.0, x))))


class POARICareerSampler(procedural.ProceduralCareerSampler):
    """p-Measure Ordered Action-Routing Intelligence for the 300-object career.

    Phi_t : the archaeological catalogue as a possibility field.
    G_t   : source/bundle/workshop/guild/hoard graph inherited from the world.
    pi_t  : slot-by-slot action policy over surviving artefact candidates.
    theta : curriculum, p schedule, target distributions, recurrence and spoiler gates.

    Ingression proposes candidate support, Concretion updates route measure through
    selected-count commitments, and Involution performs an identity-preserving
    post-selection rewrite of independent slots to improve world-shape coherence.
    """

    def __init__(self, *args: Any, involution_passes: int = 2, involution_trials: int = 42, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self.involution_passes = int(max(0, involution_passes))
        self.involution_trials = int(max(4, involution_trials))
        self.route_trace: list[Dict[str, Any]] = []
        self.pre_involution_shape: Dict[str, Any] | None = None
        self.post_involution_shape: Dict[str, Any] | None = None

    # ---------- POARI route selection ----------

    def _select_for_slot(self, slot: contract_v1.CurriculumSlot, unused: set[str]) -> procedural.Candidate:
        candidates = self._ingress(slot, unused)
        best: procedural.Candidate | None = None
        best_score = -1e18
        best_dims: Dict[str, float] | None = None
        for candidate in candidates:
            dims = self._coherence_dimensions(slot, candidate)
            if self._hard_gate(slot, candidate, dims) <= 0:
                continue
            weights = self._dimension_weights(slot)
            p = p_for_level(slot.level)
            routed = p_mean([dims[name] for name in weights], [weights[name] for name in weights], p=p)
            # A small amount of the existing detailed heuristic remains as a
            # tie-breaker; the generalized p-measure is the dominant router.
            legacy = self._slot_score(slot, candidate)
            tie = .018 * math.tanh(legacy / 4.0)
            score = routed + tie + float(self.rng.normal(0.0, .0025))
            if score > best_score:
                best, best_score, best_dims = candidate, score, dims
        if best is None:
            # Relax only after the strict possibility field is exhausted.
            best = super()._select_for_slot(slot, unused)
            best_dims = self._coherence_dimensions(slot, best)
            best_score = p_mean(list(best_dims.values()), p=p_for_level(slot.level))
        self.route_trace.append({
            "slot": slot.index,
            "level": slot.level,
            "p": p_for_level(slot.level),
            "object_id": best.object_id,
            "route_measure": round(float(best_score), 6),
            "dimensions": {k: round(float(v), 5) for k, v in sorted((best_dims or {}).items())},
        })
        return best

    def _ingress(self, slot: contract_v1.CurriculumSlot, unused: set[str]) -> list[procedural.Candidate]:
        """Free projection / support expansion before coherence routing."""
        candidates = [c for c in self.candidates if c.object_id in unused]
        if not candidates:
            candidates = list(self.candidates)
        # Keep the archaeological catalogue itself as proposal measure, while
        # preserving a small random exploration channel to avoid deterministic
        # collapse onto the same obvious candidate family.
        if len(candidates) > 2400:
            base_n = 2050
            idx = self.rng.choice(len(candidates), size=base_n, replace=False)
            proposal = [candidates[int(i)] for i in idx]
            # Add candidates with explicit class/material compatibility so rare
            # curriculum slots are not lost in the random support slice.
            compatible = [
                c for c in candidates
                if c.object_class in slot.allowed_classes and c.material_family in slot.allowed_materials
            ]
            if len(compatible) > 350:
                cidx = self.rng.choice(len(compatible), size=350, replace=False)
                compatible = [compatible[int(i)] for i in cidx]
            seen = {c.object_id for c in proposal}
            proposal.extend(c for c in compatible if c.object_id not in seen)
            return proposal
        return candidates

    def _hard_gate(self, slot: contract_v1.CurriculumSlot, c: procedural.Candidate, dims: Mapping[str, float]) -> float:
        if slot.level <= 5:
            if c.spoiler > slot.max_spoiler + .075:
                return 0.0
            if c.object_class not in slot.allowed_classes:
                return 0.0
            if c.material_family not in slot.allowed_materials:
                return 0.0
        if dims["curriculum"] < .18 or dims["anti_spoiler"] < .10:
            return 0.0
        return 1.0

    def _coherence_dimensions(self, slot: contract_v1.CurriculumSlot, c: procedural.Candidate) -> Dict[str, float]:
        available_tests = set(c.row.get("tests", {}).keys())
        required_tests = set(slot.required_tests)
        test_match = 1.0 if not required_tests else len(available_tests & required_tests) / len(required_tests)
        class_match = 1.0 if c.object_class in slot.allowed_classes else .16
        material_match = 1.0 if c.material_family in slot.allowed_materials else .20
        difficulty_match = _smooth_match(c.difficulty - slot.target_difficulty, .19)
        curriculum = p_mean(
            [class_match, material_match, max(.12, test_match), difficulty_match],
            [.29, .25, .20, .26],
            p=-1.0 if slot.level <= 8 else 0.0,
        )

        if c.spoiler <= slot.max_spoiler:
            anti_spoiler = 1.0
        else:
            anti_spoiler = math.exp(-8.0 * (c.spoiler - slot.max_spoiler))

        network = _range_coherence(
            c.network_information,
            slot.min_network_information,
            slot.max_network_information,
            softness=.15,
        )
        expected_background = float(slot.background_probability)
        observed_background = 1.0 if c.background else 0.0
        background = 1.0 - .55 * abs(observed_background - expected_background)
        hoard = _sigmoid(1.35 + 1.3 * self._hoard_score(slot, c))
        archaeological = p_mean([network, background, hoard], [.44, .34, .22], p=0.0)

        world_shape = self._candidate_world_shape_coherence(c)
        recurrence = _sigmoid(1.25 * self._recurrence_score(slot, c))
        # Novelty is deliberately weak: uniqueness must not flatten the actual
        # distribution into one specimen from every hidden category.
        same_class = self._selected_counts["class"][c.object_class]
        same_source = self._selected_counts["source"][c.dominant_source]
        novelty = float(np.clip(.90 / (1.0 + .025 * same_class + .012 * same_source), .28, .96))
        return {
            "curriculum": float(curriculum),
            "anti_spoiler": float(np.clip(anti_spoiler, 0.0, 1.0)),
            "archaeological": float(archaeological),
            "world_shape": float(world_shape),
            "recurrence": float(recurrence),
            "novelty": float(novelty),
        }

    @staticmethod
    def _dimension_weights(slot: contract_v1.CurriculumSlot) -> Dict[str, float]:
        early = max(0.0, 1.0 - (slot.level - 1) / 29.0)
        late = 1.0 - early
        return {
            "curriculum": .30,
            "anti_spoiler": .28 * early + .10 * late,
            "archaeological": .18,
            "world_shape": .15,
            "recurrence": .05 * early + .20 * late,
            "novelty": .04 + .07 * late,
        }

    def _candidate_world_shape_coherence(self, c: procedural.Candidate) -> float:
        axes = [
            ("region", c.region),
            ("bundle", c.bundle_id or "none"),
            ("source", c.dominant_source),
            ("class", c.object_class),
        ]
        coords = []
        for kind, value in axes:
            target = float(self._career_targets.get(kind, {}).get(value, 0.0))
            used = float(self._selected_counts[kind][value])
            predicted = used + 1.0
            scale = max(1.5, target * .65 + .75)
            if predicted <= target:
                coherence = .82 + .18 * min(1.0, (target - used) / scale)
            else:
                coherence = math.exp(-(predicted - target) / scale)
            coords.append(float(np.clip(coherence, .05, 1.0)))
        return p_mean(coords, p=0.0)

    # ---------- Concretion and Involution ----------

    def sample(self) -> list[Dict[str, Any]]:
        player = super().sample()
        self.pre_involution_shape = self.world_shape_diagnostics()
        if self.involution_passes > 0:
            self._involution_rewrite()
            player = [self._project_player_object(slot, self.selected_by_slot[slot.index]) for slot in self.slots]
        self.post_involution_shape = self.world_shape_diagnostics()
        return player

    def _rebuild_selected_state(self) -> None:
        self.selected = [self.selected_by_slot[slot.index] for slot in self.slots]
        self._selected_counts = {
            "region": Counter(), "bundle": Counter(), "source": Counter(),
            "guild": Counter(), "class": Counter(), "hoard": Counter(),
        }
        self._recurrence_anchors = {}
        for slot in self.slots:
            candidate = self.selected_by_slot[slot.index]
            self._register(candidate)
            self._update_recurrence_anchor(slot, candidate)

    def _involution_rewrite(self) -> None:
        """Identity-preserving rewrite: same slots, more coherent world-shape.

        Only independent/background slots are swapped. Recurrence anchors and
        deliberately planted false friends remain fixed, preserving the player's
        inferential structure while improving the sampled world's distribution.
        """
        for _ in range(self.involution_passes):
            changed = False
            current_score = self._global_coherence_score()
            used_ids = {candidate.object_id for candidate in self.selected_by_slot.values()}
            order = list(self.slots)
            self.rng.shuffle(order)
            for slot in order:
                if slot.recurrence_role not in {"independent", "background"}:
                    continue
                old = self.selected_by_slot[slot.index]
                alternatives = [
                    c for c in self.candidates
                    if c.object_id not in used_ids
                    and (c.object_class in slot.allowed_classes or slot.level > 8)
                    and (c.material_family in slot.allowed_materials or slot.level > 12)
                ]
                if not alternatives:
                    continue
                if len(alternatives) > self.involution_trials:
                    idx = self.rng.choice(len(alternatives), size=self.involution_trials, replace=False)
                    alternatives = [alternatives[int(i)] for i in idx]
                best = old
                best_score = current_score
                for candidate in alternatives:
                    dims = self._coherence_dimensions(slot, candidate)
                    if self._hard_gate(slot, candidate, dims) <= 0:
                        continue
                    self.selected_by_slot[slot.index] = candidate
                    self._rebuild_selected_state()
                    global_score = self._global_coherence_score()
                    local_score = p_mean(
                        list(dims.values()),
                        [self._dimension_weights(slot).get(k, 1.0) for k in dims],
                        p=p_for_level(slot.level),
                    )
                    combined = .84 * global_score + .16 * local_score
                    if combined > best_score + .0015:
                        best, best_score = candidate, combined
                    self.selected_by_slot[slot.index] = old
                    self._rebuild_selected_state()
                if best.object_id != old.object_id:
                    used_ids.discard(old.object_id)
                    used_ids.add(best.object_id)
                    self.selected_by_slot[slot.index] = best
                    self._rebuild_selected_state()
                    current_score = self._global_coherence_score()
                    changed = True
            if not changed:
                break

    def _axis_coherence(self, kind: str) -> float:
        targets = self._career_targets.get(kind, {})
        if not targets:
            return 1.0
        n = max(1.0, float(len(self.selected_by_slot)))
        target_total = max(1e-9, sum(targets.values()))
        names = set(targets) | set(self._selected_counts[kind])
        tv = 0.0
        for name in names:
            p_target = float(targets.get(name, 0.0)) / target_total
            p_seen = float(self._selected_counts[kind][name]) / n
            tv += abs(p_seen - p_target)
        return float(np.clip(1.0 - .5 * tv, .001, 1.0))

    def world_shape_diagnostics(self) -> Dict[str, Any]:
        axes = {
            kind: self._axis_coherence(kind)
            for kind in ("region", "bundle", "source", "class")
        }
        values = list(axes.values())
        lenses = {
            "p_minus_1_harmonic": p_mean(values, p=-1.0),
            "p_0_geometric": p_mean(values, p=0.0),
            "p_1_arithmetic": p_mean(values, p=1.0),
            "p_2_quadratic": p_mean(values, p=2.0),
        }
        return {
            "axis_coherence": {k: round(float(v), 6) for k, v in axes.items()},
            "quasinorm_lenses": {k: round(float(v), 6) for k, v in lenses.items()},
        }

    def _global_coherence_score(self) -> float:
        diagnostics = self.world_shape_diagnostics()["quasinorm_lenses"]
        # Geometric overlap is the default world-shape notion, while the harmonic
        # lens keeps one badly distorted dimension from being hidden by the rest.
        return float(.65 * diagnostics["p_0_geometric"] + .35 * diagnostics["p_minus_1_harmonic"])

    def career_report(self) -> Dict[str, Any]:
        report = super().career_report()
        report["poari"] = {
            "router_version": ROUTER_VERSION,
            "canonical_tuple": "M_t=(Phi_t,G_t,pi_t,theta_t)",
            "p_schedule": {"levels_1_8": -1, "levels_9_18": 0, "levels_19_25": 1, "levels_26_30": 2},
            "pre_involution_world_shape": self.pre_involution_shape,
            "post_involution_world_shape": self.post_involution_shape,
            "route_trace_length": len(self.route_trace),
        }
        return report

    def debug_route_trace(self) -> list[Dict[str, Any]]:
        return list(self.route_trace)
