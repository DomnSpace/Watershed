from __future__ import annotations

"""Acquisition career sampled directly from the compact ECMWF NetCDF runtime.

The legacy cached sampler deserializes every hidden loss row into a Python
``LossStratum`` object before the first player action.  That defeats the purpose
of the ECMWF-style field product.  This module keeps the latent substrate in
NetCDF arrays and materializes only the selected profile needed to instantiate a
physical artefact.

Runtime hierarchy
-----------------

    profile=(production_cell, loss_node)
        -> production cell
        -> loss node
        -> exact deposition vector
        -> loss-intensity-weighted moments of circulation coordinates

Selection hierarchy
-------------------

    global 1-D arrays / precomputed CDFs
        -> site CSR pointer slice
        -> selected profile id
        -> one lightweight LossStratum
        -> existing physical truth + measurement machinery

The 300-object career schedule and POARI action logic remain in
``acquisition_campaign.py``.  POARI still ranks archaeological inquiry/actions,
not artefacts.  In particular p=-1 remains the harmonic weak-link operator.
"""

import json
import math
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Sequence

import numpy as np
from netCDF4 import Dataset

import acquisition_campaign as campaign
import intensity_circulation as intensity
import provenance_field_mediterranean as med


RUNTIME_SCHEMA = "atolia.ecmwf-runtime.v1"
DEFAULT_RUNTIME = Path("cache/atolia_runtime_v1.nc")
RUNTIME_SAMPLER_VERSION = "atolia-ecmwf-acquisition-v1"

MOMENT_COORDS = (
    "expected_recycle_count",
    "expected_repair_count",
    "expected_source_entropy",
    "expected_field_crossings",
    "expected_physical_crossings",
    "route_distance_from_origin_km",
)

