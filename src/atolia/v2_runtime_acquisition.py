from __future__ import annotations

"""300-object career adapter for the frozen Atolia v2 metal-lineage runtime.

The v2 shipping product deliberately omits exact ``/states`` rows but retains
weighted terminal ``/profiles`` plus cells, vocabularies, workshops, tools,
hydrology and events.  This module projects those weighted profiles into the
existing acquisition campaign boundary without pretending the v2 file is the
flat v1 ECMWF runtime.

POARI continues to choose archaeological inquiry/actions.  A concrete weighted
v2 profile is materialized only after the action/site has been chosen.
"""

import json
import math
from pathlib import Path
from typing import Any, Dict, Mapping, Sequence

import numpy as np
from netCDF4 import Dataset

import acquisition_campaign as campaign
import archaeological_condensation_v3 as condensation
import archaeology_observation_v2 as observation
import ecmwf_acquisition_campaign as legacy_runtime
import intensity_circulation as intensity
import provenance_field as base
import provenance_field_mediterranean as med
import v2_config as cfg


RUNTIME_SCHEMA = cfg.V2_RUNTIME_SCHEMA
RUNTIME_SAMPLER_VERSION = "atolia-v2-metal-lineage-acquisition-v1"

_CONTEXT = {
    "grave_assemblage": .92,
    "workshop_debris": .90,
    "catastrophic_abandonment": .84,
    "finished_object_hoard": .88,
    "founder_scrap_hoard": .84,
    "personal_wealth_deposit": .78,
    "settlement_loss": .58,
    "selective_ritual_deposit": .55,
    "river_wetland_deposit": .28,
}
_HOARD_MODES = {
    "founder_scrap_hoard",
    "finished_object_hoard",
    "personal_wealth_deposit",
    "selective_ritual_deposit",
}


def _names(var: Any) -> list[str]:
    values = var[:]
    out: list[str] = []
    for value in values:
        if isinstance(value, bytes):
            out.append(value.decode("utf-8"))
        else:
            out.append(str(value))
    return out


def _weighted_harmonic_matrix(values: np.ndarray, weights: Sequence[float]) -> np.ndarray:
    x = np.clip(np.asarray(values, dtype=np.float64), 1e-6, None)
    w = np.asarray(weights, dtype=np.float64)
    w /= float(w.sum())
    return 1.0 / np.sum(w[None, :] / x, axis=1)


