from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from netCDF4 import Dataset

import ecmwf_acquisition_campaign as runtime


@dataclass
class Node:
    label: str
    kind: str = "hub"
    lon: float = 10.0
    lat: float = 45.0


class World:
    def __init__(self):
        self.nodes = {"n0": Node("N0"), "n1": Node("N1", "river", 11.0, 46.0)}
        self.bundle_incidence = {"B0": 0.4}


def _write_runtime(path):
    with Dataset(path, "w", format="NETCDF4") as ds:
        ds.schema = runtime.RUNTIME_SCHEMA
        ds.product_kind = "installer_runtime"
        ds.world_seed = 20260824
        ds.workshop_count = 3200
        ds.runtime_profile_count = 2
        ds.production_cell_count = 1
        ds.flow_summary_json = '{"circulation_seed":100.0,"return_flux":20.0,"loss_flux":10.0,"retire_flux":30.0,"residual_active":40.0,"recycle_flux":50.0,"transfer_flux":200.0,"conservation_error":50.0}'
        ds.endpoint_conservation_error = 0.0
        ds.endpoint_relative_conservation_error = 0.0
        ds.master_sha256 = "0123456789abcdef" * 4
        ds.release_invariants = "atolia-release-invariants-v1"

        dims = {
            "bundle": 1,
            "family": 1,
            "object_class": 1,
            "node": 2,
            "source": 1,
            "deposition_mode": 2,
            "transport_field": 2,
            "production_cell": 1,
            "cell_source_ptr_dim": 2,
            "cell_source_entry": 1,
            "profile": 2,
            "site_ptr_dim": 3,
            "site_profile_entry": 2,
        }
        for name, n in dims.items():
            ds.createDimension(name, n)

        def string_var(name, dim, values):
            v = ds.createVariable(name, str, (dim,))
            v[:] = np.asarray(values, dtype=object)

        string_var("bundle_name", "bundle", ["B0"])
        string_var("family_name", "family", ["regional_circulation"])
        string_var("object_class_name", "object_class", ["axe"])
        string_var("node_name", "node", ["n0", "n1"])
        string_var("source_name", "source", ["source_a"])
        string_var("deposition_mode_name", "deposition_mode", ["settlement_loss", "finished_object_hoard"])
        string_var("transport_field_name", "transport_field", ["local_catchment_reuse", "alpine_pass_transfer"])

        def one(name, dtype, value):
            v = ds.createVariable(name, dtype, ("production_cell",))
            v[:] = [value]

        one("cell_bundle", "u4", 0)
        one("cell_family", "u4", 0)
        one("cell_object_class", "u4", 0)
        one("cell_date_bc", "i2", 1200)
        one("cell_origin_node", "u4", 0)
        one("cell_destination_node", "u4", 1)
        one("cell_production_intensity", "f8", 100.0)
        one("cell_circulation_seed_intensity", "f8", 100.0)
        one("cell_recycle_mean", "f8", 0.2)
        mix = ds.createVariable("cell_transport_field_mix", "f8", ("production_cell", "transport_field"))
        mix[:] = [[0.7, 0.3]]
        ptr = ds.createVariable("cell_source_ptr", "u8", ("cell_source_ptr_dim",))
        ptr[:] = [0, 1]
        sid = ds.createVariable("cell_source_id", "u4", ("cell_source_entry",))
        sid[:] = [0]
        sw = ds.createVariable("cell_source_weight", "f8", ("cell_source_entry",))
        sw[:] = [1.0]

        pc = ds.createVariable("profile_cell", "u4", ("profile",))
        pc[:] = [0, 0]
        pn = ds.createVariable("profile_node", "u4", ("profile",))
        pn[:] = [0, 1]
        dep = ds.createVariable("profile_deposition_weight", "f8", ("profile", "deposition_mode"))
        dep[:] = [[0.9, 0.1], [0.2, 0.8]]
        loss = ds.createVariable("profile_loss_intensity", "f8", ("profile",))
        loss[:] = [10.0, 20.0]
        obs = ds.createVariable("profile_observation_rate", "f8", ("profile",))
        obs[:] = [0.02, 0.03]
        arch = ds.createVariable("profile_archaeological_intensity", "f8", ("profile",))
        arch[:] = [0.2, 0.6]
        context = ds.createVariable("profile_context_completeness", "f8", ("profile",))
        context[:] = [0.6, 0.85]
        hoard = ds.createVariable("profile_hoard_prior", "f8", ("profile",))
        hoard[:] = [0.1, 0.8]
        smin = ds.createVariable("profile_step_min", "u1", ("profile",))
        smin[:] = [1, 3]
        smax = ds.createVariable("profile_step_max", "u1", ("profile",))
        smax[:] = [2, 5]

        means = {
            "expected_recycle_count": [0.2, 0.5],
            "expected_repair_count": [0.1, 0.3],
            "expected_source_entropy": [0.0, 0.2],
            "expected_field_crossings": [0.05, 0.2],
            "expected_physical_crossings": [0.4, 1.0],
            "route_distance_from_origin_km": [100.0, 700.0],
        }
        for name, values in means.items():
            mv = ds.createVariable(f"profile_mean_{name}", "f8", ("profile",))
            mv[:] = values
            vv = ds.createVariable(f"profile_var_{name}", "f8", ("profile",))
            vv[:] = [0.0, 0.0]

        site_ptr = ds.createVariable("site_ptr", "u8", ("site_ptr_dim",))
        site_ptr[:] = [0, 1, 2]
        site_index = ds.createVariable("site_profile_index", "u4", ("site_profile_entry",))
        site_index[:] = [0, 1]


def test_runtime_store_uses_csr_and_materializes_one_profile(tmp_path):
    path = tmp_path / "runtime.nc"
    _write_runtime(path)
    store = runtime.RuntimeProfileStore(path, World())
    try:
        assert store.profile_count == 2
        assert store.profile_ids_at_site("n1").tolist() == [1]
        sites = store.build_sites(World())
        assert sites["n1"].strata == []
        assert sites["n1"].archaeological_intensity == 0.6

        s = store.materialize(1, np.random.default_rng(1))
        assert s.node_id == "n1"
        assert s.production_cell.bundle_id == "B0"
        assert s.production_cell.object_class == "axe"
        assert s.production_cell.source_mix == {"source_a": 1.0}
        assert s.deposition_mode_weights["finished_object_hoard"] == 0.8
        assert s.route_distance_from_origin_km == 700.0
        assert s.expected_physical_crossings == 1.0
        assert store.tail_mask.tolist() == [True, True]
    finally:
        store.close()


def test_runtime_flow_summary_replaces_legacy_recycle_double_count(tmp_path):
    path = tmp_path / "runtime.nc"
    _write_runtime(path)
    store = runtime.RuntimeProfileStore(path, World())
    try:
        flow = store.flow_summary()
        assert flow["legacy_conservation_error_reported"] == 50.0
        assert flow["conservation_error"] == 0.0
        assert flow["relative_conservation_error"] == 0.0
        assert "internal throughput" in flow["conservation_semantics"]
    finally:
        store.close()
