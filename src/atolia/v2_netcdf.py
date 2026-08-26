from __future__ import annotations

"""Direct NetCDF4 storage for the Atolia v2 metal-lineage world.

The writer is deliberately cell-streaming: exact terminal/loss states are appended
as one production cell is simulated, while profile accumulators are held only for
that current cell.  The giant JSON intermediate from v1 is therefore absent.

The master keeps exact terminal-state rows.  The runtime copier omits /states but
retains cells, profiles, workshops, tools, hydro, events and vocabularies.
"""

from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Sequence, Tuple

import numpy as np
from netCDF4 import Dataset, Group

import v2_config as cfg


class StringLookup:
    """Dictionary-code strings without applying HDF5 filters to VLEN strings."""

    def __init__(self, group: Group, name: str) -> None:
        self.name = str(name)
        dim = f"{name}_id"
        group.createDimension(dim, None)
        self.var = group.createVariable(f"{name}_name", str, (dim,))
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
class WeightedProfile:
    names: Tuple[str, ...]
    covariance_names: Tuple[str, ...]
    weight: float = 0.0
    count: int = 0
    mean: np.ndarray = field(init=False)
    m2: np.ndarray = field(init=False)
    cov_mean: np.ndarray = field(init=False)
    cov_m2: np.ndarray = field(init=False)

    def __post_init__(self) -> None:
        self.mean = np.zeros(len(self.names), dtype=np.float64)
        self.m2 = np.zeros(len(self.names), dtype=np.float64)
        self.cov_mean = np.zeros(len(self.covariance_names), dtype=np.float64)
        self.cov_m2 = np.zeros((len(self.covariance_names), len(self.covariance_names)), dtype=np.float64)
        self._name_index = {name: i for i, name in enumerate(self.names)}

    def add(self, values: Mapping[str, float], weight: float) -> None:
        w = max(0.0, float(weight))
        if w <= 0.0:
            return
        x = np.asarray([float(values.get(name, 0.0)) for name in self.names], dtype=np.float64)
        cx = np.asarray([float(values.get(name, 0.0)) for name in self.covariance_names], dtype=np.float64)
        new_weight = self.weight + w
        if self.weight <= 0.0:
            self.mean[:] = x
            self.cov_mean[:] = cx
        else:
            delta = x - self.mean
            self.mean += (w / new_weight) * delta
            self.m2 += w * delta * (x - self.mean)

            cdelta = cx - self.cov_mean
            old_cmean = self.cov_mean.copy()
            self.cov_mean += (w / new_weight) * cdelta
            self.cov_m2 += w * np.outer(cx - old_cmean, cx - self.cov_mean)
        self.weight = new_weight
        self.count += 1

    def variance(self) -> np.ndarray:
        if self.weight <= 0:
            return np.zeros_like(self.mean)
        return np.maximum(0.0, self.m2 / self.weight)

    def covariance(self) -> np.ndarray:
        if self.weight <= 0:
            return np.zeros_like(self.cov_m2)
        out = self.cov_m2 / self.weight
        return 0.5 * (out + out.T)

    def packed_covariance(self) -> np.ndarray:
        cov = self.covariance()
        return np.asarray([cov[i, j] for i in range(cov.shape[0]) for j in range(i + 1)], dtype=np.float64)


