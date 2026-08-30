from __future__ import annotations

from copy import deepcopy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ATOLIA = ROOT / "src" / "atolia"
if str(ATOLIA) not in sys.path:
    sys.path.insert(0, str(ATOLIA))

import v3_workshop_netcdf as workshop_nc


def _tables():
    tables = {name: [] for name in workshop_nc.TABLE_LAYOUT}
    tables["workshops"] = [{
        "workshop_id": "W-0001",
        "quality_memory": 1.23456789012345,
    }]
    tables["guilds"] = [{
        "guild_id": "G-01",
        "technical_prototype_json": "[0.123456789012345,0.5]",
    }]
    tables["operations"] = [{
        "operation_id": "op_a",
        "capability": 0.876543210987654,
    }]
    return tables


def test_phase04_hash_ignores_platform_tail_float_noise():
    a = _tables()
    b = deepcopy(a)
    # Deliberately larger than one ULP: the cross-runtime diagnostic showed that
    # derived guild affinities can differ in the 11th-12th significant digits.
    b["workshops"][0]["quality_memory"] += 1e-11
    b["operations"][0]["capability"] -= 1e-11
    b["guilds"][0]["technical_prototype_json"] = "[0.123456789019,0.5]"

    assert workshop_nc.WORKSHOP_HASH_POLICY == "canonical-float-10sig-v1"
    assert workshop_nc.workshop_hash(a) == workshop_nc.workshop_hash(b)


def test_phase04_hash_still_detects_real_numeric_and_categorical_changes():
    base = _tables()

    numeric = deepcopy(base)
    numeric["operations"][0]["capability"] += 1e-5
    assert workshop_nc.workshop_hash(base) != workshop_nc.workshop_hash(numeric)

    categorical = deepcopy(base)
    categorical["operations"][0]["operation_id"] = "op_b"
    assert workshop_nc.workshop_hash(base) != workshop_nc.workshop_hash(categorical)
