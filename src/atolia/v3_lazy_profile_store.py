from __future__ import annotations

"""Memory-bounded R17 profile access without changing acquisition identity.

The canonical player draw is defined against the *global sequential binary64 CDF*
of ``profiles/recorded_weight``.  Loading all 1.78M profile columns into NumPy just
to preserve that CDF is unnecessary.  This module factors the same CDF through the
existing cell CSR:

    global target -> cell boundary CDF -> exact profile slice inside that cell

Cell boundaries are accumulated by iterating profile weights in their original
order with the same ``running += float(weight)`` operation used by the former
``_ordered_cdf`` implementation.  No ``math.fsum`` cell aggregate is used for
selection, so the selected profile index is bit-for-bit the same as the eager
implementation for every draw.
"""

import math
from pathlib import Path
from typing import Any

import numpy as np
from netCDF4 import Dataset

import v3_frozen_world
import v3_runtime_v3 as runtime_v3


PROFILE_STREAM_CHUNK = 32768


class _VariableView:
    """Tiny proxy that keeps a NetCDF variable on disk and reads only requested rows."""

    def __init__(self, var: Any, dtype: Any) -> None:
        self.var = var
        self.dtype = dtype

    def __len__(self) -> int:
        return int(self.var.shape[0])

    def __getitem__(self, index: Any) -> Any:
        values = np.ma.getdata(self.var[index])
        arr = np.asarray(values, dtype=self.dtype)
        if arr.ndim == 0:
            return arr.item()
        return arr


class LazyProfileCDF:
    """Exact factored view of the former full profile CDF."""

    def __init__(self, recorded_var: Any, cell_ptr: np.ndarray) -> None:
        self.recorded_var = recorded_var
        self.cell_ptr = np.asarray(cell_ptr, dtype=np.int64)
        if self.cell_ptr.ndim != 1 or len(self.cell_ptr) < 2:
            raise ValueError("R17 profile cell_ptr is malformed")
        if int(self.cell_ptr[0]) != 0 or np.any(np.diff(self.cell_ptr) < 0):
            raise ValueError("R17 profile cell_ptr is not monotone from zero")
        if int(self.cell_ptr[-1]) != int(recorded_var.shape[0]):
            raise ValueError("R17 profile cell_ptr does not span recorded_weight")
        self.cell_cdf = self._build_cell_cdf()

    def _build_cell_cdf(self) -> np.ndarray:
        cell_count = len(self.cell_ptr) - 1
        out = np.empty(cell_count, dtype=np.float64)
        running = 0.0
        cell = 0
        profile_count = int(self.cell_ptr[-1])

        # Preserve the old eager `_ordered_cdf` accumulation order exactly while
        # retaining only one cumulative value per production cell.
        for start in range(0, profile_count, PROFILE_STREAM_CHUNK):
            while cell < cell_count and int(self.cell_ptr[cell + 1]) == start:
                out[cell] = running
                cell += 1
            stop = min(profile_count, start + PROFILE_STREAM_CHUNK)
            values = np.asarray(np.ma.getdata(self.recorded_var[start:stop]), dtype=np.float64)
            for offset, raw in enumerate(values):
                weight = float(raw)
                if not math.isfinite(weight) or weight < 0.0:
                    raise ValueError("R17 profile weights must be finite and nonnegative")
                running += weight
                position = start + offset + 1
                while cell < cell_count and int(self.cell_ptr[cell + 1]) == position:
                    out[cell] = running
                    cell += 1

        while cell < cell_count and int(self.cell_ptr[cell + 1]) == profile_count:
            out[cell] = running
            cell += 1
        if cell != cell_count:
            raise ValueError("R17 profile cell_ptr contains unreachable boundaries")
        if not len(out) or running <= 0.0:
            raise ValueError("R17 contains no positive archaeological profile mass")
        return out

    @property
    def total(self) -> float:
        return float(self.cell_cdf[-1])

    def index(self, draw: float) -> int:
        total = self.total
        target = min(math.nextafter(total, 0.0), max(0.0, float(draw)) * total)
        cell = min(
            int(np.searchsorted(self.cell_cdf, target, side="right")),
            len(self.cell_cdf) - 1,
        )
        start = int(self.cell_ptr[cell])
        stop = int(self.cell_ptr[cell + 1])
        if stop <= start:
            raise ValueError(f"R17 cell {cell} has no profiles")

        running = 0.0 if cell == 0 else float(self.cell_cdf[cell - 1])
        values = np.asarray(np.ma.getdata(self.recorded_var[start:stop]), dtype=np.float64)
        local_cdf = np.empty(len(values), dtype=np.float64)
        for i, raw in enumerate(values):
            running += float(raw)
            local_cdf[i] = running
        local = min(int(np.searchsorted(local_cdf, target, side="right")), len(local_cdf) - 1)
        return start + local

    @property
    def resident_bytes(self) -> int:
        return int(self.cell_ptr.nbytes + self.cell_cdf.nbytes)


