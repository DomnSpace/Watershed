from __future__ import annotations

import json
import sys
from pathlib import Path

from netCDF4 import Dataset

ROOT = Path(__file__).resolve().parents[1]
ATOLIA = ROOT / "src" / "atolia"
if str(ATOLIA) not in sys.path:
    sys.path.insert(0, str(ATOLIA))

import build_v3_master
import v3_biography_netcdf
import v3_netcdf


HYPOTHESIS_PATH = ROOT / "hypotheses" / "atolia_atesis_1800_1000_v0.json"


def test_real_phase02_smoke_build(tmp_path: Path) -> None:
    """Small real-world end-to-end build for the fast edit/test loop.

    This deliberately uses the actual TemporalFieldArchaeologicalWorld,
    release invariants, v1 intensity propagation, phase-01 NetCDF writer,
    phase-02 biography materializer and phase-02 NetCDF append/read path.
    Only geography/workshops/propagation depth are reduced for speed.
    """
    hypothesis = json.loads(HYPOTHESIS_PATH.read_text(encoding="utf-8"))
    out = tmp_path / "atolia_v3_phase02_smoke.nc"

    summary = build_v3_master.build_master_with_biography(
        hypothesis,
        out_path=out,
        world_seed=1300,
        workshop_count=2,
        intensity_steps=1,
        target_geography_nodes=12,
    )

    assert out.exists()
    assert out.stat().st_size > 0
    assert summary["latest_phase"] == v3_biography_netcdf.V3_BIOGRAPHY_PHASE
    assert summary["metal_biography"]["particles"] > 0
    assert summary["metal_biography"]["events"] >= summary["metal_biography"]["particles"]

    spine = v3_netcdf.read_spine_master(out)
    bio = v3_biography_netcdf.read_biography(out)

    assert len(spine["cells"]) > 0
    assert len(spine["loss_strata"]) == len(bio["particles"])
    assert bio["phase01_spine_sha256"] == spine["spine_sha256"]
    assert bio["biography_sha256"] == summary["metal_biography"]["biography_sha256"]

    particle_ids = {row["particle_id"] for row in bio["particles"]}
    assert len(particle_ids) == len(bio["particles"])
    assert all(row["represented_weight"] > 0.0 for row in bio["particles"])
    assert all(row["current_object_distance_km"] <= row["cumulative_metal_distance_km"] + 1e-12 for row in bio["particles"])

    with Dataset(out, "r") as ds:
        assert str(ds.phase) == v3_netcdf.V3_PHASE
        assert str(ds.latest_phase) == v3_biography_netcdf.V3_BIOGRAPHY_PHASE
        assert str(ds.phase02_spine_sha256) == str(ds.spine_sha256)
        assert {"cells", "loss_strata", "particles", "metal", "objects", "events"}.issubset(ds.groups)
