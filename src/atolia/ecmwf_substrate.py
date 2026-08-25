from __future__ import annotations

"""ECMWF-style field products for the Atolia latent archaeology substrate.

The simulation is authored with Python objects because that is convenient for
physics.  It must not be *stored* as 23 million repeated JSON object graphs.
This module converts the existing gzip JSON developer substrate into two NetCDF4
products without rerunning the 3,200-workshop simulation:

* MASTER: lossless-by-field (float64) state field with repeated categorical and
  production-cell data dictionary-coded and pointer-linked.
* RUNTIME: the same cell/profile field and indexes, but without the individual
  transfer-step states.  Profile moments preserve the loss-intensity-weighted
  mean and variance of each dynamic coordinate.

Hierarchy
---------
state -> profile=(production_cell, loss_node) -> production_cell
                                        |-> node
production_cell -> bundle/family/class/origin/destination
production_cell -> source mixture through CSR cell_source_ptr

Indexes
-------
site_ptr/site_profile_index     : all profiles at one loss node
class_ptr/class_profile_index   : all profiles for one object class
bundle_ptr/bundle_profile_index : all profiles for one bundle

No POARI p-measure is evaluated or rewritten here.  In particular, this module
cannot alter the p=-1 harmonic operator.
"""

import argparse
import gzip
import hashlib
import json
import math
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, MutableMapping, Sequence

import ijson
import numpy as np
from netCDF4 import Dataset

import archaeological_condensation_v3 as condensation
import provenance_field as base
import transport_fields as fields


MASTER_SCHEMA = "atolia.ecmwf-master.v1"
RUNTIME_SCHEMA = "atolia.ecmwf-runtime.v1"
DEFAULT_JSON = Path("cache/atolia_campaign_substrate_v1.json.gz")
DEFAULT_MASTER = Path("cache/atolia_master_v1.nc")
DEFAULT_RUNTIME = Path("cache/atolia_runtime_v1.nc")
DEFAULT_VOCAB = Path("cache/atolia_vocabulary_v1.json")
DEFAULT_RELEASE_INVARIANTS = "atolia-release-invariants-v1"
DEFAULT_CHUNK = 131_072