class V2RuntimeProfileStore:
    """Read the grouped v2 runtime and expose the campaign profile interface."""

    def __init__(self, path: Path, world: Any) -> None:
        self.path = Path(path)
        if not self.path.exists():
            raise FileNotFoundError(self.path)
        self.ds = Dataset(self.path, "r")
        try:
            self._validate(world)
            self._load_coordinates()
            self._load_core_arrays(world)
            self._build_observation_projection(world)
            self._build_site_index()
            self._build_sampling_indexes(world)
        except Exception:
            self.ds.close()
            raise

    def close(self) -> None:
        if getattr(self, "ds", None) is not None:
            self.ds.close()
            self.ds = None

    def _validate(self, world: Any) -> None:
        schema = str(getattr(self.ds, "schema", ""))
        if schema != RUNTIME_SCHEMA:
            raise ValueError(f"not an Atolia v2 runtime: schema={schema!r}")
        required_groups = {"vocab", "cells", "profiles", "workshops", "tools", "hydro", "events"}
        missing_groups = sorted(required_groups - set(self.ds.groups))
        if missing_groups:
            raise ValueError(f"v2 runtime missing groups: {missing_groups}")
        required = {
            "vocab": {
                "node_name", "object_class_name", "carrier_name", "bundle_name",
                "bundle_family_name", "source_name", "state_moment_name",
            },
            "cells": {
                "bundle_id", "bundle_family_id", "date_bc", "origin_node_id",
                "destination_node_id", "initial_object_class_id", "primary_cu_kg",
                "objectized_primary_cu_kg", "represented_initial_lineages",
                "source_ptr", "source_id", "source_weight",
            },
            "profiles": {
                "cell_id", "node_id", "object_class_id", "carrier_id",
                "represented_weight", "exact_state_count", "mean", "variance",
            },
        }
        for group_name, names in required.items():
            group = self.ds.groups[group_name]
            missing = sorted(names - set(group.variables))
            if missing:
                raise ValueError(f"v2 runtime {group_name} missing variables: {missing}")
        self.profile_count = len(self.ds.groups["profiles"].dimensions["profile"])
        self.cell_count = len(self.ds.groups["cells"].dimensions["cell"])
        if self.profile_count <= 0 or self.cell_count <= 0:
            raise ValueError("v2 runtime has no profiles or production cells")
        if not getattr(world, "nodes", None):
            raise RuntimeError("v2 acquisition requires a built shared world with nodes")

    def _load_coordinates(self) -> None:
        vocab = self.ds.groups["vocab"]
        self.node_names = _names(vocab.variables["node_name"])
        self.class_names = _names(vocab.variables["object_class_name"])
        self.carrier_names = _names(vocab.variables["carrier_name"])
        self.bundle_names = _names(vocab.variables["bundle_name"])
        self.family_names = _names(vocab.variables["bundle_family_name"])
        self.source_names = _names(vocab.variables["source_name"])
        self.moment_names = _names(vocab.variables["state_moment_name"])
        self.moment_index = {name: i for i, name in enumerate(self.moment_names)}
        required_moments = {
            "current_object_distance_km", "remelt_count", "repair_count",
            "source_entropy", "water_mode_count", "external_exchange_fraction",
            "atesis_crossing_count", "ownership_transfer_count",
        }
        missing = sorted(required_moments - set(self.moment_index))
        if missing:
            raise ValueError(f"v2 runtime missing player moments: {missing}")
        self.node_index = {name: i for i, name in enumerate(self.node_names)}
        self.deposition_modes = list(base.DEPOSITION_MODES)
        self.transport_fields = ["metal_lineage_network"]

    def _load_core_arrays(self, world: Any) -> None:
        cells = self.ds.groups["cells"]
        profiles = self.ds.groups["profiles"]

        self.profile_cell = np.asarray(profiles.variables["cell_id"][:], dtype=np.int64)
        self.profile_node = np.asarray(profiles.variables["node_id"][:], dtype=np.int64)
        self.profile_class = np.asarray(profiles.variables["object_class_id"][:], dtype=np.int64)
        self.profile_carrier = np.asarray(profiles.variables["carrier_id"][:], dtype=np.int64)
        self.profile_weight = np.asarray(profiles.variables["represented_weight"][:], dtype=np.float64)
        self.profile_mean_matrix = np.asarray(profiles.variables["mean"][:], dtype=np.float64)
        self.profile_var_matrix = np.asarray(profiles.variables["variance"][:], dtype=np.float64)

        self.cell_bundle = np.asarray(cells.variables["bundle_id"][:], dtype=np.int64)
        self.cell_family = np.asarray(cells.variables["bundle_family_id"][:], dtype=np.int64)
        self.cell_class = np.asarray(cells.variables["initial_object_class_id"][:], dtype=np.int64)
        self.cell_date = np.asarray(cells.variables["date_bc"][:], dtype=np.int64)
        self.cell_origin = np.asarray(cells.variables["origin_node_id"][:], dtype=np.int64)
        self.cell_destination = np.asarray(cells.variables["destination_node_id"][:], dtype=np.int64)
        self.cell_primary_cu = np.asarray(cells.variables["primary_cu_kg"][:], dtype=np.float64)
        self.cell_objectized_cu = np.asarray(cells.variables["objectized_primary_cu_kg"][:], dtype=np.float64)
        self.cell_lineages = np.asarray(cells.variables["represented_initial_lineages"][:], dtype=np.float64)

        if self.profile_cell.size != self.profile_count or self.profile_node.size != self.profile_count:
            raise ValueError("v2 runtime profile arrays are incomplete")
        if np.any(self.profile_cell < 0) or np.any(self.profile_cell >= self.cell_count):
            raise ValueError("v2 profile cell ids are out of range")
        if np.any(self.profile_node < 0) or np.any(self.profile_node >= len(self.node_names)):
            raise ValueError("v2 profile node ids are out of range")
        if np.any(self.profile_class < 0) or np.any(self.profile_class >= len(self.class_names)):
            raise ValueError("v2 profile object-class ids are out of range")

        used_node_ids = np.unique(np.concatenate((self.profile_node, self.cell_origin, self.cell_destination)))
        missing_nodes = [self.node_names[int(i)] for i in used_node_ids if self.node_names[int(i)] not in world.nodes]
        if missing_nodes:
            raise ValueError(
                "v2 runtime/world geography mismatch; runtime nodes absent from shared world: "
                + ", ".join(missing_nodes[:8])
            )

        self.mean_route = self._moment_array("current_object_distance_km")
        self.mean_physical = self._moment_array("water_mode_count") + self._moment_array("atesis_crossing_count")
        self.mean_field = np.clip(self._moment_array("external_exchange_fraction"), 0.0, 1.0)

    def _moment_array(self, name: str) -> np.ndarray:
        return np.asarray(self.profile_mean_matrix[:, self.moment_index[name]], dtype=np.float64)

    def _moment_var_array(self, name: str) -> np.ndarray:
        return np.maximum(0.0, np.asarray(self.profile_var_matrix[:, self.moment_index[name]], dtype=np.float64))

    def _terminal_loss_fraction(self) -> float:
        try:
            accounting = json.loads(str(getattr(self.ds, "accounting_json", "{}")))
            rows = dict(accounting.get("terminal_weight_by_kind", {}))
            total = sum(max(0.0, float(v)) for v in rows.values())
            retired = max(0.0, float(rows.get("retire", 0.0)))
            if total > 0.0:
                return float(np.clip(1.0 - retired / total, .05, 1.0))
        except (TypeError, ValueError, json.JSONDecodeError):
            pass
        return .77

    def _build_observation_projection(self, world: Any) -> None:
        # The runtime intentionally collapses terminal kind inside each weighted
        # profile.  Archaeological deposition is therefore an observation-layer
        # projection, not a reconstruction of omitted exact states.  Reuse the
        # repository's existing v2 observation grammar rather than adding a new
        # one here.
        bundle_by_id = {str(bundle.id): bundle for bundle in world.bundles}
        missing_bundles = sorted({self.bundle_names[int(i)] for i in np.unique(self.cell_bundle)} - set(bundle_by_id))
        if missing_bundles:
            raise ValueError(
                "v2 runtime/world bundle mismatch: " + ", ".join(missing_bundles[:8])
            )

        mode_count = len(self.deposition_modes)
        self.deposition = np.zeros((self.profile_count, mode_count), dtype=np.float32)
        mode_index = {name: i for i, name in enumerate(self.deposition_modes)}
        cache: Dict[tuple[str, str], np.ndarray] = {}

        for pid in range(self.profile_count):
            cid = int(self.profile_cell[pid])
            bundle_id = self.bundle_names[int(self.cell_bundle[cid])]
            object_class = self.class_names[int(self.profile_class[pid])]
            key = (bundle_id, object_class)
            row = cache.get(key)
            if row is None:
                probs = observation.ArchaeologicalObservationWorld._deposition_probabilities(
                    world, object_class, bundle_by_id[bundle_id]
                )
                row = np.zeros(mode_count, dtype=np.float64)
                for mode, value in probs.items():
                    if mode in mode_index:
                        row[mode_index[mode]] = max(0.0, float(value))
                total = float(row.sum())
                if total <= 0.0:
                    row[mode_index.get("settlement_loss", 0)] = 1.0
                else:
                    row /= total
                cache[key] = row
            self.deposition[pid, :] = row

        observation_factor = np.asarray([
            float(condensation.MODE_SURVIVAL.get(mode, .46))
            * float(condensation.MODE_DISCOVERY.get(mode, .018))
            * float(condensation.MODE_RECORD.get(mode, .44))
            for mode in self.deposition_modes
        ], dtype=np.float64)
        context_factor = np.asarray([float(_CONTEXT.get(mode, .50)) for mode in self.deposition_modes], dtype=np.float64)
        hoard_mask = np.asarray([1.0 if mode in _HOARD_MODES else 0.0 for mode in self.deposition_modes], dtype=np.float64)

        dep = np.asarray(self.deposition, dtype=np.float64)
        self.profile_observation = np.maximum(1e-8, dep @ observation_factor)
        self.profile_context = np.clip(dep @ context_factor, 0.0, 1.0)
        self.profile_hoard = np.clip(dep @ hoard_mask, 0.0, 1.0)
        self.profile_loss = np.maximum(0.0, self.profile_weight) * self._terminal_loss_fraction()
        self.profile_arch = self.profile_loss * self.profile_observation

    def _build_site_index(self) -> None:
        order = np.argsort(self.profile_node, kind="stable").astype(np.int64)
        counts = np.bincount(self.profile_node, minlength=len(self.node_names)).astype(np.int64)
        ptr = np.empty(len(self.node_names) + 1, dtype=np.int64)
        ptr[0] = 0
        np.cumsum(counts, out=ptr[1:])
        self.site_profile_index = order
        self.site_ptr = ptr

    def _build_sampling_indexes(self, world: Any) -> None:
        incidence_by_cell = np.asarray([
            float(getattr(world, "bundle_incidence", {}).get(self.bundle_names[int(bid)], 1.0))
            for bid in self.cell_bundle
        ], dtype=np.float64)
        origin_region_by_cell = np.asarray([
            med.REGION_BY_NODE.get(self.node_names[int(nid)], "other") for nid in self.cell_origin
        ], dtype=object)
        loss_region = np.asarray([
            med.REGION_BY_NODE.get(self.node_names[int(nid)], "other") for nid in self.profile_node
        ], dtype=object)
        profile_incidence = incidence_by_cell[self.profile_cell]
        origin_region = origin_region_by_cell[self.profile_cell]

        self.tail_mask = (
            (profile_incidence < .50)
            | (self.mean_route >= 520.0)
            | (self.mean_physical >= .80)
            | (self.mean_field >= .12)
            | (origin_region != loss_region)
        )
        self.exceptionality = np.clip(
            .32 * np.minimum(1.0, self.mean_route / 1400.0)
            + .22 * np.minimum(1.0, self.mean_physical / 2.5)
            + .18 * np.minimum(1.0, self.mean_field / .25)
            + .18 * (profile_incidence < .50).astype(np.float64)
            + .10 * (1.0 - self.profile_context),
            0.0,
            1.0,
        )

        archaeological_yield = np.clip(.15 + .85 * np.log1p(np.maximum(0.0, self.profile_arch)) / 12.0, .05, 1.0)
        recoverability = np.clip(self.profile_observation / .03, .05, 1.0)
        novelty = np.clip(.20 + .80 * self.exceptionality, .05, 1.0)
        anti_leak = np.clip(1.08 - self.profile_context, .05, 1.0)
        exceptional_loss = np.clip(.12 + .88 * self.exceptionality, .05, 1.0)
        dims = np.column_stack([archaeological_yield, recoverability, novelty, anti_leak, exceptional_loss])
        poari = _weighted_harmonic_matrix(dims, [.14, .15, .22, .19, .30])
        base_kernel = np.sqrt(np.maximum(1e-12, self.profile_arch)) * np.square(.18 + poari)

        self.tail_ids = np.flatnonzero(self.tail_mask).astype(np.int64)
        self.ordinary_ids = np.flatnonzero(~self.tail_mask).astype(np.int64)
        tail_w = base_kernel[self.tail_ids] * 3.0
        ordinary_w = base_kernel[self.ordinary_ids] * 1.8
        self.tail_cdf = np.cumsum(np.where(np.isfinite(tail_w), tail_w, 0.0))
        self.ordinary_cdf = np.cumsum(np.where(np.isfinite(ordinary_w), ordinary_w, 0.0))

        hoard_ids = np.flatnonzero(self.profile_hoard > .02).astype(np.int64)
        self.hoard_ids = hoard_ids if hoard_ids.size else np.arange(self.profile_count, dtype=np.int64)
        lam = np.maximum(1e-12, self.profile_arch[self.hoard_ids] * np.maximum(.02, self.profile_hoard[self.hoard_ids]))
        self.hoard_cdf = np.cumsum(np.power(lam, .70))

    def profile_ids_at_site(self, node_id: str) -> np.ndarray:
        nid = self.node_index.get(str(node_id))
        if nid is None:
            return np.empty(0, dtype=np.int64)
        a, z = int(self.site_ptr[nid]), int(self.site_ptr[nid + 1])
        return np.asarray(self.site_profile_index[a:z], dtype=np.int64)

    def build_sites(self, world: Any) -> Dict[str, campaign.SiteOpportunity]:
        sites: Dict[str, campaign.SiteOpportunity] = {}
        for node_id in self.node_names:
            ids = self.profile_ids_at_site(node_id)
            if ids.size == 0 or node_id not in world.nodes:
                continue
            node = world.nodes[node_id]
            arch = self.profile_arch[ids]
            loss = self.profile_loss[ids]
            classes = self.profile_class[ids]
            deposition = np.asarray(self.deposition[ids, :], dtype=np.float64)
            site = campaign.SiteOpportunity(
                node_id=node_id,
                region=med.REGION_BY_NODE.get(node_id, "other"),
                kind=str(node.kind),
                lon=float(node.lon),
                lat=float(node.lat),
            )
            site.archaeological_intensity = float(arch.sum())
            site.loss_intensity = float(loss.sum())
            class_mass = np.bincount(classes, weights=arch, minlength=len(self.class_names))
            site.class_mass.update({
                self.class_names[i]: float(value)
                for i, value in enumerate(class_mass) if float(value) > 0.0
            })
            dep_mass = np.sum(deposition * arch[:, None], axis=0)
            site.deposition_mass.update({
                self.deposition_modes[i]: float(value)
                for i, value in enumerate(dep_mass) if float(value) > 0.0
            })
            route = self.mean_route[ids]
            physical = self.mean_physical[ids]
            field = self.mean_field[ids]
            site.route_km_sum = float(np.sum(arch * route))
            site.route_km_sq_sum = float(np.sum(arch * route * route))
            site.physical_cross_sum = float(np.sum(arch * physical))
            site.field_cross_sum = float(np.sum(arch * field))
            sites[node_id] = site
        return sites

    def source_mix_for_cell(self, cid: int) -> Dict[str, float]:
        cells = self.ds.groups["cells"]
        ptr = cells.variables["source_ptr"]
        a, z = int(ptr[cid]), int(ptr[cid + 1])
        ids = np.asarray(cells.variables["source_id"][a:z], dtype=np.int64)
        weights = np.asarray(cells.variables["source_weight"][a:z], dtype=np.float64)
        return {self.source_names[int(i)]: float(w) for i, w in zip(ids, weights)}

    def cell_object_class(self, pid: int) -> str:
        return self.class_names[int(self.profile_class[int(pid)])]

    def cell_date_bc(self, pid: int) -> int:
        return int(self.cell_date[int(self.profile_cell[int(pid)])])

    def _draw_moment(self, pid: int, name: str, rng: np.random.Generator | None) -> float:
        idx = self.moment_index[name]
        mean = float(self.profile_mean_matrix[pid, idx])
        if rng is None:
            value = mean
        else:
            var = max(0.0, float(self.profile_var_matrix[pid, idx]))
            value = mean if var <= 1e-18 else float(rng.normal(mean, math.sqrt(var)))
        if name in {"source_entropy", "external_exchange_fraction", "technical_memory_fraction", "network_embedding", "manufacture_quality"}:
            return float(np.clip(value, 0.0, 1.0))
        return max(0.0, float(value))

    def materialize(self, pid: int, rng: np.random.Generator | None = None) -> intensity.LossStratum:
        pid = int(pid)
        if not 0 <= pid < self.profile_count:
            raise IndexError(pid)
        cid = int(self.profile_cell[pid])
        node_id = self.node_names[int(self.profile_node[pid])]
        object_class = self.class_names[int(self.profile_class[pid])]
        carrier = self.carrier_names[int(self.profile_carrier[pid])]
        remelts = self._draw_moment(pid, "remelt_count", rng)
        repairs = self._draw_moment(pid, "repair_count", rng)
        water = self._draw_moment(pid, "water_mode_count", rng)
        atesis = self._draw_moment(pid, "atesis_crossing_count", rng)
        ownership = self._draw_moment(pid, "ownership_transfer_count", rng)

        production_cell = intensity.ProductionCell(
            bundle_id=self.bundle_names[int(self.cell_bundle[cid])],
            bundle_family=self.family_names[int(self.cell_family[cid])],
            object_class=object_class,
            date_bc=int(self.cell_date[cid]),
            origin=self.node_names[int(self.cell_origin[cid])],
            destination=self.node_names[int(self.cell_destination[cid])],
            production_intensity=float(self.cell_lineages[cid]),
            circulation_seed_intensity=float(self.cell_lineages[cid]),
            source_mix=self.source_mix_for_cell(cid),
            recycle_mean=float(remelts),
        )
        deposition_row = np.asarray(self.deposition[pid, :], dtype=np.float64)
        deposition = {
            name: float(value)
            for name, value in zip(self.deposition_modes, deposition_row)
            if float(value) > 0.0
        }
        return intensity.LossStratum(
            production_cell=production_cell,
            node_id=node_id,
            step=max(0, int(round(remelts + repairs + ownership))),
            loss_intensity=float(self.profile_loss[pid]),
            deposition_mode_weights=deposition,
            expected_recycle_count=remelts,
            expected_repair_count=repairs,
            expected_source_entropy=self._draw_moment(pid, "source_entropy", rng),
            expected_field_crossings=self._draw_moment(pid, "external_exchange_fraction", rng),
            expected_physical_crossings=max(0.0, water + atesis),
            route_distance_from_origin_km=self._draw_moment(pid, "current_object_distance_km", rng),
            field_mix={f"carrier:{carrier}": 1.0},
        )

    def flow_summary(self) -> Dict[str, Any]:
        try:
            accounting = dict(json.loads(str(getattr(self.ds, "accounting_json", "{}"))))
        except (TypeError, json.JSONDecodeError):
            accounting = {}
        return {
            "runtime_schema": RUNTIME_SCHEMA,
            "runtime_profiles": int(self.profile_count),
            "runtime_production_cells": int(self.cell_count),
            "terminal_loss_fraction": self._terminal_loss_fraction(),
            "v2_accounting": accounting,
        }

    def fingerprint(self) -> str:
        model = str(getattr(self.ds, "model_version", "unknown"))
        seed = str(getattr(self.ds, "world_seed", "unknown"))
        return f"{RUNTIME_SCHEMA}:{model}:{seed}:{self.profile_count}:{self.cell_count}"


