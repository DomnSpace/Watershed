from __future__ import annotations

import hashlib
from typing import Any, Dict, Mapping

import numpy as np

import archaeology_observation_v2 as observation
import artifact_mobility as mobility
import physical_geography as physical
import provenance_field as base
import provenance_field_mediterranean as med
import dense_geography_v1 as dense


FIELD_WORLD_VERSION = "archaeology-field-world-v1"


class FieldArchaeologicalObservationWorld(observation.ArchaeologicalObservationWorld):
    """Archaeology world with a physical carrier graph and class-specific mobility fields."""

    target_geography_nodes = 1000

    def __init__(self, *args: Any, target_geography_nodes: int | None = None, **kwargs: Any):
        super().__init__(*args, **kwargs)
        if target_geography_nodes is not None:
            self.target_geography_nodes = int(target_geography_nodes)
        self.geography_report: Dict[str, Any] = {}
        self._mobility_cache: Dict[tuple[str, str, int], mobility.MobilityRoute] = {}

    def _build_graph(self) -> None:
        super()._build_graph()
        canonical = set(self.nodes)
        self.geography_report = physical.install_carrier(self, self.target_geography_nodes)
        self.geography_report["connectivity"] = dense.connectivity_report(self, canonical)
        self.geography_report["canonical_nodes"] = len(canonical)
        self.geography_report["region_counts"] = self._region_counts()
        self.geography_report["field_world_version"] = FIELD_WORLD_VERSION

    def _region_counts(self) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for node_id in self.nodes:
            region = med.REGION_BY_NODE.get(node_id, "other")
            counts[region] = counts.get(region, 0) + 1
        return dict(sorted(counts.items()))

    @staticmethod
    def _phase_date(date_bc: int) -> int:
        # Route cache in 100-year phases keeps generation tractable while retaining
        # chronological field drift.
        return int(round(date_bc / 100.0) * 100)

    def mobility_route(self, bundle: base.JetBundle, object_class: str, date_bc: int) -> mobility.MobilityRoute:
        phase_date = self._phase_date(date_bc)
        key = (bundle.id, object_class, phase_date)
        route = self._mobility_cache.get(key)
        if route is None:
            digest = hashlib.sha256(f"{self.seed}:{bundle.id}:{object_class}:{phase_date}".encode()).digest()
            jitter_seed = int.from_bytes(digest[:8], "big") & 0x7FFFFFFF
            route = mobility.route_for_object(self, bundle, object_class, phase_date, jitter_seed)
            self._mobility_cache[key] = route
        return route

    def _mobility_metrics(self, bundle: base.JetBundle, object_class: str, date_bc: int) -> Dict[str, float]:
        r = self.mobility_route(bundle, object_class, date_bc)
        return {
            "route_km": r.km,
            "route_hops": float(r.hops),
            "corridor_crossings": float(r.physical_crossings),
            "physical_corridor_crossings": float(r.physical_crossings),
            "field_crossings": float(r.field_crossings),
            "liminal_fraction": float(np.mean([
                self.nodes[node].kind in {"coast", "pass", "river", "hub"} for node in r.nodes
            ])) if r.nodes else 0.0,
            "generalized_route_cost": float(r.generalized_cost),
        }

    def _route_metrics(self, bundle: base.JetBundle) -> Dict[str, float]:
        # Bundle-only callers retain a representative route. Catalogue generation
        # overrides this with object-class/time-specific biographies below.
        return self._mobility_metrics(bundle, "ingot", 1300)

    def generate_archaeological_catalogue(self, max_materialized: int = 30000) -> Dict[str, Any]:
        """Observation-v2 generation with field-conditioned object biographies."""
        if not self.bundles or not self.workshops:
            raise RuntimeError("Call build() before generating catalogue.")

        stage_names = ["hidden_production", "circulation_reuse", "loss_deposition",
                       "archaeological_survival", "modern_discovery", "recorded_catalogue_expectation"]
        stages = {name: self._new_stage() for name in stage_names}
        observed_specs = []
        hidden_production = hidden_circulation = expected_recorded = 0.0

        for bundle in self.bundles:
            for t in self.time_slices:
                tonnes = float(bundle.flux_tonnes.get(t, 0.0))
                if tonnes <= 0:
                    continue
                classes, class_weights = self._class_weights(t, bundle)
                for object_class, class_weight in zip(classes, class_weights):
                    object_class = str(object_class); class_weight = float(class_weight)
                    metrics = self._mobility_metrics(bundle, object_class, t)
                    mass = float(base.OBJECT_CLASSES[object_class]["mean_kg"])
                    production = tonnes * 1000.0 * 0.48 * class_weight / max(0.01, mass)
                    circulation = production / max(0.12, 1.0 - float(bundle.recycle_mean))
                    hidden_production += production; hidden_circulation += circulation
                    p_return = self._return_probability(object_class, bundle, metrics)
                    mode_probs = self._deposition_probabilities(object_class, bundle)
                    self._stage_add(stages["hidden_production"], weight=production, bundle=bundle, object_class=object_class,
                                    mode=None, metrics=metrics, p_return=p_return, p_loss=0, p_survival=0, p_discovery=0)
                    self._stage_add(stages["circulation_reuse"], weight=circulation, bundle=bundle, object_class=object_class,
                                    mode=None, metrics=metrics, p_return=p_return, p_loss=0, p_survival=0, p_discovery=0)
                    for mode, p_mode in mode_probs.items():
                        p_loss = self._loss_probability(object_class, bundle, mode, metrics, p_return)
                        p_survive = self._survival_probability(object_class, mode)
                        p_discover = self._discovery_probability(object_class, bundle, mode, metrics)
                        p_record = self._record_probability(object_class, mode)
                        lost = circulation * p_mode * p_loss; survived = lost * p_survive
                        discovered = survived * p_discover; recorded = discovered * p_record
                        expected_recorded += recorded
                        for stage_name, weight in (("loss_deposition", lost), ("archaeological_survival", survived),
                                                   ("modern_discovery", discovered), ("recorded_catalogue_expectation", recorded)):
                            self._stage_add(stages[stage_name], weight=weight, bundle=bundle, object_class=object_class,
                                            mode=mode, metrics=metrics, p_return=p_return, p_loss=p_loss,
                                            p_survival=p_survive, p_discovery=p_discover)
                        n = int(self.rng.poisson(recorded))
                        if n > 0:
                            observed_specs.append((bundle, t, object_class, mode, n, {
                                "p_return": p_return, "p_loss": p_loss, "p_survival": p_survive,
                                "p_discovery": p_discover, "p_record": p_record, **metrics,
                            }))

        total_n = sum(spec[4] for spec in observed_specs)
        scale = 1.0 if total_n <= max_materialized else max_materialized / max(1, total_n)
        rows = []; object_no = 0
        for bundle, t, object_class, mode, n_raw, probs in observed_specs:
            n = int(self.rng.binomial(n_raw, scale)) if scale < 1.0 else int(n_raw)
            route = self.mobility_route(bundle, object_class, t)
            for _ in range(n):
                object_no += 1
                route_pos = mobility.choose_deposition_position(self.rng, route.nodes, object_class)
                dep_node_id = route.nodes[route_pos]; dep_node = self.nodes[dep_node_id]
                back = int(self.rng.integers(0, min(4, route_pos + 1))) if route_pos else 0
                workshop_node = route.nodes[max(0, route_pos - back)]
                workshop = self._active_workshop(workshop_node, t)
                row = super(observation.ArchaeologicalObservationWorld, self)._materialize_object(
                    object_no, object_class, bundle, t, workshop, dep_node)
                row["deposition_mode_truth"] = mode
                row["preservation"] = self._preservation_label(object_class, mode)
                truth = row.setdefault("truth", {})
                truth.update({
                    "observation_model_version": observation.OBSERVATION_MODEL_VERSION,
                    "mobility_model_version": mobility.MOBILITY_MODEL_VERSION,
                    "ordinary_return_probability": round(float(probs["p_return"]), 6),
                    "exceptional_loss_probability": round(float(probs["p_loss"]), 6),
                    "archaeological_survival_probability": round(float(probs["p_survival"]), 6),
                    "modern_discovery_probability": round(float(probs["p_discovery"]), 6),
                    "record_probability": round(float(probs["p_record"]), 6),
                    "route_km": round(route.km, 3), "route_hops": route.hops,
                    "corridor_crossings": route.physical_crossings,
                    "physical_corridor_crossings": route.physical_crossings,
                    "field_crossings": round(route.field_crossings, 6),
                    "generalized_route_cost": round(route.generalized_cost, 5),
                    "transport_field_mix": {k: round(v, 5) for k, v in route.field_mix.items() if v > .005},
                    "route_nodes_truth": list(route.nodes),
                    "liminal_fraction": round(float(probs["liminal_fraction"]), 5),
                    "exceptionality": round(float(np.clip(
                        .30 * min(1.0, route.km / 1800.0) + .18 * min(1.0, route.physical_crossings / 4.0)
                        + .14 * min(1.0, route.field_crossings / .25) + .22 * float(self.bundle_incidence.get(bundle.id, 1.0) < .5)
                        + .16 * observation.MODE_LOSS_MULTIPLIER[mode] / max(observation.MODE_LOSS_MULTIPLIER.values()), 0, 1)), 5),
                })
                rows.append(row)

        self._assign_hoards(rows); self.catalogue_truth = rows
        self.archaeology_waterfall = self._finalize_waterfall(stages)
        self.archaeology_waterfall["materialized_catalogue"] = self.catalogue_stage_summary(rows)
        return {
            "observation_model_version": observation.OBSERVATION_MODEL_VERSION,
            "mobility_model_version": mobility.MOBILITY_MODEL_VERSION,
            "field_world_version": FIELD_WORLD_VERSION,
            "hidden_production_events_est": int(round(hidden_production)),
            "hidden_manufacture_use_events_est": int(round(hidden_circulation)),
            "expected_catalogued_before_bound": float(expected_recorded), "materialization_scale": float(scale),
            "catalogued_objects": len(rows), "mobility_routes_cached": len(self._mobility_cache),
            "archaeology_waterfall": self.archaeology_waterfall,
        }