# Must mirror the acquisition model.  These are archaeological observation
# coordinates, not hidden source/workshop truth.
_CONTEXT_COMPLETENESS = {
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


def _open_gzip(path: Path, mode: str = "rb"):
    return gzip.open(path, mode) if path.suffix == ".gz" else path.open(mode)


def _read_prefix_metadata(path: Path) -> Dict[str, Any]:
    """Read top-level metadata before loss_strata without materializing the list."""
    marker = b'"loss_strata":['
    buf = bytearray()
    with _open_gzip(path, "rb") as fh:
        while True:
            block = fh.read(1024 * 1024)
            if not block:
                raise ValueError("loss_strata array marker not found")
            buf.extend(block)
            pos = buf.find(marker)
            if pos >= 0:
                prefix = bytes(buf[:pos])
                # build_payload writes loss_strata after all large metadata.  The
                # release-invariants tag was appended after it, so it is supplied
                # separately by the converter CLI/root attribute.
                synthetic = prefix + b'"loss_strata":[]}'
                return json.loads(synthetic.decode("utf-8"))
            if len(buf) > 128 * 1024 * 1024:
                raise ValueError("unexpectedly large metadata prefix before loss_strata")


def _canonical_cell_key(cell: Mapping[str, Any]) -> tuple[Any, ...]:
    return (
        str(cell["bundle_id"]),
        str(cell["bundle_family"]),
        str(cell["object_class"]),
        int(cell["date_bc"]),
        str(cell["origin"]),
        str(cell["destination"]),
        float(cell["production_intensity"]),
        float(cell["circulation_seed_intensity"]),
        float(cell["recycle_mean"]),
        tuple(sorted((str(k), float(v)) for k, v in cell.get("source_mix", {}).items())),
    )


def _observation_rate(deposition: Mapping[str, float]) -> float:
    value = 0.0
    for mode, p_mode in deposition.items():
        value += (
            float(p_mode)
            * float(condensation.MODE_SURVIVAL.get(mode, .46))
            * float(condensation.MODE_DISCOVERY.get(mode, .018))
            * float(condensation.MODE_RECORD.get(mode, .44))
        )
    return max(1e-12, float(value))


def _context_completeness(deposition: Mapping[str, float]) -> float:
    return float(
        sum(float(p) * _CONTEXT_COMPLETENESS.get(str(mode), .50) for mode, p in deposition.items())
    )


def _hoard_prior(deposition: Mapping[str, float]) -> float:
    return float(sum(float(deposition.get(mode, 0.0)) for mode in _HOARD_MODES))


def _corrected_closure(flow: Mapping[str, Any]) -> Dict[str, float]:
    """Endpoint closure; recycle is internal throughput, not an external source."""
    seed = float(flow.get("circulation_seed", 0.0))
    rhs = sum(float(flow.get(k, 0.0)) for k in ("return_flux", "loss_flux", "retire_flux", "residual_active"))
    err = seed - rhs
    return {
        "endpoint_conservation_error": err,
        "endpoint_relative_conservation_error": err / max(1.0, seed),
        "recycle_flux_internal_throughput": float(flow.get("recycle_flux", 0.0)),
        "transfer_flux_internal_throughput": float(flow.get("transfer_flux", 0.0)),
    }


class _Lookup:
    def __init__(self, ds: Dataset, name: str):
        self.name = name
        ds.createDimension(name, None)
        self.var = ds.createVariable(f"{name}_name", str, (name,))
        self.index: Dict[str, int] = {}
        self.values: list[str] = []

    def get(self, value: Any) -> int:
        text = str(value)
        found = self.index.get(text)
        if found is not None:
            return found
        idx = len(self.values)
        self.index[text] = idx
        self.values.append(text)
        self.var[idx] = text
        return idx


@dataclass
class _ProfileAccumulator:
    count: int = 0
    weight: float = 0.0
    step_min: int = 255
    step_max: int = 0
    wx: Dict[str, float] = field(default_factory=dict)
    wx2: Dict[str, float] = field(default_factory=dict)

    def add(self, row: Mapping[str, Any]) -> None:
        w = max(0.0, float(row["loss_intensity"]))
        self.count += 1
        self.weight += w
        step = int(row["step"])
        self.step_min = min(self.step_min, step)
        self.step_max = max(self.step_max, step)
        for name in (
            "expected_recycle_count",
            "expected_repair_count",
            "expected_source_entropy",
            "expected_field_crossings",
            "expected_physical_crossings",
            "route_distance_from_origin_km",
        ):
            x = float(row[name])
            self.wx[name] = self.wx.get(name, 0.0) + w * x
            self.wx2[name] = self.wx2.get(name, 0.0) + w * x * x

    def mean_var(self, name: str) -> tuple[float, float]:
        if self.weight <= 0.0:
            return 0.0, 0.0
        mean = self.wx.get(name, 0.0) / self.weight
        second = self.wx2.get(name, 0.0) / self.weight
        return float(mean), float(max(0.0, second - mean * mean))


class MasterWriter:
    """Append-only NetCDF writer with categorical dictionaries and CSR pointers."""

    STATE_FLOATS = (
        "expected_recycle_count",
        "expected_repair_count",
        "expected_source_entropy",
        "expected_field_crossings",
        "expected_physical_crossings",
        "route_distance_from_origin_km",
    )

    def __init__(
        self,
        path: Path,
        metadata: Mapping[str, Any],
        release_invariants: str,
        chunk_rows: int = DEFAULT_CHUNK,
    ) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self.chunk_rows = int(max(4096, chunk_rows))
        self.ds = Dataset(path, "w", format="NETCDF4")
        ds = self.ds
        ds.schema = MASTER_SCHEMA
        ds.product_kind = "developer_master"
        ds.release_invariants = str(release_invariants)
        for key in ("world_seed", "workshop_count", "intensity_steps", "hypothesis_sha256", "intensity_model_version"):
            if key in metadata:
                setattr(ds, key, metadata[key])
        flow = dict(metadata.get("flow_summary", {}))
        ds.flow_summary_json = json.dumps(flow, sort_keys=True, separators=(",", ":"))
        for key, value in _corrected_closure(flow).items():
            setattr(ds, key, float(value))
        ds.geography_report_json = json.dumps(metadata.get("geography_report", {}), sort_keys=True, separators=(",", ":"))

        self.bundle = _Lookup(ds, "bundle")
        self.family = _Lookup(ds, "family")
        self.object_class = _Lookup(ds, "object_class")
        self.node = _Lookup(ds, "node")
        self.source = _Lookup(ds, "source")

        self.modes = tuple(str(x) for x in base.DEPOSITION_MODES)
        self.field_names = tuple(str(x) for x in fields.FIELD_NAMES)
        ds.createDimension("deposition_mode", len(self.modes))
        ds.createDimension("transport_field", len(self.field_names))
        mode_var = ds.createVariable("deposition_mode_name", str, ("deposition_mode",))
        field_var = ds.createVariable("transport_field_name", str, ("transport_field",))
        mode_var[:] = np.asarray(self.modes, dtype=object)
        field_var[:] = np.asarray(self.field_names, dtype=object)
        self.mode_index = {name: i for i, name in enumerate(self.modes)}
        self.field_index = {name: i for i, name in enumerate(self.field_names)}

        for dim in ("production_cell", "cell_source_ptr_dim", "cell_source_entry", "profile", "state"):
            ds.createDimension(dim, None)

        c1 = (min(16384, self.chunk_rows),)
        s1 = (self.chunk_rows,)
        p1 = (min(65536, self.chunk_rows),)
        def cv(name: str, dtype: str, dims: tuple[str, ...], chunks: tuple[int, ...] | None = None):
            return ds.createVariable(name, dtype, dims, zlib=True, complevel=4, shuffle=True, chunksizes=chunks)

        # Cell table.  Repeated production-cell dictionaries in JSON become one row.
        self.cell_bundle = cv("cell_bundle", "u4", ("production_cell",), c1)
        self.cell_family = cv("cell_family", "u4", ("production_cell",), c1)
        self.cell_class = cv("cell_object_class", "u4", ("production_cell",), c1)
        self.cell_date = cv("cell_date_bc", "i2", ("production_cell",), c1)
        self.cell_origin = cv("cell_origin_node", "u4", ("production_cell",), c1)
        self.cell_destination = cv("cell_destination_node", "u4", ("production_cell",), c1)
        self.cell_production = cv("cell_production_intensity", "f8", ("production_cell",), c1)
        self.cell_seed = cv("cell_circulation_seed_intensity", "f8", ("production_cell",), c1)
        self.cell_recycle = cv("cell_recycle_mean", "f8", ("production_cell",), c1)
        self.cell_field_mix = cv(
            "cell_transport_field_mix", "f8", ("production_cell", "transport_field"),
            (min(4096, self.chunk_rows), len(self.field_names)),
        )
        self.cell_source_ptr = cv("cell_source_ptr", "u8", ("cell_source_ptr_dim",), c1)
        self.cell_source_id = cv("cell_source_id", "u4", ("cell_source_entry",), c1)
        self.cell_source_weight = cv("cell_source_weight", "f8", ("cell_source_entry",), c1)
        self.cell_source_ptr[0] = 0
        self.source_entry_count = 0

        # Profile=(cell,node).  Deposition is invariant across propagation step and
        # is stored exactly once here after validation.
        self.profile_cell = cv("profile_cell", "u4", ("profile",), p1)
        self.profile_node = cv("profile_node", "u4", ("profile",), p1)
        self.profile_deposition = cv(
            "profile_deposition_weight", "f8", ("profile", "deposition_mode"),
            (min(8192, self.chunk_rows), len(self.modes)),
        )
        self.profile_loss = cv("profile_loss_intensity", "f8", ("profile",), p1)
        self.profile_state_count = cv("profile_state_count", "u1", ("profile",), p1)
        self.profile_step_min = cv("profile_step_min", "u1", ("profile",), p1)
        self.profile_step_max = cv("profile_step_max", "u1", ("profile",), p1)
        self.profile_observation = cv("profile_observation_rate", "f8", ("profile",), p1)
        self.profile_arch = cv("profile_archaeological_intensity", "f8", ("profile",), p1)
        self.profile_context = cv("profile_context_completeness", "f8", ("profile",), p1)
        self.profile_hoard = cv("profile_hoard_prior", "f8", ("profile",), p1)
        self.profile_mean: Dict[str, Any] = {}
        self.profile_var: Dict[str, Any] = {}
        for name in self.STATE_FLOATS:
            self.profile_mean[name] = cv(f"profile_mean_{name}", "f8", ("profile",), p1)
            self.profile_var[name] = cv(f"profile_var_{name}", "f8", ("profile",), p1)

        # Exact transfer-step state field points to profile rather than repeating
        # production-cell, node, deposition, field names, etc.
        self.state_profile = cv("state_profile", "u4", ("state",), s1)
        self.state_step = cv("state_step", "u1", ("state",), s1)
        self.state_loss = cv("state_loss_intensity", "f8", ("state",), s1)
        self.state_float: Dict[str, Any] = {
            name: cv(f"state_{name}", "f8", ("state",), s1) for name in self.STATE_FLOATS
        }

        self.cell_key_to_id: Dict[tuple[Any, ...], int] = {}
        self.cell_field_reference: Dict[int, tuple[float, ...]] = {}
        self.profile_id_by_current_node: Dict[int, int] = {}
        self.profile_deposition_reference: Dict[int, tuple[float, ...]] = {}
        self.profile_acc: Dict[int, _ProfileAccumulator] = {}
        self.current_cell_id: int | None = None
        self.closed_cells: set[int] = set()
        self.cell_count = 0
        self.profile_count = 0
        self.state_count = 0
        self._state_buffer: Dict[str, list[Any]] = {
            "profile": [], "step": [], "loss": [], **{name: [] for name in self.STATE_FLOATS}
        }

    def _intern_cell(self, cell: Mapping[str, Any], field_mix: Mapping[str, Any]) -> int:
        key = _canonical_cell_key(cell)
        found = self.cell_key_to_id.get(key)
        mix = tuple(float(field_mix.get(name, 0.0)) for name in self.field_names)
        if found is not None:
            ref = self.cell_field_reference[found]
            if not np.allclose(ref, mix, rtol=0.0, atol=1e-14):
                raise ValueError(f"transport field mix changed inside production cell {found}")
            return found

        cid = self.cell_count
        self.cell_count += 1
        self.cell_key_to_id[key] = cid
        self.cell_field_reference[cid] = mix
        self.cell_bundle[cid] = self.bundle.get(cell["bundle_id"])
        self.cell_family[cid] = self.family.get(cell["bundle_family"])
        self.cell_class[cid] = self.object_class.get(cell["object_class"])
        self.cell_date[cid] = int(cell["date_bc"])
        self.cell_origin[cid] = self.node.get(cell["origin"])
        self.cell_destination[cid] = self.node.get(cell["destination"])
        self.cell_production[cid] = float(cell["production_intensity"])
        self.cell_seed[cid] = float(cell["circulation_seed_intensity"])
        self.cell_recycle[cid] = float(cell["recycle_mean"])
        self.cell_field_mix[cid, :] = np.asarray(mix, dtype=np.float64)

        for source_name, weight in sorted(cell.get("source_mix", {}).items()):
            idx = self.source_entry_count
            self.cell_source_id[idx] = self.source.get(source_name)
            self.cell_source_weight[idx] = float(weight)
            self.source_entry_count += 1
        self.cell_source_ptr[cid + 1] = self.source_entry_count
        return cid

    def _start_cell(self, cid: int) -> None:
        if self.current_cell_id == cid:
            return
        if self.current_cell_id is not None:
            self._finalize_current_cell()
            self.closed_cells.add(self.current_cell_id)
        if cid in self.closed_cells:
            raise ValueError(
                "input loss_strata are not contiguous by production cell; "
                "the canonical builder is expected to preserve report order"
            )
        self.current_cell_id = cid
        self.profile_id_by_current_node = {}
        self.profile_acc = {}

    def _profile(self, cid: int, node_id: str, deposition: Mapping[str, Any]) -> int:
        nid = self.node.get(node_id)
        found = self.profile_id_by_current_node.get(nid)
        dep = tuple(float(deposition.get(name, 0.0)) for name in self.modes)
        if found is not None:
            ref = self.profile_deposition_reference[found]
            if not np.allclose(ref, dep, rtol=0.0, atol=1e-14):
                raise ValueError(f"deposition weights changed within profile {found}")
            return found
        pid = self.profile_count
        self.profile_count += 1
        self.profile_id_by_current_node[nid] = pid
        self.profile_deposition_reference[pid] = dep
        self.profile_cell[pid] = cid
        self.profile_node[pid] = nid
        self.profile_deposition[pid, :] = np.asarray(dep, dtype=np.float64)
        self.profile_acc[pid] = _ProfileAccumulator()
        return pid

    def append(self, row: Mapping[str, Any]) -> None:
        cell = row["production_cell"]
        cid = self._intern_cell(cell, row.get("field_mix", {}))
        self._start_cell(cid)
        pid = self._profile(cid, str(row["node_id"]), row.get("deposition_mode_weights", {}))
        self.profile_acc[pid].add(row)

        b = self._state_buffer
        b["profile"].append(pid)
        b["step"].append(int(row["step"]))
        b["loss"].append(float(row["loss_intensity"]))
        for name in self.STATE_FLOATS:
            b[name].append(float(row[name]))
        if len(b["profile"]) >= self.chunk_rows:
            self._flush_states()

    def _flush_states(self) -> None:
        b = self._state_buffer
        n = len(b["profile"])
        if not n:
            return
        a, z = self.state_count, self.state_count + n
        self.state_profile[a:z] = np.asarray(b["profile"], dtype=np.uint32)
        self.state_step[a:z] = np.asarray(b["step"], dtype=np.uint8)
        self.state_loss[a:z] = np.asarray(b["loss"], dtype=np.float64)
        for name in self.STATE_FLOATS:
            self.state_float[name][a:z] = np.asarray(b[name], dtype=np.float64)
        self.state_count = z
        for values in b.values():
            values.clear()

    def _finalize_current_cell(self) -> None:
        if self.current_cell_id is None:
            return
        for pid, acc in self.profile_acc.items():
            dep = {
                name: self.profile_deposition_reference[pid][i] for i, name in enumerate(self.modes)
            }
            self.profile_loss[pid] = acc.weight
            self.profile_state_count[pid] = acc.count
            self.profile_step_min[pid] = 0 if acc.step_min == 255 else acc.step_min
            self.profile_step_max[pid] = acc.step_max
            obs = _observation_rate(dep)
            self.profile_observation[pid] = obs
            self.profile_arch[pid] = acc.weight * obs
            self.profile_context[pid] = _context_completeness(dep)
            self.profile_hoard[pid] = _hoard_prior(dep)
            for name in self.STATE_FLOATS:
                mean, var = acc.mean_var(name)
                self.profile_mean[name][pid] = mean
                self.profile_var[name][pid] = var

    def _build_pointer_index(self, key: np.ndarray, count: int, prefix: str) -> None:
        if key.size == 0:
            return
        order = np.argsort(key, kind="stable").astype(np.uint32, copy=False)
        counts = np.bincount(key.astype(np.int64), minlength=count).astype(np.uint64)
        ptr = np.empty(count + 1, dtype=np.uint64)
        ptr[0] = 0
        np.cumsum(counts, out=ptr[1:])
        self.ds.createDimension(f"{prefix}_profile_entry", int(order.size))
        self.ds.createDimension(f"{prefix}_ptr_dim", int(ptr.size))
        iv = self.ds.createVariable(
            f"{prefix}_profile_index", "u4", (f"{prefix}_profile_entry",),
            zlib=True, complevel=4, shuffle=True,
            chunksizes=(min(self.chunk_rows, max(1, int(order.size))),),
        )
        pv = self.ds.createVariable(
            f"{prefix}_ptr", "u8", (f"{prefix}_ptr_dim",),
            zlib=True, complevel=4, shuffle=True,
            chunksizes=(min(65536, max(1, int(ptr.size))),),
        )
        iv[:] = order
        pv[:] = ptr

    def finish(self) -> Dict[str, Any]:
        self._flush_states()
        self._finalize_current_cell()
        if self.current_cell_id is not None:
            self.closed_cells.add(self.current_cell_id)
        ds = self.ds
        ds.state_count = int(self.state_count)
        ds.profile_count = int(self.profile_count)
        ds.production_cell_count = int(self.cell_count)
        ds.cell_source_entry_count = int(self.source_entry_count)

        # Pointer products over the already compact profile field.
        profile_node = np.asarray(self.profile_node[: self.profile_count], dtype=np.int64)
        profile_cell = np.asarray(self.profile_cell[: self.profile_count], dtype=np.int64)
        cell_class = np.asarray(self.cell_class[: self.cell_count], dtype=np.int64)
        cell_bundle = np.asarray(self.cell_bundle[: self.cell_count], dtype=np.int64)
        self._build_pointer_index(profile_node, len(self.node.values), "site")
        self._build_pointer_index(cell_class[profile_cell], len(self.object_class.values), "class")
        self._build_pointer_index(cell_bundle[profile_cell], len(self.bundle.values), "bundle")

        vocab = {
            "schema": "atolia.semantic-vocabulary.v1",
            "counts": {
                "bundle_id": len(self.bundle.values),
                "bundle_family": len(self.family.values),
                "object_class": len(self.object_class.values),
                "node_id": len(self.node.values),
                "source_id": len(self.source.values),
                "deposition_mode": len(self.modes),
                "transport_field": len(self.field_names),
                "production_cell": self.cell_count,
                "profile_cell_node": self.profile_count,
                "loss_state": self.state_count,
            },
            "values": {
                "bundle_id": self.bundle.values,
                "bundle_family": self.family.values,
                "object_class": self.object_class.values,
                "node_id": self.node.values,
                "source_id": self.source.values,
                "deposition_mode": list(self.modes),
                "transport_field": list(self.field_names),
            },
            "pointers": {
                "state_profile": "loss state -> (production cell, loss node) profile",
                "profile_cell": "profile -> production cell",
                "profile_node": "profile -> loss node",
                "cell_source_ptr": "production cell -> sparse source-mixture entries",
                "site_ptr": "loss node -> profile index slice",
                "class_ptr": "object class -> profile index slice",
                "bundle_ptr": "bundle -> profile index slice",
            },
        }
        ds.sync()
        return vocab

    def close(self) -> None:
        self.ds.close()


def _copy_runtime(master_path: Path, runtime_path: Path, chunk_rows: int = DEFAULT_CHUNK) -> None:
    """Copy every master coordinate/profile/index field except exact step states."""
    runtime_path.parent.mkdir(parents=True, exist_ok=True)
    with Dataset(master_path, "r") as src, Dataset(runtime_path, "w", format="NETCDF4") as dst:
        for name in src.ncattrs():
            dst.setncattr(name, src.getncattr(name))
        dst.schema = RUNTIME_SCHEMA
        dst.product_kind = "installer_runtime"
        dst.master_sha256 = _sha256_file(master_path)

        keep_vars = [
            name for name, var in src.variables.items()
            if not name.startswith("state_") and "state" not in var.dimensions
        ]
        needed_dims: set[str] = set()
        for name in keep_vars:
            needed_dims.update(src.variables[name].dimensions)
        for dim_name in needed_dims:
            dim = src.dimensions[dim_name]
            dst.createDimension(dim_name, len(dim))

        for name in keep_vars:
            sv = src.variables[name]
            dtype: Any = str if sv.datatype is str else sv.datatype
            kwargs: Dict[str, Any] = {}
            if dtype is not str and sv.dimensions:
                shape = tuple(len(src.dimensions[d]) for d in sv.dimensions)
                chunks = tuple(max(1, min(int(n), chunk_rows if i == 0 else int(n))) for i, n in enumerate(shape))
                kwargs = {"zlib": True, "complevel": 4, "shuffle": True, "chunksizes": chunks}
            dv = dst.createVariable(name, dtype, sv.dimensions, **kwargs)
            for attr in sv.ncattrs():
                dv.setncattr(attr, sv.getncattr(attr))
            if sv.ndim == 0:
                dv.assignValue(sv.getValue())
            else:
                # Copy large profile tables in slabs rather than materializing them.
                n0 = sv.shape[0]
                if n0 == 0:
                    continue
                if sv.ndim == 1:
                    for a in range(0, n0, chunk_rows):
                        z = min(n0, a + chunk_rows)
                        dv[a:z] = sv[a:z]
                else:
                    for a in range(0, n0, max(4096, chunk_rows // 8)):
                        z = min(n0, a + max(4096, chunk_rows // 8))
                        dv[a:z, ...] = sv[a:z, ...]


def _sha256_file(path: Path, block_size: int = 8 * 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            block = fh.read(block_size)
            if not block:
                return h.hexdigest()
            h.update(block)


def convert(
    source: Path = DEFAULT_JSON,
    master: Path = DEFAULT_MASTER,
    runtime: Path = DEFAULT_RUNTIME,
    vocabulary: Path = DEFAULT_VOCAB,
    *,
    release_invariants: str = DEFAULT_RELEASE_INVARIANTS,
    chunk_rows: int = DEFAULT_CHUNK,
    build_runtime: bool = True,
) -> Dict[str, Any]:
    source = Path(source)
    master = Path(master)
    runtime = Path(runtime)
    vocabulary = Path(vocabulary)
    if not source.exists():
        raise FileNotFoundError(source)
    metadata = _read_prefix_metadata(source)
    writer = MasterWriter(master, metadata, release_invariants, chunk_rows=chunk_rows)
    try:
        with _open_gzip(source, "rb") as fh:
            for i, row in enumerate(ijson.items(fh, "loss_strata.item"), start=1):
                writer.append(row)
                if i % 1_000_000 == 0:
                    print(
                        f"converted {i:,} states -> {writer.profile_count:,} profiles / "
                        f"{writer.cell_count:,} cells",
                        flush=True,
                    )
        vocab = writer.finish()
    finally:
        writer.close()

    vocabulary.parent.mkdir(parents=True, exist_ok=True)
    vocabulary.write_text(json.dumps(vocab, indent=2, ensure_ascii=False), encoding="utf-8")
    if build_runtime:
        _copy_runtime(master, runtime, chunk_rows=chunk_rows)

    report = {
        "source": str(source),
        "source_bytes": source.stat().st_size,
        "master": str(master),
        "master_bytes": master.stat().st_size,
        "master_sha256": _sha256_file(master),
        "runtime": str(runtime) if build_runtime else None,
        "runtime_bytes": runtime.stat().st_size if build_runtime else None,
        "runtime_sha256": _sha256_file(runtime) if build_runtime else None,
        "vocabulary": str(vocabulary),
        "counts": vocab["counts"],
        "corrected_closure": _corrected_closure(metadata.get("flow_summary", {})),
        "release_invariants": release_invariants,
    }
    return report


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Convert the giant Atolia JSON substrate into ECMWF-style NetCDF master/runtime products."
    )
    ap.add_argument("--source", type=Path, default=DEFAULT_JSON)
    ap.add_argument("--master", type=Path, default=DEFAULT_MASTER)
    ap.add_argument("--runtime", type=Path, default=DEFAULT_RUNTIME)
    ap.add_argument("--vocabulary", type=Path, default=DEFAULT_VOCAB)
    ap.add_argument("--release-invariants", default=DEFAULT_RELEASE_INVARIANTS)
    ap.add_argument("--chunk-rows", type=int, default=DEFAULT_CHUNK)
    ap.add_argument("--no-runtime", action="store_true", help="Create only the lossless master product.")
    args = ap.parse_args()
    report = convert(
        args.source,
        args.master,
        args.runtime,
        args.vocabulary,
        release_invariants=args.release_invariants,
        chunk_rows=args.chunk_rows,
        build_runtime=not args.no_runtime,
    )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
