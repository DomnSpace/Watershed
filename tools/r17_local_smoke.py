from __future__ import annotations

"""Fast local gate for the two-NetCDF R17 -> player_17 contract."""

import argparse
from pathlib import Path
import shutil
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
ATOLIA = ROOT / "src" / "atolia"
for path in (ROOT, ATOLIA):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from netCDF4 import Dataset

from generate_player_netcdf import generate_player_netcdf
import v3_frozen_world
import v3_player_integrity
import v3_runtime_v3


def validate_r17(path: Path) -> dict[str, object]:
    with Dataset(path, "r") as ds:
        if str(getattr(ds, "schema", "")) != v3_runtime_v3.RUNTIME_SCHEMA:
            raise RuntimeError(f"unexpected R17 schema: {getattr(ds, 'schema', None)!r}")
        if str(getattr(ds, "world_table_schema", "")) != v3_frozen_world.WORLD_TABLE_SCHEMA:
            raise RuntimeError("R17 lacks the frozen-world table")
        if int(ds.population_cells) != 37100 or int(ds.target_player_objects) != 300:
            raise RuntimeError("R17 cell/player dimensions are wrong")
        for group in ("world_nodes", "world_edges", "world_sources", "world_bundles", "world_workshops", "world_guilds", "production_cells", "profiles", "canonical_hydro", "integrity"):
            if group not in ds.groups:
                raise RuntimeError(f"R17 missing group {group}")
        if str(getattr(ds, "hypothesis_storage", "")) != "not-shipped-compiled-into-frozen-field":
            raise RuntimeError("R17 hypothesis boundary is not frozen-field-only")
        if "hypothesis_bytes" in ds.variables:
            raise RuntimeError("R17 contains plaintext hypothesis bytes")
        profiles = int(ds.groups["profiles"].profile_count)
        if profiles <= 0:
            raise RuntimeError("R17 profile field is empty")
        fingerprint = str(getattr(ds, "runtime_fingerprint", ""))
        if len(fingerprint) != 64:
            raise RuntimeError("R17 runtime fingerprint is malformed")
        return {
            "schema": str(ds.schema),
            "cells": int(ds.population_cells),
            "profiles": profiles,
            "fingerprint": fingerprint,
            "bytes": path.stat().st_size,
        }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--runtime", type=Path, required=True)
    ap.add_argument("--out-dir", type=Path)
    ap.add_argument("--structural-only", action="store_true")
    args = ap.parse_args()
    runtime = args.runtime.resolve()
    report = validate_r17(runtime)
    print("R17 structural gate:", report)
    if args.structural_only:
        return

    owned_temp = args.out_dir is None
    out = Path(tempfile.mkdtemp(prefix="r17-local-smoke-")) if owned_temp else args.out_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)
    try:
        paths = {
            "a1": out / "player_A1.nc",
            "a2": out / "player_A2.nc",
            "b": out / "player_B.nc",
        }
        generate_player_netcdf("r17-local-player-A", runtime=runtime, output_path=paths["a1"])
        generate_player_netcdf("r17-local-player-A", runtime=runtime, output_path=paths["a2"])
        generate_player_netcdf("r17-local-player-B", runtime=runtime, output_path=paths["b"])
        a1 = v3_player_integrity.validate_player_netcdf(paths["a1"])
        a2 = v3_player_integrity.validate_player_netcdf(paths["a2"])
        b = v3_player_integrity.validate_player_netcdf(paths["b"])
        if a1["object_count"] != a2["object_count"] or a1["object_count"] != b["object_count"] or a1["object_count"] != 300:
            raise RuntimeError("A/A/B did not produce exactly 300 objects")
        if a1["player_state_fingerprint"] != a2["player_state_fingerprint"]:
            raise RuntimeError("same key did not reproduce the full hidden player state")
        if a1["object_ids"] != a2["object_ids"]:
            raise RuntimeError("same key did not reproduce the same ordered 300 IDs")
        if a1["object_ids"] == b["object_ids"]:
            raise RuntimeError("different key produced the same ordered 300 IDs")
        overlap = len(set(a1["object_ids"]) & set(b["object_ids"]))
        print("A/A full semantic fingerprint:", a1["player_state_fingerprint"])
        print("B full semantic fingerprint:", b["player_state_fingerprint"])
        print("A/B object overlap:", overlap, "/ 300")
        print("PASS: frozen R17 -> deterministic A/A -> divergent B -> deep player_17 validation")
        if not owned_temp:
            print("kept smoke files in", out)
    finally:
        if owned_temp:
            shutil.rmtree(out, ignore_errors=True)


if __name__ == "__main__":
    main()