class DirectV2Writer:
    def __init__(self, path: Path, *, world_seed: int, model_metadata: Mapping[str, Any],
                 chunk_rows: int = cfg.DEFAULT_CONFIG.netcdf_chunk_rows,
                 compression_level: int = cfg.DEFAULT_CONFIG.compression_level) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self.chunk_rows = max(1024, int(chunk_rows))
        self.compression_level = int(np.clip(compression_level, 0, 9))
        self.ds = Dataset(path, "w", format="NETCDF4")
        ds = self.ds
        ds.schema = cfg.V2_MASTER_SCHEMA
        ds.product_kind = "developer_master"
        ds.model_version = cfg.V2_MODEL_VERSION
        ds.world_seed = int(world_seed)
        ds.poari_contract = "POARI routes archaeological inquiry, not artefact selection."
        ds.model_metadata_json = json.dumps(dict(model_metadata), sort_keys=True, separators=(",", ":"))

        self.vocab = ds.createGroup("vocab")
        self.cells = ds.createGroup("cells")
        self.states = ds.createGroup("states")
        self.profiles = ds.createGroup("profiles")
        self.workshops = ds.createGroup("workshops")
        self.tools = ds.createGroup("tools")
        self.hydro = ds.createGroup("hydro")
        self.events = ds.createGroup("events")

        self.node = StringLookup(self.vocab, "node")
        self.object_class = StringLookup(self.vocab, "object_class")
        self.carrier = StringLookup(self.vocab, "carrier")
        self.terminal = StringLookup(self.vocab, "terminal_kind")
        self.bundle = StringLookup(self.vocab, "bundle")
        self.family = StringLookup(self.vocab, "bundle_family")
        self.source = StringLookup(self.vocab, "source")
        self.guild = StringLookup(self.vocab, "guild")
        self.tool_family = StringLookup(self.vocab, "tool_family")
        self.tool_subtype = StringLookup(self.vocab, "tool_subtype")
        self.hydro_mechanism = StringLookup(self.vocab, "hydro_mechanism")
        self.hydro_provenance = StringLookup(self.vocab, "hydro_provenance")
        self.event_type = StringLookup(self.vocab, "event_type")

        self._init_fixed_vocab()
        self._init_cells()
        self._init_states()
        self._init_profiles()
        self._init_workshops()
        self._init_tools()
        self._init_hydro()
        self._init_events()

        self.cell_count = 0
        self.source_entry_count = 0
        self.state_count = 0
        self.profile_count = 0
        self.workshop_count = 0
        self.tool_count = 0
        self.hydro_count = 0
        self.event_count = 0
        self.current_cell_id: int | None = None
        self._profile_id_by_key: Dict[tuple[int, int, int, int], int] = {}
        self._profile_acc: Dict[int, WeightedProfile] = {}
        self._state_buffer: Dict[str, list[Any]] = {name: [] for name in (
            "profile", "cell", "node", "class", "carrier", "terminal", "date_bc",
            "weight", "metal_mass", "lineages", "episodes", "aggregation"
        )}
        self._state_moment_buffer: list[np.ndarray] = []
        self._state_element_buffer: list[np.ndarray] = []
        self._state_pb_buffer: list[np.ndarray] = []

    def _cv(self, group: Group, name: str, dtype: str, dims: tuple[str, ...],
            chunksizes: tuple[int, ...] | None = None):
        kwargs: Dict[str, Any] = {"shuffle": True}
        if self.compression_level > 0:
            kwargs.update(zlib=True, complevel=self.compression_level)
        if chunksizes is not None:
            kwargs["chunksizes"] = chunksizes
        return group.createVariable(name, dtype, dims, **kwargs)

    def _init_fixed_vocab(self) -> None:
        g = self.vocab
        g.createDimension("element", len(cfg.ELEMENTS))
        g.createDimension("pb_isotope", len(cfg.PB_ISOTOPES))
        g.createDimension("state_moment", len(cfg.STATE_MOMENTS))
        g.createDimension("cov_moment", len(cfg.COVARIANCE_MOMENTS))
        for name, values, dim in (
            ("element_name", cfg.ELEMENTS, "element"),
            ("pb_isotope_name", cfg.PB_ISOTOPES, "pb_isotope"),
            ("state_moment_name", cfg.STATE_MOMENTS, "state_moment"),
            ("cov_moment_name", cfg.COVARIANCE_MOMENTS, "cov_moment"),
        ):
            var = g.createVariable(name, str, (dim,))
            var[:] = np.asarray(values, dtype=object)
        for value in cfg.CARRIER_ROLES:
            self.carrier.get(value)
        for value in cfg.TERMINAL_KINDS:
            self.terminal.get(value)

    def _init_cells(self) -> None:
        g = self.cells
        for dim in ("cell", "source_ptr", "source_entry"):
            g.createDimension(dim, None)
        c = (min(8192, self.chunk_rows),)
        self.cell_bundle = self._cv(g, "bundle_id", "u4", ("cell",), c)
        self.cell_family = self._cv(g, "bundle_family_id", "u4", ("cell",), c)
        self.cell_date = self._cv(g, "date_bc", "i2", ("cell",), c)
        self.cell_origin = self._cv(g, "origin_node_id", "u4", ("cell",), c)
        self.cell_destination = self._cv(g, "destination_node_id", "u4", ("cell",), c)
        self.cell_class = self._cv(g, "initial_object_class_id", "u4", ("cell",), c)
        self.cell_primary_cu = self._cv(g, "primary_cu_kg", "f8", ("cell",), c)
        self.cell_objectized_cu = self._cv(g, "objectized_primary_cu_kg", "f8", ("cell",), c)
        self.cell_lineages = self._cv(g, "represented_initial_lineages", "f8", ("cell",), c)
        self.cell_atesis_fraction = self._cv(g, "atesis_source_fraction", "f8", ("cell",), c)
        self.cell_source_ptr = self._cv(g, "source_ptr", "u8", ("source_ptr",), c)
        self.cell_source_id = self._cv(g, "source_id", "u4", ("source_entry",), c)
        self.cell_source_weight = self._cv(g, "source_weight", "f8", ("source_entry",), c)
        self.cell_source_ptr[0] = 0

    def _init_states(self) -> None:
        g = self.states
        g.createDimension("state", None)
        g.createDimension("state_moment", len(cfg.STATE_MOMENTS))
        g.createDimension("element", len(cfg.ELEMENTS))
        g.createDimension("pb_isotope", len(cfg.PB_ISOTOPES))
        r = (self.chunk_rows,)
        self.state_profile = self._cv(g, "profile_id", "u8", ("state",), r)
        self.state_cell = self._cv(g, "cell_id", "u4", ("state",), r)
        self.state_node = self._cv(g, "node_id", "u4", ("state",), r)
        self.state_class = self._cv(g, "object_class_id", "u4", ("state",), r)
        self.state_carrier = self._cv(g, "carrier_id", "u4", ("state",), r)
        self.state_terminal = self._cv(g, "terminal_kind_id", "u4", ("state",), r)
        self.state_date = self._cv(g, "date_bc", "i2", ("state",), r)
        self.state_weight = self._cv(g, "represented_state_weight", "f8", ("state",), r)
        self.state_metal_mass = self._cv(g, "metal_mass_kg", "f8", ("state",), r)
        self.state_lineages = self._cv(g, "represented_lineages", "f8", ("state",), r)
        self.state_episodes = self._cv(g, "represented_object_episodes", "f8", ("state",), r)
        self.state_aggregation = self._cv(g, "aggregation_id", "i8", ("state",), r)
        self.state_moments = self._cv(g, "moment", "f8", ("state", "state_moment"), (min(8192, self.chunk_rows), len(cfg.STATE_MOMENTS)))
        self.state_elements = self._cv(g, "element_mass_kg", "f8", ("state", "element"), (min(8192, self.chunk_rows), len(cfg.ELEMENTS)))
        self.state_pb = self._cv(g, "pb_isotope_inventory", "f8", ("state", "pb_isotope"), (min(8192, self.chunk_rows), len(cfg.PB_ISOTOPES)))

    def _init_profiles(self) -> None:
        g = self.profiles
        g.createDimension("profile", None)
        g.createDimension("state_moment", len(cfg.STATE_MOMENTS))
        n_cov = len(cfg.COVARIANCE_MOMENTS)
        g.createDimension("cov_packed", n_cov * (n_cov + 1) // 2)
        p = (min(32768, self.chunk_rows),)
        self.profile_cell = self._cv(g, "cell_id", "u4", ("profile",), p)
        self.profile_node = self._cv(g, "node_id", "u4", ("profile",), p)
        self.profile_class = self._cv(g, "object_class_id", "u4", ("profile",), p)
        self.profile_carrier = self._cv(g, "carrier_id", "u4", ("profile",), p)
        self.profile_weight = self._cv(g, "represented_weight", "f8", ("profile",), p)
        self.profile_state_count = self._cv(g, "exact_state_count", "u4", ("profile",), p)
        self.profile_mean = self._cv(g, "mean", "f8", ("profile", "state_moment"), (min(8192, self.chunk_rows), len(cfg.STATE_MOMENTS)))
        self.profile_var = self._cv(g, "variance", "f8", ("profile", "state_moment"), (min(8192, self.chunk_rows), len(cfg.STATE_MOMENTS)))
        self.profile_cov = self._cv(g, "covariance_packed", "f8", ("profile", "cov_packed"), (min(8192, self.chunk_rows), n_cov * (n_cov + 1) // 2))

    def _init_workshops(self) -> None:
        g = self.workshops
        g.createDimension("workshop", None)
        g.createDimension("guild_axis", 12)
        q = (min(8192, self.chunk_rows),)
        self.workshop_id = g.createVariable("workshop_name", str, ("workshop",))
        self.workshop_node = self._cv(g, "node_id", "u4", ("workshop",), q)
        self.workshop_start = self._cv(g, "start_bc", "i2", ("workshop",), q)
        self.workshop_end = self._cv(g, "end_bc", "i2", ("workshop",), q)
        self.workshop_workers = self._cv(g, "workers", "u2", ("workshop",), q)
        self.workshop_quality = self._cv(g, "quality_memory", "f4", ("workshop",), q)
        self.workshop_volume = self._cv(g, "recent_volume", "f4", ("workshop",), q)
        self.workshop_guild = self._cv(g, "guild_affinity", "f4", ("workshop", "guild_axis"), (min(2048, self.chunk_rows), 12))

    def _init_tools(self) -> None:
        g = self.tools
        g.createDimension("tool", None)
        q = (min(16384, self.chunk_rows),)
        self.tool_name = g.createVariable("tool_name", str, ("tool",))
        self.tool_nickname = g.createVariable("nickname", str, ("tool",))
        self.tool_workshop = self._cv(g, "workshop_index", "u4", ("tool",), q)
        self.tool_family_id = self._cv(g, "family_id", "u4", ("tool",), q)
        self.tool_subtype_id = self._cv(g, "subtype_id", "u4", ("tool",), q)
        self.tool_depth = self._cv(g, "lineage_depth", "u2", ("tool",), q)
        self.tool_mass = self._cv(g, "mass_kg", "f4", ("tool",), q)
        self.tool_face_area = self._cv(g, "face_area_mm2", "f4", ("tool",), q)
        self.tool_face_radius = self._cv(g, "face_radius_mm", "f4", ("tool",), q)
        self.tool_handle = self._cv(g, "handle_length_mm", "f4", ("tool",), q)
        self.tool_precision = self._cv(g, "precision_bias", "f4", ("tool",), q)
        self.tool_force = self._cv(g, "force_bias", "f4", ("tool",), q)
        self.tool_portability = self._cv(g, "portability", "f4", ("tool",), q)
        self.tool_wear = self._cv(g, "wear", "f4", ("tool",), q)
        self.tool_repairs = self._cv(g, "repair_count", "u2", ("tool",), q)

    def _init_hydro(self) -> None:
        g = self.hydro
        g.createDimension("candidate", None)
        q = (min(32768, self.chunk_rows),)
        self.hydro_a = self._cv(g, "node_a", "u4", ("candidate",), q)
        self.hydro_b = self._cv(g, "node_b", "u4", ("candidate",), q)
        self.hydro_prov = self._cv(g, "provenance_id", "u4", ("candidate",), q)
        self.hydro_mech = self._cv(g, "mechanism_id", "u4", ("candidate",), q)
        self.hydro_probability = self._cv(g, "base_probability", "f4", ("candidate",), q)
        self.hydro_realized = self._cv(g, "realized", "u1", ("candidate",), q)
        self.hydro_navigability = self._cv(g, "navigability", "f4", ("candidate",), q)
        self.hydro_observed = self._cv(g, "observed", "u1", ("candidate",), q)

    def _init_events(self) -> None:
        g = self.events
        g.createDimension("event", None)
        q = (min(32768, self.chunk_rows),)
        self.event_type_id = self._cv(g, "event_type_id", "u4", ("event",), q)
        self.event_cell = self._cv(g, "cell_id", "i8", ("event",), q)
        self.event_node = self._cv(g, "node_id", "u4", ("event",), q)
        self.event_date = self._cv(g, "date_bc", "i2", ("event",), q)
        self.event_weight = self._cv(g, "represented_weight", "f8", ("event",), q)
        self.event_value = self._cv(g, "value", "f8", ("event",), q)

    def append_cell(self, cell: Mapping[str, Any]) -> int:
        if self.current_cell_id is not None:
            raise RuntimeError("finish_current_cell() before appending the next cell")
        cid = self.cell_count
        self.cell_count += 1
        self.cell_bundle[cid] = self.bundle.get(cell["bundle_id"])
        self.cell_family[cid] = self.family.get(cell["bundle_family"])
        self.cell_date[cid] = int(cell["date_bc"])
        self.cell_origin[cid] = self.node.get(cell["origin"])
        self.cell_destination[cid] = self.node.get(cell["destination"])
        self.cell_class[cid] = self.object_class.get(cell["object_class"])
        self.cell_primary_cu[cid] = float(cell["primary_cu_kg"])
        self.cell_objectized_cu[cid] = float(cell["objectized_primary_cu_kg"])
        self.cell_lineages[cid] = float(cell["represented_initial_lineages"])
        self.cell_atesis_fraction[cid] = float(cell.get("atesis_source_fraction", 0.0))
        for source_name, weight in sorted(dict(cell.get("source_mix", {})).items()):
            idx = self.source_entry_count
            self.cell_source_id[idx] = self.source.get(source_name)
            self.cell_source_weight[idx] = float(weight)
            self.source_entry_count += 1
        self.cell_source_ptr[cid + 1] = self.source_entry_count
        self.current_cell_id = cid
        self._profile_id_by_key = {}
        self._profile_acc = {}
        return cid

    def _profile(self, cid: int, node_id: str, object_class: str, carrier: str) -> int:
        nid = self.node.get(node_id)
        cls = self.object_class.get(object_class)
        car = self.carrier.get(carrier)
        key = (cid, nid, cls, car)
        found = self._profile_id_by_key.get(key)
        if found is not None:
            return found
        pid = self.profile_count
        self.profile_count += 1
        self._profile_id_by_key[key] = pid
        self.profile_cell[pid] = cid
        self.profile_node[pid] = nid
        self.profile_class[pid] = cls
        self.profile_carrier[pid] = car
        self._profile_acc[pid] = WeightedProfile(tuple(cfg.STATE_MOMENTS), tuple(cfg.COVARIANCE_MOMENTS))
        return pid

    def append_state(self, *, cell_id: int, node_id: str, object_class: str, carrier: str,
                     terminal_kind: str, date_bc: int, represented_weight: float,
                     metal_mass_kg: float, represented_lineages: float,
                     represented_object_episodes: float, moments: Mapping[str, float],
                     element_mass_kg: Mapping[str, float], pb_isotope_inventory: Mapping[str, float],
                     aggregation_id: int = -1) -> int:
        if self.current_cell_id != int(cell_id):
            raise RuntimeError("states must be appended while their production cell is current")
        pid = self._profile(cell_id, node_id, object_class, carrier)
        weight = max(0.0, float(represented_weight))
        self._profile_acc[pid].add(moments, weight)
        b = self._state_buffer
        b["profile"].append(pid)
        b["cell"].append(int(cell_id))
        b["node"].append(self.node.get(node_id))
        b["class"].append(self.object_class.get(object_class))
        b["carrier"].append(self.carrier.get(carrier))
        b["terminal"].append(self.terminal.get(terminal_kind))
        b["date_bc"].append(int(date_bc))
        b["weight"].append(weight)
        b["metal_mass"].append(float(metal_mass_kg))
        b["lineages"].append(float(represented_lineages))
        b["episodes"].append(float(represented_object_episodes))
        b["aggregation"].append(int(aggregation_id))
        self._state_moment_buffer.append(np.asarray([float(moments.get(n, 0.0)) for n in cfg.STATE_MOMENTS], dtype=np.float64))
        self._state_element_buffer.append(np.asarray([float(element_mass_kg.get(n, 0.0)) for n in cfg.ELEMENTS], dtype=np.float64))
        self._state_pb_buffer.append(np.asarray([float(pb_isotope_inventory.get(n, 0.0)) for n in cfg.PB_ISOTOPES], dtype=np.float64))
        if len(b["profile"]) >= self.chunk_rows:
            self._flush_states()
        return pid

    def _flush_states(self) -> None:
        n = len(self._state_buffer["profile"])
        if not n:
            return
        a, z = self.state_count, self.state_count + n
        b = self._state_buffer
        for var, name, dtype in (
            (self.state_profile, "profile", np.uint64), (self.state_cell, "cell", np.uint32),
            (self.state_node, "node", np.uint32), (self.state_class, "class", np.uint32),
            (self.state_carrier, "carrier", np.uint32), (self.state_terminal, "terminal", np.uint32),
            (self.state_date, "date_bc", np.int16), (self.state_weight, "weight", np.float64),
            (self.state_metal_mass, "metal_mass", np.float64), (self.state_lineages, "lineages", np.float64),
            (self.state_episodes, "episodes", np.float64), (self.state_aggregation, "aggregation", np.int64),
        ):
            var[a:z] = np.asarray(b[name], dtype=dtype)
        self.state_moments[a:z, :] = np.vstack(self._state_moment_buffer)
        self.state_elements[a:z, :] = np.vstack(self._state_element_buffer)
        self.state_pb[a:z, :] = np.vstack(self._state_pb_buffer)
        self.state_count = z
        for values in b.values():
            values.clear()
        self._state_moment_buffer.clear()
        self._state_element_buffer.clear()
        self._state_pb_buffer.clear()

    def finish_current_cell(self) -> None:
        if self.current_cell_id is None:
            return
        self._flush_states()
        for pid, acc in self._profile_acc.items():
            self.profile_weight[pid] = float(acc.weight)
            self.profile_state_count[pid] = int(acc.count)
            self.profile_mean[pid, :] = acc.mean
            self.profile_var[pid, :] = acc.variance()
            self.profile_cov[pid, :] = acc.packed_covariance()
        self.current_cell_id = None
        self._profile_id_by_key.clear()
        self._profile_acc.clear()

    def append_workshops(self, ecologies: Sequence[Any]) -> None:
        guild_ids = tuple(sorted(f"G-{i:02d}" for i in range(1, 13)))
        for gid in guild_ids:
            self.guild.get(gid)
        for ecology in ecologies:
            wi = self.workshop_count
            self.workshop_count += 1
            self.workshop_id[wi] = str(ecology.workshop_id)
            self.workshop_node[wi] = self.node.get(ecology.node_id)
            self.workshop_start[wi] = int(ecology.start_bc)
            self.workshop_end[wi] = int(ecology.end_bc)
            self.workshop_workers[wi] = int(ecology.workers)
            self.workshop_quality[wi] = float(ecology.quality_memory)
            self.workshop_volume[wi] = float(ecology.recent_volume)
            self.workshop_guild[wi, :] = np.asarray([float(ecology.guild_affinities.get(gid, 0.0)) for gid in guild_ids], dtype=np.float32)
            for tool in ecology.tools:
                ti = self.tool_count
                self.tool_count += 1
                self.tool_name[ti] = str(tool.tool_id)
                self.tool_nickname[ti] = str(tool.nickname)
                self.tool_workshop[ti] = wi
                self.tool_family_id[ti] = self.tool_family.get(tool.family)
                self.tool_subtype_id[ti] = self.tool_subtype.get(tool.subtype)
                self.tool_depth[ti] = int(tool.lineage_depth)
                self.tool_mass[ti] = float(tool.mass_kg)
                self.tool_face_area[ti] = float(tool.face_area_mm2)
                self.tool_face_radius[ti] = float(tool.face_radius_mm)
                self.tool_handle[ti] = float(tool.handle_length_mm)
                self.tool_precision[ti] = float(tool.precision_bias)
                self.tool_force[ti] = float(tool.force_bias)
                self.tool_portability[ti] = float(tool.portability)
                self.tool_wear[ti] = float(tool.wear)
                self.tool_repairs[ti] = int(tool.repair_count)

    def append_hydro(self, rows: Iterable[Mapping[str, Any]]) -> None:
        for row in rows:
            i = self.hydro_count
            self.hydro_count += 1
            self.hydro_a[i] = self.node.get(row["a"])
            self.hydro_b[i] = self.node.get(row["b"])
            self.hydro_prov[i] = self.hydro_provenance.get(row.get("provenance", "inferred"))
            self.hydro_mech[i] = self.hydro_mechanism.get(row.get("mechanism", "candidate_channel"))
            self.hydro_probability[i] = float(row.get("probability", 0.0))
            self.hydro_realized[i] = int(bool(row.get("realized", False)))
            self.hydro_navigability[i] = float(row.get("navigability", 0.0))
            self.hydro_observed[i] = int(bool(row.get("observed", False)))

    def append_event(self, event_type: str, *, cell_id: int = -1, node_id: str,
                     date_bc: int, represented_weight: float = 0.0, value: float = 0.0) -> None:
        i = self.event_count
        self.event_count += 1
        self.event_type_id[i] = self.event_type.get(event_type)
        self.event_cell[i] = int(cell_id)
        self.event_node[i] = self.node.get(node_id)
        self.event_date[i] = int(date_bc)
        self.event_weight[i] = float(represented_weight)
        self.event_value[i] = float(value)

    def finish(self, accounting: Mapping[str, Any]) -> None:
        self.finish_current_cell()
        self.ds.state_count = int(self.state_count)
        self.ds.profile_count = int(self.profile_count)
        self.ds.production_cell_count = int(self.cell_count)
        self.ds.workshop_count = int(self.workshop_count)
        self.ds.tool_count = int(self.tool_count)
        self.ds.hydro_candidate_count = int(self.hydro_count)
        self.ds.event_count = int(self.event_count)
        self.ds.accounting_json = json.dumps(dict(accounting), sort_keys=True, separators=(",", ":"))
        self.ds.sync()

    def close(self) -> None:
        self.ds.close()


def _copy_attrs(src: Any, dst: Any) -> None:
    for name in src.ncattrs():
        if name == "_FillValue":
            continue
        setattr(dst, name, getattr(src, name))


def _is_string_var(var: Any) -> bool:
    try:
        return var.datatype is str or var.dtype is str or var.dtype == str
    except Exception:
        return False


def _copy_group(src: Group, dst: Group, *, omit_groups: frozenset[str], compression_level: int) -> None:
    for dim_name, dim in src.dimensions.items():
        if dim_name not in dst.dimensions:
            dst.createDimension(dim_name, None if dim.isunlimited() else len(dim))
    for var_name, var in src.variables.items():
        fill = getattr(var, "_FillValue", None) if "_FillValue" in var.ncattrs() else None
        kwargs: Dict[str, Any] = {}
        if fill is not None:
            kwargs["fill_value"] = fill
        if not _is_string_var(var) and compression_level > 0:
            kwargs.update(zlib=True, complevel=int(compression_level), shuffle=True)
        out = dst.createVariable(var_name, var.datatype, var.dimensions, **kwargs)
        _copy_attrs(var, out)
        out[:] = var[:]
    for child_name, child in src.groups.items():
        if child_name in omit_groups:
            continue
        child_out = dst.createGroup(child_name)
        _copy_attrs(child, child_out)
        _copy_group(child, child_out, omit_groups=omit_groups, compression_level=compression_level)


def build_runtime(master_path: Path, runtime_path: Path, *, compression_level: int = 4) -> Dict[str, Any]:
    master_path, runtime_path = Path(master_path), Path(runtime_path)
    runtime_path.parent.mkdir(parents=True, exist_ok=True)
    with Dataset(master_path, "r") as src, Dataset(runtime_path, "w", format="NETCDF4") as dst:
        _copy_attrs(src, dst)
        dst.schema = cfg.V2_RUNTIME_SCHEMA
        dst.product_kind = "shipping_runtime"
        dst.exact_state_rows_omitted = 1
        _copy_group(src, dst, omit_groups=frozenset({"states"}), compression_level=compression_level)
        dst.sync()
    return {"master": str(master_path), "runtime": str(runtime_path), "runtime_schema": cfg.V2_RUNTIME_SCHEMA}