class LazyRuntimeV3:
    """Drop-in replacement for ``v3_player_crystallizer.RuntimeV3``.

    World/cell tables remain small enough to materialize.  The million-row profile
    columns remain NetCDF-backed and only selected rows/slices are read.
    """

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.ds = Dataset(self.path, "r")
        try:
            if str(getattr(self.ds, "schema", "")) != runtime_v3.RUNTIME_SCHEMA:
                raise ValueError("not an Atolia v3 frozen-field R17 runtime")
            if str(getattr(self.ds, "world_table_schema", "")) != v3_frozen_world.WORLD_TABLE_SCHEMA:
                raise ValueError("R17 lacks the frozen world tables")
            self.world_build_id = str(self.ds.world_build_id)
            self.world_seed = int(self.ds.world_seed)
            self.intensity_steps = int(self.ds.intensity_steps)
            self.population_cells = int(self.ds.population_cells)
            self.target_objects = int(self.ds.target_player_objects)
            self.runtime_fingerprint = str(self.ds.runtime_fingerprint)
            self.canonical_hydro_id = str(self.ds.canonical_hydro_realization_id)
            self.world = v3_frozen_world.FrozenWorld(self.ds)
            self.cells = v3_frozen_world.load_production_cells(self.ds)

            gp = self.ds.groups["profiles"]
            self.profile_count = int(gp.profile_count)
            self.cell_ptr = np.asarray(gp.variables["cell_ptr"][:], dtype=np.int64)
            if len(self.cell_ptr) != self.population_cells + 1:
                raise ValueError("R17 profile cell CSR length mismatch")

            # These proxies retain the old public attributes so profile readout
            # code can index a selected row without realizing the whole column.
            self.profile_cell = _VariableView(gp.variables["cell_index"], np.int64)
            self.profile_node = _VariableView(gp.variables["node_index"], np.int64)
            self.profile_lineages = _VariableView(gp.variables["lineage_count"], np.int64)
            self.profile_loss = _VariableView(gp.variables["loss_intensity"], np.float64)
            self.profile_represented = _VariableView(gp.variables["represented_weight"], np.float64)
            self.profile_recorded = _VariableView(gp.variables["recorded_weight"], np.float64)
            self.profile_step_min = _VariableView(gp.variables["step_min"], np.int64)
            self.profile_step_max = _VariableView(gp.variables["step_max"], np.int64)
            self.profile_hash = _VariableView(gp.variables["checkpoint_sha256"], np.uint8)
            self.profile_cdf = LazyProfileCDF(gp.variables["recorded_weight"], self.cell_ptr)

            gi = self.ds.groups["integrity"]
            self.cell_identity_hash = np.asarray(gi.variables["cell_identity_sha256"][:], dtype=np.uint8)

            gh = self.ds.groups["canonical_hydro"]
            hydro_nodes = [
                x.decode("utf-8") if isinstance(x, bytes) else str(x)
                for x in gh.variables["node_id"][:]
            ]
            hydro_values = np.asarray(gh.variables["context"][:], dtype=np.float64)
            self.canonical_hydro_context = {
                node: float(value) for node, value in zip(hydro_nodes, hydro_values)
            }
            self.node_ids = list(self.world.nodes)
        except Exception:
            self.ds.close()
            raise

        if len(self.cells) != self.population_cells:
            self.close()
            raise ValueError("R17 frozen production-cell count mismatch")
        if len(self.profile_cell) != self.profile_count or len(self.profile_hash) != self.profile_count:
            self.close()
            raise ValueError("R17 profile field is incomplete")
        if self.target_objects != runtime_v3.TARGET_OBJECTS:
            self.close()
            raise ValueError("R17 target object count is not 300")

    def close(self) -> None:
        if getattr(self, "ds", None) is not None:
            self.ds.close()
            self.ds = None

    def expected_profile_row(self, profile_index: int) -> dict[str, Any]:
        gp = self.ds.groups["profiles"]
        p = int(profile_index)
        node_id = self.node_ids[int(self.profile_node[p])]
        row: dict[str, Any] = {
            "node_token": __import__("v3_phase08_runtime_fragment").anonymous_token(
                self.world_build_id, "node", node_id
            ),
            "lineage_count": int(self.profile_lineages[p]),
            "loss_intensity": float(self.profile_loss[p]),
            "recorded_weight": float(self.profile_recorded[p]),
            "step_min": int(self.profile_step_min[p]),
            "step_max": int(self.profile_step_max[p]),
        }
        for field in runtime_v3.PROFILE_PHASE01_FIELDS:
            row[f"{field}_mean"] = float(gp.variables[f"mean_{field}"][p])
            row[f"{field}_variance"] = float(gp.variables[f"variance_{field}"][p])
        return row


def install(crystallizer: Any) -> str:
    """Install lazy R17 access without altering acquisition PRF semantics."""
    if getattr(crystallizer, "_lazy_profile_store_installed", False):
        return "atolia-v3-r17-lazy-profile-store-v1"

    eager_cdf_index = crystallizer._cdf_index

    def factored_cdf_index(cdf: Any, draw: float) -> int:
        if isinstance(cdf, LazyProfileCDF):
            return cdf.index(draw)
        return eager_cdf_index(cdf, draw)

    crystallizer.RuntimeV3 = LazyRuntimeV3
    crystallizer._cdf_index = factored_cdf_index
    crystallizer._lazy_profile_store_installed = True
    return "atolia-v3-r17-lazy-profile-store-v1"
