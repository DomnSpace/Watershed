#!/usr/bin/env python3
from __future__ import annotations

"""Cross-runtime diagnostics for the Atolia v3 phase-04 workshop layer.

Reads a phase-04 smoke NetCDF and emits structural and precision-banded
fingerprints. If the smoke file is absent (for example after an Arcade project
re-import), it first builds the standard 64-cell phase-04 smoke product and then
diagnoses that exact file.
"""

import argparse
import hashlib
import json
from pathlib import Path
import platform
import sys
from typing import Any, Mapping

import netCDF4
import numpy as np


def _bootstrap_atolia_path() -> Path:
    candidates = [Path.cwd() / "src" / "atolia", Path.cwd()]
    for root in (Path("/home/pyodide/arcade_project"), Path("/home/pyodide/dvx_project")):
        candidates.extend((root / "src" / "atolia", root))
    for entry in list(sys.path):
        if entry:
            root = Path(entry)
            candidates.extend((root / "src" / "atolia", root))
    for candidate in candidates:
        if (candidate / "v3_workshop_netcdf.py").is_file():
            key = str(candidate)
            if key not in sys.path:
                sys.path.insert(0, key)
            return candidate
    raise ModuleNotFoundError("Could not locate Watershed src/atolia")


ATOLIA_DIR = _bootstrap_atolia_path()
PROJECT_ROOT = ATOLIA_DIR.parent.parent if ATOLIA_DIR.name == "atolia" else Path.cwd()

import v3_smoke
import v3_workshop_netcdf as workshop_nc


DEFAULT_HYPOTHESIS = Path("hypotheses/atolia_atesis_1800_1000_v0.json")


def _sha(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _parse_json_field(field: str, value: Any) -> Any:
    if isinstance(value, str) and field.endswith("_json"):
        try:
            return json.loads(value)
        except Exception:
            return value
    return value


def _structure_value(value: Any) -> Any:
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, float):
        return "<float>"
    if isinstance(value, Mapping):
        return {str(k): _structure_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_structure_value(v) for v in value]
    return value


def _precision_value(value: Any, digits: int) -> Any:
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, float):
        if value == 0.0:
            return 0.0
        return float(format(float(value), f".{digits}g"))
    if isinstance(value, Mapping):
        return {str(k): _precision_value(v, digits) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_precision_value(v, digits) for v in value]
    return value


def _row_structure(table_name: str, row: Mapping[str, Any]) -> dict[str, Any]:
    schema = dict(workshop_nc.SCHEMAS[table_name])
    out: dict[str, Any] = {}
    for field, value in row.items():
        kind = schema.get(field)
        parsed = _parse_json_field(field, value)
        if kind == "f8":
            continue
        out[field] = _structure_value(parsed)
    return out


def _row_precision(row: Mapping[str, Any], digits: int) -> dict[str, Any]:
    return {
        field: _precision_value(_parse_json_field(field, value), digits)
        for field, value in row.items()
    }


def _ensure_smoke(path: Path) -> bool:
    if path.is_file():
        return False
    hypothesis_path = PROJECT_ROOT / DEFAULT_HYPOTHESIS
    if not hypothesis_path.is_file():
        raise FileNotFoundError(
            f"phase-04 diagnostic cannot build missing smoke file; hypothesis not found: {hypothesis_path}"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    hypothesis = json.loads(hypothesis_path.read_text(encoding="utf-8"))
    v3_smoke.build_smoke_master_with_workshops(
        hypothesis,
        out_path=path,
        world_seed=1300,
        workshop_count=v3_smoke.DEFAULT_SMOKE_WORKSHOPS,
        intensity_steps=v3_smoke.DEFAULT_SMOKE_STEPS,
        target_geography_nodes=v3_smoke.DEFAULT_SMOKE_GEOGRAPHY_NODES,
        production_cell_limit=v3_smoke.DEFAULT_SMOKE_CELLS,
    )
    return True


def diagnose(path: Path) -> dict[str, Any]:
    built_smoke = _ensure_smoke(path)
    layer = workshop_nc.read_workshop_layer(path)
    tables = {name: layer[name] for name in workshop_nc.TABLE_LAYOUT}

    structural_tables = {
        name: [_row_structure(name, row) for row in rows]
        for name, rows in tables.items()
    }
    structural_per_table = {
        name: _sha(rows) for name, rows in structural_tables.items()
    }

    precision: dict[str, Any] = {}
    for digits in (12, 10, 9, 8):
        projected = {
            name: [_row_precision(row, digits) for row in rows]
            for name, rows in tables.items()
        }
        precision[str(digits)] = {
            "aggregate": _sha(projected),
            "per_table": {name: _sha(rows) for name, rows in projected.items()},
        }

    return {
        "path": str(path),
        "built_smoke": bool(built_smoke),
        "python": sys.version.split()[0],
        "platform": sys.platform,
        "machine": platform.machine(),
        "numpy": np.__version__,
        "netcdf4": netCDF4.__version__,
        "stored_hash_policy": layer["hash_policy"],
        "stored_workshop_sha256": layer["workshop_sha256"],
        "row_counts": {name: len(rows) for name, rows in tables.items()},
        "structural": {
            "aggregate": _sha(structural_tables),
            "per_table": structural_per_table,
        },
        "precision": precision,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--path",
        type=Path,
        default=Path("cache/atolia_v3_phase04_smoke.nc"),
    )
    args = ap.parse_args()
    path = args.path if args.path.is_absolute() else PROJECT_ROOT / args.path
    result = diagnose(path)
    print(json.dumps(result, indent=2, sort_keys=True))
    host_emit = globals().get("emit")
    if callable(host_emit):
        host_emit(result)


if __name__ == "__main__":
    main()
