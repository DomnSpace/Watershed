from __future__ import annotations

import json
import math
import sys
from pathlib import Path

from netCDF4 import Dataset

ROOT = Path(__file__).resolve().parents[1]
ATOLIA = ROOT / "src" / "atolia"
if str(ATOLIA) not in sys.path:
    sys.path.insert(0, str(ATOLIA))

import v3_metallurgy_netcdf
import v3_smoke
import v3_source_metallurgy


HYPOTHESIS_PATH = ROOT / "hypotheses" / "atolia_atesis_1800_1000_v0.json"


def test_real_phase03_smoke_build(tmp_path: Path) -> None:
    hypothesis = json.loads(HYPOTHESIS_PATH.read_text(encoding="utf-8"))
    out = tmp_path / "atolia_v3_phase03_smoke.nc"

    summary = v3_smoke.build_smoke_master_with_metallurgy(
        hypothesis,
        out_path=out,
        world_seed=1300,
        workshop_count=2,
        intensity_steps=2,
        target_geography_nodes=12,
        production_cell_limit=64,
    )

    assert out.exists() and out.stat().st_size > 0
    assert summary["latest_phase"] == v3_metallurgy_netcdf.V3_METALLURGY_PHASE
    assert summary["cells"] == 64
    assert summary["loss_strata"] > 0
    assert summary["metal_biography"]["particles"] == summary["loss_strata"]
    assert summary["source_metallurgy"]["chemistry_batches"] == summary["metal_biography"]["batches"]
    assert summary["source_metallurgy"]["elements"] == (
        summary["source_metallurgy"]["chemistry_batches"]
        * len(v3_source_metallurgy.ELEMENTS)
    )
    assert summary["source_metallurgy"]["pb_isotopes"] == (
        summary["source_metallurgy"]["chemistry_batches"]
        * len(v3_source_metallurgy.PB_ISOTOPES)
    )
    assert summary["roundtrip"]["phase01_spine_hash_equal"] is True
    assert summary["roundtrip"]["phase02_biography_hash_equal"] is True
    assert summary["roundtrip"]["phase03_metallurgy_hash_equal"] is True
    assert summary["roundtrip"]["phase02_phase03_batch_ids_equal"] is True
    assert summary["roundtrip"]["source_calibration_status"] == (
        v3_source_metallurgy.SOURCE_CALIBRATION_STATUS
    )

    actual = v3_metallurgy_netcdf.read_metallurgy(out)
    assert actual["metallurgy_sha256"] == summary["source_metallurgy"]["metallurgy_sha256"]
    assert all(
        math.isclose(row["metal_mass_kg"], row["element_mass_sum_kg"], rel_tol=1e-12, abs_tol=1e-12)
        for row in actual["chemistry_batches"]
    )
    assert all(
        math.isfinite(row["Pb206_204"])
        and math.isfinite(row["Pb207_204"])
        and math.isfinite(row["Pb208_204"])
        for row in actual["chemistry_batches"]
    )

    with Dataset(out, "r") as ds:
        assert str(ds.phase) == "atolia-v3-01-v1-propagation-spine"
        assert str(ds.latest_phase) == v3_metallurgy_netcdf.V3_METALLURGY_PHASE
        assert str(ds.phase03_spine_sha256) == str(ds.spine_sha256)
        assert str(ds.phase03_biography_sha256) == str(ds.phase02_biography_sha256)
        assert {"cells", "loss_strata", "particles", "metal", "objects", "events", "sources", "metallurgy"}.issubset(ds.groups)