_REQUIRED_VARIABLES = {
    "bundle_name",
    "family_name",
    "object_class_name",
    "node_name",
    "source_name",
    "deposition_mode_name",
    "transport_field_name",
    "cell_bundle",
    "cell_family",
    "cell_object_class",
    "cell_date_bc",
    "cell_origin_node",
    "cell_destination_node",
    "cell_production_intensity",
    "cell_circulation_seed_intensity",
    "cell_recycle_mean",
    "cell_transport_field_mix",
    "cell_source_ptr",
    "cell_source_id",
    "cell_source_weight",
    "profile_cell",
    "profile_node",
    "profile_deposition_weight",
    "profile_loss_intensity",
    "profile_observation_rate",
    "profile_archaeological_intensity",
    "profile_context_completeness",
    "profile_hoard_prior",
    "profile_step_min",
    "profile_step_max",
    "site_ptr",
    "site_profile_index",
    *{f"profile_mean_{name}" for name in MOMENT_COORDS},
    *{f"profile_var_{name}" for name in MOMENT_COORDS},
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


def _sample_weighted_id(rng: np.random.Generator, ids: np.ndarray, weights: np.ndarray) -> int:
    if ids.size == 0:
        raise ValueError("cannot sample an empty profile set")
    w = np.asarray(weights, dtype=np.float64)
    w = np.where(np.isfinite(w) & (w > 0.0), w, 0.0)
    total = float(w.sum())
    if total <= 0.0:
        return int(ids[int(rng.integers(0, ids.size))])
    target = float(rng.random()) * total
    cdf = np.cumsum(w)
    index = int(np.searchsorted(cdf, target, side="right"))
    return int(ids[min(index, ids.size - 1)])


def _sample_cdf(rng: np.random.Generator, ids: np.ndarray, cdf: np.ndarray) -> int:
    if ids.size == 0:
        raise ValueError("cannot sample an empty CDF")
    total = float(cdf[-1])
    if not math.isfinite(total) or total <= 0.0:
        return int(ids[int(rng.integers(0, ids.size))])
    target = float(rng.random()) * total
    index = int(np.searchsorted(cdf, target, side="right"))
    return int(ids[min(index, ids.size - 1)])


def _weighted_harmonic_matrix(values: np.ndarray, weights: Sequence[float]) -> np.ndarray:
    """Vectorized p=-1 generalized mean; never clips the harmonic sum to one."""
    x = np.clip(np.asarray(values, dtype=np.float64), 1e-6, None)
    w = np.asarray(weights, dtype=np.float64)
    w /= float(w.sum())
    return 1.0 / np.sum(w[None, :] / x, axis=1)


class RuntimeProfileStore:
    """Read-only NetCDF runtime with array/CDF access and on-demand materialization."""

    def __init__(self, path: Path, world: Any) -> None:
        self.path = Path(path)
        if not self.path.exists():
            raise FileNotFoundError(self.path)
        self.ds = Dataset(self.path, "r")
        try:
            self._validate(world)
            self._load_coordinates()
            self._load_core_arrays(world)
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
            raise ValueError(f"not an Atolia ECMWF runtime: schema={schema!r}")
        missing = sorted(_REQUIRED_VARIABLES - set(self.ds.variables))
        if missing:
            raise ValueError(f"runtime missing required variables: {missing}")
        if "profile" not in self.ds.dimensions or "production_cell" not in self.ds.dimensions:
            raise ValueError("runtime missing profile/production_cell dimensions")
        self.profile_count = len(self.ds.dimensions["profile"])
        self.cell_count = len(self.ds.dimensions["production_cell"])
        attr_profiles = int(getattr(self.ds, "runtime_profile_count", getattr(self.ds, "profile_count", -1)))
        attr_cells = int(getattr(self.ds, "production_cell_count", -1))
        if attr_profiles >= 0 and attr_profiles != self.profile_count:
            raise ValueError(
                f"runtime profile count mismatch: dimension={self.profile_count:,} attr={attr_profiles:,}"
            )
        if attr_cells >= 0 and attr_cells != self.cell_count:
            raise ValueError(
                f"runtime production-cell count mismatch: dimension={self.cell_count:,} attr={attr_cells:,}"
            )
        if not getattr(world, "nodes", None):
            raise RuntimeError("ECMWF acquisition requires a built shared world with nodes")

    def _load_coordinates(self) -> None:
        ds = self.ds
        self.bundle_names = _names(ds.variables["bundle_name"])
        self.family_names = _names(ds.variables["family_name"])
        self.class_names = _names(ds.variables["object_class_name"])
        self.node_names = _names(ds.variables["node_name"])
        self.source_names = _names(ds.variables["source_name"])
        self.deposition_modes = _names(ds.variables["deposition_mode_name"])
        self.transport_fields = _names(ds.variables["transport_field_name"])
        self.node_index = {name: i for i, name in enumerate(self.node_names)}

    def _load_core_arrays(self, world: Any) -> None:
        ds = self.ds
        # A few dense 1-D numeric fields are cheap compared with millions of
        # Python objects and make the early-tail CDF genuinely O(log n) per draw.
        self.profile_cell = np.asarray(ds.variables["profile_cell"][:], dtype=np.int64)
        self.profile_node = np.asarray(ds.variables["profile_node"][:], dtype=np.int64)
        self.profile_loss = np.asarray(ds.variables["profile_loss_intensity"][:], dtype=np.float64)
        self.profile_observation = np.asarray(ds.variables["profile_observation_rate"][:], dtype=np.float64)
        self.profile_arch = np.asarray(ds.variables["profile_archaeological_intensity"][:], dtype=np.float64)
        self.profile_context = np.asarray(ds.variables["profile_context_completeness"][:], dtype=np.float64)
        self.profile_hoard = np.asarray(ds.variables["profile_hoard_prior"][:], dtype=np.float64)
        self.mean_route = np.asarray(ds.variables["profile_mean_route_distance_from_origin_km"][:], dtype=np.float64)
        self.mean_physical = np.asarray(ds.variables["profile_mean_expected_physical_crossings"][:], dtype=np.float64)
        self.mean_field = np.asarray(ds.variables["profile_mean_expected_field_crossings"][:], dtype=np.float64)

        self.cell_bundle = np.asarray(ds.variables["cell_bundle"][:], dtype=np.int64)
        self.cell_family = np.asarray(ds.variables["cell_family"][:], dtype=np.int64)
        self.cell_class = np.asarray(ds.variables["cell_object_class"][:], dtype=np.int64)
        self.cell_date = np.asarray(ds.variables["cell_date_bc"][:], dtype=np.int64)
        self.cell_origin = np.asarray(ds.variables["cell_origin_node"][:], dtype=np.int64)
        self.cell_destination = np.asarray(ds.variables["cell_destination_node"][:], dtype=np.int64)
        self.site_ptr = np.asarray(ds.variables["site_ptr"][:], dtype=np.int64)

        if self.profile_cell.size != self.profile_count or self.profile_node.size != self.profile_count:
            raise ValueError("runtime profile arrays are incomplete")
        if np.any(self.profile_cell < 0) or np.any(self.profile_cell >= self.cell_count):
            raise ValueError("runtime profile_cell contains out-of-range production-cell ids")
        if np.any(self.profile_node < 0) or np.any(self.profile_node >= len(self.node_names)):
            raise ValueError("runtime profile_node contains out-of-range node ids")

        missing_nodes = [name for name in self.node_names if name not in world.nodes]
        if missing_nodes:
            raise ValueError(
                "runtime/world geography mismatch; runtime nodes absent from shared world: "
                + ", ".join(missing_nodes[:8])
            )

    def _build_sampling_indexes(self, world: Any) -> None:
        # Tail/exceptionality are exactly the existing acquisition definitions,
        # evaluated on profile means rather than millions of exact step rows.
        incidence_by_cell = np.asarray(
            [
                float(getattr(world, "bundle_incidence", {}).get(self.bundle_names[int(bid)], 1.0))
                for bid in self.cell_bundle
            ],
            dtype=np.float64,
        )
        origin_region_by_cell = np.asarray(
            [med.REGION_BY_NODE.get(self.node_names[int(nid)], "other") for nid in self.cell_origin],
            dtype=object,
        )
        loss_region = np.asarray(
            [med.REGION_BY_NODE.get(self.node_names[int(nid)], "other") for nid in self.profile_node],
            dtype=object,
        )
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

        archaeological_yield = np.clip(
            .15 + .85 * np.log1p(np.maximum(0.0, self.profile_arch)) / 12.0,
            .05,
            1.0,
        )
        recoverability = np.clip(self.profile_observation / .03, .05, 1.0)
        novelty = np.clip(.20 + .80 * self.exceptionality, .05, 1.0)
        anti_leak = np.clip(1.08 - self.profile_context, .05, 1.0)
        exceptional_loss = np.clip(.12 + .88 * self.exceptionality, .05, 1.0)
        dims = np.column_stack(
            [archaeological_yield, recoverability, novelty, anti_leak, exceptional_loss]
        )
        poari = _weighted_harmonic_matrix(dims, [.14, .15, .22, .19, .30])
        base_kernel = np.sqrt(np.maximum(1e-12, self.profile_arch)) * np.square(.18 + poari)

        self.tail_ids = np.flatnonzero(self.tail_mask).astype(np.int64)
        self.ordinary_ids = np.flatnonzero(~self.tail_mask).astype(np.int64)
        tail_w = base_kernel[self.tail_ids] * 3.0
        ordinary_w = base_kernel[self.ordinary_ids] * 1.8
        self.tail_cdf = np.cumsum(np.where(np.isfinite(tail_w), tail_w, 0.0))
        self.ordinary_cdf = np.cumsum(np.where(np.isfinite(ordinary_w), ordinary_w, 0.0))

        hoard_mask = self.profile_hoard > .02
        self.hoard_ids = np.flatnonzero(hoard_mask).astype(np.int64)
        if self.hoard_ids.size:
            lam = np.maximum(1e-12, self.profile_arch[self.hoard_ids] * self.profile_hoard[self.hoard_ids])
            self.hoard_cdf = np.cumsum(np.power(lam, .70))
        else:
            self.hoard_ids = np.arange(self.profile_count, dtype=np.int64)
            self.hoard_cdf = np.cumsum(np.power(np.maximum(1e-12, self.profile_arch), .70))

    def profile_ids_at_site(self, node_id: str) -> np.ndarray:
        nid = self.node_index.get(str(node_id))
        if nid is None:
            return np.empty(0, dtype=np.int64)
        a, z = int(self.site_ptr[nid]), int(self.site_ptr[nid + 1])
        if z <= a:
            return np.empty(0, dtype=np.int64)
        return np.asarray(self.ds.variables["site_profile_index"][a:z], dtype=np.int64)

    def build_sites(self, world: Any) -> Dict[str, campaign.SiteOpportunity]:
        """Aggregate site action coordinates without retaining profile-id lists."""
        sites: Dict[str, campaign.SiteOpportunity] = {}
        dep_var = self.ds.variables["profile_deposition_weight"]
        for node_id in self.node_names:
            ids = self.profile_ids_at_site(node_id)
            if ids.size == 0:
                continue
            node = world.nodes[node_id]
            arch = self.profile_arch[ids]
            loss = self.profile_loss[ids]
            cells = self.profile_cell[ids]
            classes = self.cell_class[cells]
            route = self.mean_route[ids]
            physical = self.mean_physical[ids]
            field = self.mean_field[ids]
            deposition = np.asarray(dep_var[ids, :], dtype=np.float64)

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
            site.class_mass.update(
                {
                    self.class_names[i]: float(value)
                    for i, value in enumerate(class_mass)
                    if float(value) > 0.0
                }
            )
            dep_mass = np.sum(deposition * arch[:, None], axis=0)
            site.deposition_mass.update(
                {
                    self.deposition_modes[i]: float(value)
                    for i, value in enumerate(dep_mass)
                    if float(value) > 0.0
                }
            )
            site.route_km_sum = float(np.sum(arch * route))
            site.route_km_sq_sum = float(np.sum(arch * route * route))
            site.physical_cross_sum = float(np.sum(arch * physical))
            site.field_cross_sum = float(np.sum(arch * field))
            # ``site.strata`` intentionally remains empty.  CSR pointers own the
            # profile membership; duplicating them as Python ints would recreate
            # the old memory problem.
            sites[node_id] = site
        return sites

    def source_mix_for_cell(self, cid: int) -> Dict[str, float]:
        ptr = self.ds.variables["cell_source_ptr"]
        a, z = int(ptr[cid]), int(ptr[cid + 1])
        ids = np.asarray(self.ds.variables["cell_source_id"][a:z], dtype=np.int64)
        weights = np.asarray(self.ds.variables["cell_source_weight"][a:z], dtype=np.float64)
        return {self.source_names[int(i)]: float(w) for i, w in zip(ids, weights)}

    def cell_object_class(self, pid: int) -> str:
        cid = int(self.profile_cell[int(pid)])
        return self.class_names[int(self.cell_class[cid])]

    def cell_date_bc(self, pid: int) -> int:
        return int(self.cell_date[int(self.profile_cell[int(pid)])])

    def _draw_moment(self, pid: int, name: str, rng: np.random.Generator | None) -> float:
        mean = float(self.ds.variables[f"profile_mean_{name}"][pid])
        if rng is None:
            value = mean
        else:
            var = max(0.0, float(self.ds.variables[f"profile_var_{name}"][pid]))
            value = mean if var <= 1e-18 else float(rng.normal(mean, math.sqrt(var)))
        if name == "expected_source_entropy":
            return float(np.clip(value, 0.0, 1.0))
        return max(0.0, float(value))

    def materialize(self, pid: int, rng: np.random.Generator | None = None) -> intensity.LossStratum:
        """Materialize one profile as the existing campaign's lightweight boundary object.

        Profile means drive selection.  At materialization time the six preserved
        marginal variances may be sampled independently because the v1 runtime
        stores moments but not covariance.  This approximation is explicit in the
        sampler report; it never changes the profile's loss/deposition weights.
        """
        pid = int(pid)
        if not 0 <= pid < self.profile_count:
            raise IndexError(pid)
        cid = int(self.profile_cell[pid])
        node_id = self.node_names[int(self.profile_node[pid])]

        production_cell = intensity.ProductionCell(
            bundle_id=self.bundle_names[int(self.cell_bundle[cid])],
            bundle_family=self.family_names[int(self.cell_family[cid])],
            object_class=self.class_names[int(self.cell_class[cid])],
            date_bc=int(self.cell_date[cid]),
            origin=self.node_names[int(self.cell_origin[cid])],
            destination=self.node_names[int(self.cell_destination[cid])],
            production_intensity=float(self.ds.variables["cell_production_intensity"][cid]),
            circulation_seed_intensity=float(self.ds.variables["cell_circulation_seed_intensity"][cid]),
            source_mix=self.source_mix_for_cell(cid),
            recycle_mean=float(self.ds.variables["cell_recycle_mean"][cid]),
        )

        deposition_row = np.asarray(self.ds.variables["profile_deposition_weight"][pid, :], dtype=np.float64)
        deposition = {
            name: float(value)
            for name, value in zip(self.deposition_modes, deposition_row)
            if float(value) > 0.0
        }
        field_row = np.asarray(self.ds.variables["cell_transport_field_mix"][cid, :], dtype=np.float64)
        field_mix = {
            name: float(value)
            for name, value in zip(self.transport_fields, field_row)
            if float(value) > 0.0
        }
        step_min = int(self.ds.variables["profile_step_min"][pid])
        step_max = int(self.ds.variables["profile_step_max"][pid])
        if rng is None or step_max <= step_min:
            step = int(round(.5 * (step_min + step_max)))
        else:
            step = int(rng.integers(step_min, step_max + 1))

        return intensity.LossStratum(
            production_cell=production_cell,
            node_id=node_id,
            step=step,
            loss_intensity=float(self.profile_loss[pid]),
            deposition_mode_weights=deposition,
            expected_recycle_count=self._draw_moment(pid, "expected_recycle_count", rng),
            expected_repair_count=self._draw_moment(pid, "expected_repair_count", rng),
            expected_source_entropy=self._draw_moment(pid, "expected_source_entropy", rng),
            expected_field_crossings=self._draw_moment(pid, "expected_field_crossings", rng),
            expected_physical_crossings=self._draw_moment(pid, "expected_physical_crossings", rng),
            route_distance_from_origin_km=self._draw_moment(pid, "route_distance_from_origin_km", rng),
            field_mix=field_mix,
        )

    def flow_summary(self) -> Dict[str, Any]:
        raw = getattr(self.ds, "flow_summary_json", "{}")
        try:
            flow = dict(json.loads(str(raw)))
        except (TypeError, json.JSONDecodeError):
            flow = {}
        # Existing masters may contain the historical diagnostic that treated
        # recycling as an external source.  Prefer the corrected endpoint attrs.
        if hasattr(self.ds, "endpoint_conservation_error"):
            if "conservation_error" in flow:
                flow["legacy_conservation_error_reported"] = flow["conservation_error"]
            if "relative_conservation_error" in flow:
                flow["legacy_relative_conservation_error_reported"] = flow["relative_conservation_error"]
            flow["conservation_error"] = float(self.ds.endpoint_conservation_error)
            flow["relative_conservation_error"] = float(self.ds.endpoint_relative_conservation_error)
            flow["conservation_semantics"] = "endpoint closure; recycle/transfer are internal throughput"
        flow["runtime_profiles"] = int(self.profile_count)
        flow["runtime_production_cells"] = int(self.cell_count)
        return flow

    def fingerprint(self) -> str:
        master = str(getattr(self.ds, "master_sha256", ""))
        release = str(getattr(self.ds, "release_invariants", ""))
        return f"{RUNTIME_SCHEMA}:{master[:16]}:{self.profile_count}:{self.cell_count}:{release}"


class ECMWFAcquisitionCampaignSampler(campaign.AcquisitionCampaignSampler):
    """300-object career whose latent candidate field stays inside NetCDF."""

    def __init__(self, *args: Any, runtime_path: Path = DEFAULT_RUNTIME, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self.runtime_path = Path(runtime_path)
        self.runtime_store: RuntimeProfileStore | None = None
        self.runtime_fingerprint: str | None = None

    def close_runtime(self) -> None:
        if self.runtime_store is not None:
            self.runtime_store.close()
            self.runtime_store = None

    def prepare_candidates(self) -> None:
        if not getattr(self.world, "workshops", None) or not getattr(self.world, "sources", None):
            raise RuntimeError("ECMWF acquisition still requires the shared world sources/workshops")
        store = RuntimeProfileStore(self.runtime_path, self.world)
        self.runtime_store = store
        self.runtime_fingerprint = store.fingerprint()
        self.flow_reports = []
        self.flow_summary = store.flow_summary()
        # Deliberately leave the legacy list empty.  All four latent-profile draws
        # below operate on arrays/CSR pointers and materialize only one selected row.
        self.loss_strata = []
        self.sites = store.build_sites(self.world)
        if not self.sites:
            store.close()
            self.runtime_store = None
            raise RuntimeError("ECMWF runtime contains no archaeological sites")
        self._prepared = True

    def _store(self) -> RuntimeProfileStore:
        if self.runtime_store is None:
            raise RuntimeError("runtime profile store is not prepared")
        return self.runtime_store

    def _materialize_profile(self, pid: int, career_no: int, purpose: str) -> intensity.LossStratum:
        rng = np.random.default_rng(
            campaign._seed64(self.seeds.archaeology_seed, "ecmwf_profile", purpose, career_no, int(pid))
        )
        return self._store().materialize(int(pid), rng)

    def _profile_dims(self, pid: int) -> Dict[str, float]:
        store = self._store()
        arch = float(store.profile_arch[pid])
        exception = float(store.exceptionality[pid])
        return {
            "archaeological_yield": float(np.clip(.15 + .85 * math.log1p(arch) / 12.0, .05, 1.0)),
            "recoverability": float(np.clip(store.profile_observation[pid] / .03, .05, 1.0)),
            "novelty": float(np.clip(.20 + .80 * exception, .05, 1.0)),
            "anti_leak": float(np.clip(1.08 - store.profile_context[pid], .05, 1.0)),
            "exceptional_loss": float(np.clip(.12 + .88 * exception, .05, 1.0)),
        }

    def _sample_stray(self, career_no: int):
        store = self._store()
        want_tail = bool(self.rng.random() < campaign.EARLY_TAIL_TARGET)
        if want_tail and store.tail_ids.size:
            pid = _sample_cdf(self.rng, store.tail_ids, store.tail_cdf)
        elif (not want_tail) and store.ordinary_ids.size:
            pid = _sample_cdf(self.rng, store.ordinary_ids, store.ordinary_cdf)
        else:
            ids = np.arange(store.profile_count, dtype=np.int64)
            pid = _sample_weighted_id(self.rng, ids, np.sqrt(np.maximum(1e-12, store.profile_arch)))
        s = self._materialize_profile(pid, career_no, "stray")
        dims = self._profile_dims(pid)
        weights = {
            "archaeological_yield": .14,
            "recoverability": .15,
            "novelty": .22,
            "anti_leak": .19,
            "exceptional_loss": .30,
        }
        action = campaign.ResearchAction(
            action_id=f"A-{career_no:03d}",
            regime="stray_tail",
            site_node=s.node_id,
            p=-1.0,
            dimensions=dims,
            poari_score=campaign.p_measure(dims, weights, -1.0),
            temperature=.80,
            block_size=1,
            question="What kind of world could have put this poorly contextualized object here?",
        )
        self.research_actions.append(action)
        return s, action

    def _choose_hoard(self, career_no: int) -> None:
        store = self._store()
        pid = _sample_cdf(self.rng, store.hoard_ids, store.hoard_cdf)
        anchor = self._materialize_profile(pid, career_no, "hoard_anchor")
        event_bc = max(950, int(anchor.production_cell.date_bc - self.rng.integers(45, 125)))
        node = self.world.nodes[anchor.node_id]
        discovery_year = int(np.clip(round(self.rng.normal(1972, 32)), 1870, 2025))
        hoard_id = f"H-CAM-{campaign._seed64(self.seeds.career_seed, anchor.node_id, event_bc) % 100000:05d}"
        site_id = f"SITE-H-{campaign._seed64(anchor.node_id, hoard_id) % 100000:05d}"
        self._hoard = {
            "hoard_id": hoard_id,
            "node_id": anchor.node_id,
            "region": med.REGION_BY_NODE.get(anchor.node_id, "other"),
            "event_bc": event_bc,
            "discovery_year_ce": discovery_year,
            "site_id": site_id,
            "lon": float(node.lon + self.rng.normal(0, .0025)),
            "lat": float(node.lat + self.rng.normal(0, .0018)),
            "anchor_bundle_family": anchor.production_cell.bundle_family,
            "runtime_profile_id_truth": int(pid),
        }
        self._hoard_class_counts.clear()
        self.research_actions.append(
            campaign.ResearchAction(
                action_id=f"A-{career_no:03d}-HOARD",
                regime="random_hoard",
                site_node=anchor.node_id,
                p=0.0,
                dimensions={"random_archaeological_draw": 1.0},
                poari_score=1.0,
                temperature=1.0,
                block_size=30,
                question="What structure, if any, recurs inside one context that was not chosen for explanatory value?",
            )
        )

    def _acquire_hoard_object(self, career_no: int, slot: Any):
        if self._hoard is None:
            self._choose_hoard(career_no)
        assert self._hoard is not None
        store = self._store()
        event_bc = int(self._hoard["event_bc"])
        node_id = str(self._hoard["node_id"])
        ids = store.profile_ids_at_site(node_id)
        if ids.size == 0:
            ids = np.arange(store.profile_count, dtype=np.int64)
        dates = store.cell_date[store.profile_cell[ids]]
        mask = (dates >= event_bc) & (dates <= event_bc + 260)
        pool = ids[mask]
        if pool.size == 0:
            pool = ids

        class_ids = store.cell_class[store.profile_cell[pool]]
        classes = [store.class_names[int(cid)] for cid in class_ids]
        diversity = np.asarray(
            [1.0 / (1.0 + .55 * self._hoard_class_counts[name]) for name in classes],
            dtype=np.float64,
        )
        weights = (
            np.power(np.maximum(1e-10, store.profile_arch[pool]), .58)
            * (.20 + store.profile_hoard[pool])
            * diversity
        )
        pid = _sample_weighted_id(self.rng, pool, weights)
        selected_class = store.cell_object_class(pid)
        self._hoard_class_counts[selected_class] += 1
        s = self._materialize_profile(pid, career_no, "hoard_object")
        action = self.research_actions[-1]
        return self._candidate_from_stratum(s, career_no, slot, action, hoard=self._hoard)

    def _sample_stratum_at_site(self, node_id: str, regime_name: str) -> intensity.LossStratum:
        store = self._store()
        pool = store.profile_ids_at_site(node_id)
        if pool.size == 0:
            raise RuntimeError(f"runtime site has no profiles: {node_id}")

        local_class = Counter()
        if self._active_action:
            action_objects = [
                oid
                for oid, meta in self.acquisition_by_object.items()
                if meta.get("action_id") == self._active_action.action_id
            ]
            for oid in action_objects:
                c = self._candidate_by_id.get(oid)
                if c:
                    local_class[c.object_class] += 1

        class_ids = store.cell_class[store.profile_cell[pool]]
        diversity = np.asarray(
            [
                1.0 / (1.0 + .42 * local_class[store.class_names[int(cid)]])
                for cid in class_ids
            ],
            dtype=np.float64,
        )
        weights = np.power(np.maximum(1e-12, store.profile_arch[pool]), .62) * diversity
        if regime_name in {"discriminating_dig", "network_reconstruction"}:
            weights *= (
                1.0
                + .35 * np.minimum(1.0, store.mean_physical[pool])
                + .30 * np.minimum(1.0, store.mean_field[pool] / .18)
            )
        elif regime_name == "falsification_probe":
            weights *= (
                1.0
                + .50 * (~store.tail_mask[pool]).astype(np.float64)
                + .35 * (1.0 - store.profile_context[pool])
            )
        pid = _sample_weighted_id(self.rng, pool, weights)
        # ``career_no`` is not part of this inherited method's signature.  The
        # active action id is stable and sufficient to separate moment draws.
        career_hint = int(str(self._active_action.action_id).split("-")[1]) if self._active_action else 0
        return self._materialize_profile(pid, career_hint, regime_name)

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
            "site_membership_storage": "NetCDF CSR pointers",
            "materialization_boundary": "one selected profile -> one LossStratum -> one physical artefact",
            "profile_variance_sampling": "independent marginal normal, nonnegative; source entropy clipped [0,1]",
            "profile_covariance_available": False,
        }
        report["poari_action_rule"] = (
            "POARI ranks research actions/sites. Runtime profiles are sampled only after action selection; "
            "p=-1 remains harmonic weak-link-sensitive."
        )
        return report
