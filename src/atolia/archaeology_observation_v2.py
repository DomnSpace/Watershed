from __future__ import annotations

import math
from collections import Counter, defaultdict
from typing import Any, Dict, Mapping, Sequence

import numpy as np

import provenance_field as base
import provenance_field_mediterranean as med


OBSERVATION_MODEL_VERSION = "archaeology-observation-v2"

# These are archaeological observation priors, not production priors.
# They deliberately enrich exceptional loss/deposition without changing hidden flux.
MODE_LOSS_MULTIPLIER: Dict[str, float] = {
    "founder_scrap_hoard": 0.42,
    "finished_object_hoard": 0.58,
    "selective_ritual_deposit": 1.55,
    "personal_wealth_deposit": 0.74,
    "grave_assemblage": 0.82,
    "settlement_loss": 0.82,
    "river_wetland_deposit": 1.85,
    "workshop_debris": 0.28,
    "catastrophic_abandonment": 1.75,
}

MODE_SURVIVAL_MULTIPLIER: Dict[str, float] = {
    "founder_scrap_hoard": 1.03,
    "finished_object_hoard": 1.05,
    "selective_ritual_deposit": 0.97,
    "personal_wealth_deposit": 1.00,
    "grave_assemblage": 0.94,
    "settlement_loss": 0.84,
    "river_wetland_deposit": 1.08,
    "workshop_debris": 0.76,
    "catastrophic_abandonment": 0.91,
}

MODE_DISCOVERY_MULTIPLIER: Dict[str, float] = {
    "founder_scrap_hoard": 1.28,
    "finished_object_hoard": 1.18,
    "selective_ritual_deposit": 0.82,
    "personal_wealth_deposit": 0.98,
    "grave_assemblage": 1.16,
    "settlement_loss": 1.04,
    "river_wetland_deposit": 0.48,
    "workshop_debris": 1.20,
    "catastrophic_abandonment": 1.34,
}

PRESTIGE_CLASSES = {"sword", "dagger", "ornament", "figurine", "vessel", "spearhead"}
BULK_RETURN_CLASSES = {"ingot", "scrap", "axe", "sickle", "chisel", "fitting"}
LIMINAL_NODE_KINDS = {"coast", "pass", "river", "hub"}


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-max(-24.0, min(24.0, float(x)))))


def _safe_entropy(mix: Mapping[str, float]) -> float:
    values = np.asarray([float(v) for v in mix.values() if float(v) > 0], dtype=float)
    if len(values) <= 1:
        return 0.0
    values /= values.sum()
    return float(-np.sum(values * np.log(values)) / math.log(len(values)))