class V2AcquisitionCampaignSampler(legacy_runtime.ECMWFAcquisitionCampaignSampler):
    """Existing 300-career action grammar over direct v2 weighted profiles."""

    def prepare_candidates(self) -> None:
        if not getattr(self.world, "workshops", None) or not getattr(self.world, "sources", None):
            raise RuntimeError("v2 acquisition requires the shared world sources/workshops")
        store = V2RuntimeProfileStore(self.runtime_path, self.world)
        self.runtime_store = store
        self.runtime_fingerprint = store.fingerprint()
        self.flow_reports = []
        self.flow_summary = store.flow_summary()
        self.loss_strata = []
        self.sites = store.build_sites(self.world)
        if not self.sites:
            store.close()
            self.runtime_store = None
            raise RuntimeError("v2 runtime contains no archaeological sites")
        self._prepared = True

    def career_report(self):
        report = super().career_report()
        store = self.runtime_store
        report["ecmwf_runtime"] = {
            "schema": RUNTIME_SCHEMA,
            "sampler_version": RUNTIME_SAMPLER_VERSION,
            "path": str(self.runtime_path),
            "fingerprint": self.runtime_fingerprint,
            "profile_count": int(store.profile_count) if store is not None else None,
            "production_cell_count": int(store.cell_count) if store is not None else None,
            "python_loss_strata_materialized_at_prepare": 0,
            "site_membership_storage": "in-memory CSR index over v2 profile node ids",
            "materialization_boundary": "one selected v2 weighted profile -> one LossStratum -> one physical artefact",
            "profile_variance_sampling": "v2 weighted marginal variance; source/exchange fractions clipped to [0,1]",
            "profile_covariance_available": True,
            "terminal_kind_projection": "runtime-global retire share + existing archaeology-observation-v2 deposition grammar",
        }
        return report