class ArchaeologicalObservationWorld(med.MediterraneanProvenanceWorld):
    """Mediterranean provenance world with explicit archaeology observation stages.

    Hidden production/circulation remains inherited from the v1 world. This class
    only changes the route from use/circulation into the archaeologically visible
    catalogue, so low-incidence tails can be enriched by exceptional loss without
    becoming implausibly common in the hidden economy.
    """

    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self.archaeology_waterfall: Dict[str, Any] = {}

    # ---------- route / observation coordinates ----------

    def _route_metrics(self, bundle: base.JetBundle) -> Dict[str, float]:
        route = list(bundle.route)
        km = 0.0
        for a, b in zip(route[:-1], route[1:]):
            na, nb = self.nodes[a], self.nodes[b]
            km += base.haversine_km(na.lon, na.lat, nb.lon, nb.lat)
        regions = [med.REGION_BY_NODE.get(node, "other") for node in route]
        crossings = sum(a != b for a, b in zip(regions[:-1], regions[1:]))
        liminal = sum(self.nodes[node].kind in LIMINAL_NODE_KINDS for node in route) / max(1, len(route))
        return {
            "route_km": float(km),
            "route_hops": float(max(0, len(route) - 1)),
            "corridor_crossings": float(crossings),
            "liminal_fraction": float(liminal),
        }

    def _deposition_probabilities(self, object_class: str, bundle: base.JetBundle) -> Dict[str, float]:
        # Mirrors the existing deposition grammar but returns the whole distribution
        # so loss can be evaluated before materialization.
        arr = np.array([0.15, 0.16, 0.10, 0.08, 0.09, 0.16, 0.10, 0.10, 0.06], dtype=float)
        if object_class in {"scrap", "ingot"}:
            arr += np.array([0.25, 0.0, 0.0, 0.0, -0.03, -0.04, -0.02, 0.18, 0.0])
        if object_class in PRESTIGE_CLASSES:
            arr += np.array([-0.03, 0.08, 0.13, 0.06, 0.08, -0.08, 0.03, -0.08, 0.0])
        if bundle.family == "local_recycling":
            arr[0] += 0.16
            arr[7] += 0.12
        if self.bundle_incidence.get(bundle.id, 1.0) < 0.5:
            # Tail objects are not produced more often; conditional on disappearing
            # from circulation, transport/liminal loss is more plausible.
            arr[5] += 0.06
            arr[6] += 0.13
            arr[8] += 0.08
        arr = np.clip(arr, 0.001, None)
        arr /= arr.sum()
        return {mode: float(p) for mode, p in zip(base.DEPOSITION_MODES, arr)}

    def _return_probability(self, object_class: str, bundle: base.JetBundle, metrics: Mapping[str, float]) -> float:
        tail = float(self.bundle_incidence.get(bundle.id, 1.0) < 0.5)
        core_bulk = float(not tail and object_class in BULK_RETURN_CLASSES)
        prestige = float(object_class in PRESTIGE_CLASSES)
        route = min(1.0, float(metrics["route_km"]) / 1800.0)
        crossings = min(1.0, float(metrics["corridor_crossings"]) / 4.0)
        recycle = float(bundle.recycle_mean)
        z = (
            1.05
            + 1.35 * core_bulk
            + 1.10 * recycle
            + 0.25 * prestige
            - 1.00 * tail
            - 0.72 * route
            - 0.55 * crossings
            - 0.30 * float(metrics["liminal_fraction"])
        )
        return float(np.clip(_sigmoid(z), 0.08, 0.985))

    def _loss_probability(
        self,
        object_class: str,
        bundle: base.JetBundle,
        mode: str,
        metrics: Mapping[str, float],
        p_return: float,
    ) -> float:
        tail = float(self.bundle_incidence.get(bundle.id, 1.0) < 0.5)
        route = min(1.0, float(metrics["route_km"]) / 1800.0)
        hops = min(1.0, float(metrics["route_hops"]) / 9.0)
        crossings = min(1.0, float(metrics["corridor_crossings"]) / 4.0)
        prestige = float(object_class in PRESTIGE_CLASSES)
        z = -4.15 + 1.10 * tail + 0.70 * route + 0.55 * hops + 0.72 * crossings + 0.42 * prestige
        exceptional = _sigmoid(z) * MODE_LOSS_MULTIPLIER[mode]
        return float(np.clip((1.0 - p_return) * exceptional, 2.0e-5, 0.12))

    def _survival_probability(self, object_class: str, mode: str) -> float:
        p = float(base.OBJECT_CLASSES[object_class]["survival"]) * MODE_SURVIVAL_MULTIPLIER[mode]
        return float(np.clip(p, 0.10, 0.97))

    def _discovery_probability(
        self,
        object_class: str,
        bundle: base.JetBundle,
        mode: str,
        metrics: Mapping[str, float],
    ) -> float:
        tail = float(self.bundle_incidence.get(bundle.id, 1.0) < 0.5)
        mean_mass = float(base.OBJECT_CLASSES[object_class]["mean_kg"])
        mass_visibility = min(1.0, math.log1p(mean_mass * 7.0) / math.log(1.0 + 7.0 * 4.8))
        remote_penalty = min(0.55, float(metrics["route_km"]) / 5000.0)
        # Discovery is intentionally low overall. Tail/remote contexts can survive
        # well but remain hard to encounter in the modern record.
        p = 0.0105 * MODE_DISCOVERY_MULTIPLIER[mode] * (0.68 + 0.70 * mass_visibility)
        p *= 1.0 - 0.20 * tail - 0.25 * remote_penalty
        return float(np.clip(p, 0.0012, 0.035))

    @staticmethod
    def _record_probability(object_class: str, mode: str) -> float:
        p = 0.42
        if object_class in PRESTIGE_CLASSES:
            p += 0.12
        if mode in {"grave_assemblage", "finished_object_hoard", "catastrophic_abandonment"}:
            p += 0.08
        if mode == "workshop_debris":
            p -= 0.10
        return float(np.clip(p, 0.18, 0.72))

    # ---------- waterfall summaries ----------

    @staticmethod
    def _new_stage() -> Dict[str, Any]:
        return {
            "weight": 0.0,
            "tail_weight": 0.0,
            "macro_region": defaultdict(float),
            "object_class": defaultdict(float),
            "deposition_mode": defaultdict(float),
            "route_km_sum": 0.0,
            "route_hops_sum": 0.0,
            "corridor_crossings_sum": 0.0,
            "source_entropy_sum": 0.0,
            "recycle_fraction_sum": 0.0,
            "guild_strength_sum": 0.0,
            "mass_kg_sum": 0.0,
            "prestige_sum": 0.0,
            "p_return_sum": 0.0,
            "p_loss_sum": 0.0,
            "p_survival_sum": 0.0,
            "p_discovery_sum": 0.0,
        }

    def _stage_add(
        self,
        stage: Dict[str, Any],
        *,
        weight: float,
        bundle: base.JetBundle,
        object_class: str,
        mode: str | None,
        metrics: Mapping[str, float],
        p_return: float,
        p_loss: float,
        p_survival: float,
        p_discovery: float,
    ) -> None:
        if weight <= 0:
            return
        tail = self.bundle_incidence.get(bundle.id, 1.0) < 0.5
        region = med.REGION_BY_NODE.get(bundle.destination, "other")
        entropy = _safe_entropy(bundle.source_mix)
        guild_proxy = 0.0
        stage["weight"] += weight
        stage["tail_weight"] += weight * float(tail)
        stage["macro_region"][region] += weight
        stage["object_class"][object_class] += weight
        if mode:
            stage["deposition_mode"][mode] += weight
        stage["route_km_sum"] += weight * float(metrics["route_km"])
        stage["route_hops_sum"] += weight * float(metrics["route_hops"])
        stage["corridor_crossings_sum"] += weight * float(metrics["corridor_crossings"])
        stage["source_entropy_sum"] += weight * entropy
        stage["recycle_fraction_sum"] += weight * float(bundle.recycle_mean)
        stage["guild_strength_sum"] += weight * guild_proxy
        stage["mass_kg_sum"] += weight * float(base.OBJECT_CLASSES[object_class]["mean_kg"])
        stage["prestige_sum"] += weight * float(base.OBJECT_CLASSES[object_class]["status"])
        stage["p_return_sum"] += weight * p_return
        stage["p_loss_sum"] += weight * p_loss
        stage["p_survival_sum"] += weight * p_survival
        stage["p_discovery_sum"] += weight * p_discovery

    @staticmethod
    def _finalize_stage(stage: Mapping[str, Any]) -> Dict[str, Any]:
        w = max(1e-12, float(stage["weight"]))
        return {
            "expected_count": float(stage["weight"]),
            "tail_share": float(stage["tail_weight"]) / w,
            "macro_region": dict(sorted(stage["macro_region"].items())),
            "object_class": dict(sorted(stage["object_class"].items())),
            "deposition_mode": dict(sorted(stage["deposition_mode"].items())),
            "means": {
                "route_km": float(stage["route_km_sum"]) / w,
                "route_hops": float(stage["route_hops_sum"]) / w,
                "corridor_crossings": float(stage["corridor_crossings_sum"]) / w,
                "source_entropy": float(stage["source_entropy_sum"]) / w,
                "recycle_fraction": float(stage["recycle_fraction_sum"]) / w,
                "guild_strength_proxy": float(stage["guild_strength_sum"]) / w,
                "mass_kg": float(stage["mass_kg_sum"]) / w,
                "prestige": float(stage["prestige_sum"]) / w,
                "p_return": float(stage["p_return_sum"]) / w,
                "p_loss": float(stage["p_loss_sum"]) / w,
                "p_survival": float(stage["p_survival_sum"]) / w,
                "p_discovery": float(stage["p_discovery_sum"]) / w,
            },
        }

    @staticmethod
    def _tail_odds(share: float) -> float:
        share = float(np.clip(share, 1e-12, 1.0 - 1e-12))
        return share / (1.0 - share)

    def _finalize_waterfall(self, stages: Mapping[str, Mapping[str, Any]]) -> Dict[str, Any]:
        out = {name: self._finalize_stage(stage) for name, stage in stages.items()}
        names = list(out)
        transitions = {}
        for a, b in zip(names[:-1], names[1:]):
            oa = self._tail_odds(out[a]["tail_share"])
            ob = self._tail_odds(out[b]["tail_share"])
            transitions[f"{a}_to_{b}"] = {
                "tail_odds_multiplier": float(ob / max(1e-12, oa)),
                "tail_share_delta": float(out[b]["tail_share"] - out[a]["tail_share"]),
            }
        return {
            "model_version": OBSERVATION_MODEL_VERSION,
            "stages": out,
            "transitions": transitions,
        }

    # ---------- catalogue generation ----------

    def generate_archaeological_catalogue(self, max_materialized: int = 30000) -> Dict[str, Any]:
        if not self.bundles or not self.workshops:
            raise RuntimeError("Call build() before generating catalogue.")

        stage_names = [
            "hidden_production",
            "circulation_reuse",
            "loss_deposition",
            "archaeological_survival",
            "modern_discovery",
            "recorded_catalogue_expectation",
        ]
        stages = {name: self._new_stage() for name in stage_names}
        observed_specs: list[tuple[base.JetBundle, int, str, str, int, Dict[str, float]]] = []
        hidden_production = 0.0
        hidden_circulation = 0.0
        expected_recorded = 0.0

        for bundle in self.bundles:
            metrics = self._route_metrics(bundle)
            for t in self.time_slices:
                tonnes = float(bundle.flux_tonnes.get(t, 0.0))
                if tonnes <= 0:
                    continue
                classes, class_weights = self._class_weights(t, bundle)
                for object_class, class_weight in zip(classes, class_weights):
                    object_class = str(object_class)
                    class_weight = float(class_weight)
                    mass = float(base.OBJECT_CLASSES[object_class]["mean_kg"])
                    production = tonnes * 1000.0 * 0.48 * class_weight / max(0.01, mass)
                    circulation = production / max(0.12, 1.0 - float(bundle.recycle_mean))
                    hidden_production += production
                    hidden_circulation += circulation
                    p_return = self._return_probability(object_class, bundle, metrics)
                    mode_probs = self._deposition_probabilities(object_class, bundle)

                    self._stage_add(
                        stages["hidden_production"], weight=production, bundle=bundle,
                        object_class=object_class, mode=None, metrics=metrics,
                        p_return=p_return, p_loss=0.0, p_survival=0.0, p_discovery=0.0,
                    )
                    self._stage_add(
                        stages["circulation_reuse"], weight=circulation, bundle=bundle,
                        object_class=object_class, mode=None, metrics=metrics,
                        p_return=p_return, p_loss=0.0, p_survival=0.0, p_discovery=0.0,
                    )

                    for mode, p_mode in mode_probs.items():
                        p_loss = self._loss_probability(object_class, bundle, mode, metrics, p_return)
                        p_survive = self._survival_probability(object_class, mode)
                        p_discover = self._discovery_probability(object_class, bundle, mode, metrics)
                        p_record = self._record_probability(object_class, mode)
                        lost = circulation * p_mode * p_loss
                        survived = lost * p_survive
                        discovered = survived * p_discover
                        recorded = discovered * p_record
                        expected_recorded += recorded

                        self._stage_add(stages["loss_deposition"], weight=lost, bundle=bundle,
                                        object_class=object_class, mode=mode, metrics=metrics,
                                        p_return=p_return, p_loss=p_loss, p_survival=p_survive, p_discovery=p_discover)
                        self._stage_add(stages["archaeological_survival"], weight=survived, bundle=bundle,
                                        object_class=object_class, mode=mode, metrics=metrics,
                                        p_return=p_return, p_loss=p_loss, p_survival=p_survive, p_discovery=p_discover)
                        self._stage_add(stages["modern_discovery"], weight=discovered, bundle=bundle,
                                        object_class=object_class, mode=mode, metrics=metrics,
                                        p_return=p_return, p_loss=p_loss, p_survival=p_survive, p_discovery=p_discover)
                        self._stage_add(stages["recorded_catalogue_expectation"], weight=recorded, bundle=bundle,
                                        object_class=object_class, mode=mode, metrics=metrics,
                                        p_return=p_return, p_loss=p_loss, p_survival=p_survive, p_discovery=p_discover)

                        n = int(self.rng.poisson(recorded))
                        if n > 0:
                            probs = {
                                "p_return": p_return,
                                "p_loss": p_loss,
                                "p_survival": p_survive,
                                "p_discovery": p_discover,
                                "p_record": p_record,
                                **metrics,
                            }
                            observed_specs.append((bundle, t, object_class, mode, n, probs))

        total_n = sum(spec[4] for spec in observed_specs)
        scale = 1.0 if total_n <= max_materialized else max_materialized / max(1, total_n)

        rows: list[Dict[str, Any]] = []
        object_no = 0
        for bundle, t, object_class, mode, n_raw, probs in observed_specs:
            n = int(self.rng.binomial(n_raw, scale)) if scale < 1.0 else int(n_raw)
            for _ in range(n):
                object_no += 1
                route_pos = int(self.rng.integers(max(0, len(bundle.route) // 3), len(bundle.route)))
                dep_node_id = bundle.route[route_pos]
                dep_node = self.nodes[dep_node_id]
                workshop_node = bundle.route[max(0, route_pos - int(self.rng.integers(0, min(3, route_pos + 1))))]
                workshop = self._active_workshop(workshop_node, t)
                row = super()._materialize_object(object_no, object_class, bundle, t, workshop, dep_node)
                row["deposition_mode_truth"] = mode
                row["preservation"] = self._preservation_label(object_class, mode)
                truth = row.setdefault("truth", {})
                truth["observation_model_version"] = OBSERVATION_MODEL_VERSION
                truth["ordinary_return_probability"] = round(float(probs["p_return"]), 6)
                truth["exceptional_loss_probability"] = round(float(probs["p_loss"]), 6)
                truth["archaeological_survival_probability"] = round(float(probs["p_survival"]), 6)
                truth["modern_discovery_probability"] = round(float(probs["p_discovery"]), 6)
                truth["record_probability"] = round(float(probs["p_record"]), 6)
                truth["route_km"] = round(float(probs["route_km"]), 3)
                truth["route_hops"] = int(round(float(probs["route_hops"])))
                truth["corridor_crossings"] = int(round(float(probs["corridor_crossings"])))
                truth["liminal_fraction"] = round(float(probs["liminal_fraction"]), 5)
                truth["exceptionality"] = round(float(np.clip(
                    0.34 * min(1.0, float(probs["route_km"]) / 1800.0)
                    + 0.22 * min(1.0, float(probs["corridor_crossings"]) / 4.0)
                    + 0.24 * float(self.bundle_incidence.get(bundle.id, 1.0) < 0.5)
                    + 0.20 * MODE_LOSS_MULTIPLIER[mode] / max(MODE_LOSS_MULTIPLIER.values()),
                    0.0, 1.0)), 5)
                rows.append(row)

        self._assign_hoards(rows)
        self.catalogue_truth = rows
        self.archaeology_waterfall = self._finalize_waterfall(stages)
        self.archaeology_waterfall["materialized_catalogue"] = self.catalogue_stage_summary(rows)
        return {
            "observation_model_version": OBSERVATION_MODEL_VERSION,
            "hidden_production_events_est": int(round(hidden_production)),
            "hidden_manufacture_use_events_est": int(round(hidden_circulation)),
            "expected_catalogued_before_bound": float(expected_recorded),
            "materialization_scale": float(scale),
            "catalogued_objects": len(rows),
            "archaeology_waterfall": self.archaeology_waterfall,
        }

    def catalogue_stage_summary(self, rows: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
        if not rows:
            return {"count": 0}
        regions = Counter(str(r.get("truth", {}).get("macro_region", "other")) for r in rows)
        classes = Counter(str(r.get("class", "other")) for r in rows)
        modes = Counter(str(r.get("deposition_mode_truth", "unknown")) for r in rows)
        tail = np.asarray([float(bool(r.get("truth", {}).get("long_distance_tail", False))) for r in rows], dtype=float)
        def mean_truth(key: str, default: float = 0.0) -> float:
            return float(np.mean([float(r.get("truth", {}).get(key, default)) for r in rows]))
        return {
            "count": len(rows),
            "tail_share": float(tail.mean()),
            "macro_region": dict(sorted(regions.items())),
            "object_class": dict(sorted(classes.items())),
            "deposition_mode": dict(sorted(modes.items())),
            "means": {
                "route_km": mean_truth("route_km"),
                "route_hops": mean_truth("route_hops"),
                "corridor_crossings": mean_truth("corridor_crossings"),
                "source_entropy": mean_truth("source_entropy"),
                "recycle_fraction": mean_truth("recycle_fraction"),
                "guild_strength": mean_truth("guild_strength"),
                "mass_kg": float(np.mean([float(r.get("mass_kg", 0.0)) for r in rows])),
                "prestige": float(np.mean([float(base.OBJECT_CLASSES[str(r.get("class", "fitting"))]["status"]) for r in rows])),
                "p_return": mean_truth("ordinary_return_probability"),
                "p_loss": mean_truth("exceptional_loss_probability"),
                "p_survival": mean_truth("archaeological_survival_probability"),
                "p_discovery": mean_truth("modern_discovery_probability"),
            },
        }
