#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping

FIELDS = (
    "padanic_adriatic", "rhine_north_sea", "rhone_west_med", "danube_sava_morava",
    "mediterranean_littoral", "adriatic_ionian_aegean", "aegean_anatolia_cyprus",
    "britain_channel_continental", "west_med_island_chain", "alpine_pass_transfer",
    "open_sea_prestige", "local_catchment_reuse",
)


def _require(cond: bool, msg: str) -> None:
    if not cond:
        raise ValueError(msg)


def _sum_close_one(m: Mapping[str, Any], tol: float = 1e-5) -> bool:
    return abs(sum(float(v) for v in m.values()) - 1.0) <= tol


def validate(profile: Mapping[str, Any]) -> dict[str, Any]:
    _require(profile.get("schema") == "atolia.calibration-profile.v1", "unexpected schema")
    _require(bool(profile.get("temporary_editor")), "profile must remain marked temporary_editor until freeze")
    world = profile["world"]
    _require(int(world["carrier_nodes"]) == 1000, "carrier_nodes must remain 1000")

    transport = profile["transport"]
    mixes = transport["object_field_mix"]
    for obj, mix in mixes.items():
        missing = set(FIELDS) - set(mix)
        _require(not missing, f"{obj}: missing fields {sorted(missing)}")
        _require(all(float(v) >= 0 for v in mix.values()), f"{obj}: negative field mixture")
        _require(_sum_close_one(mix, 2e-3), f"{obj}: field mixture must sum to 1")
    for name, value in transport["field_direction_bias"].items():
        _require(-1.0 <= float(value) <= 1.0, f"{name}: direction bias outside [-1,1]")
    for name, pulse in transport["field_pulses"].items():
        _require(900 <= float(pulse["center_bc"]) <= 1900, f"{name}: implausible pulse center")
        _require(float(pulse["sigma_years"]) > 0, f"{name}: sigma must be >0")

    obs = profile["observation"]["modes"]
    for mode, factors in obs.items():
        for key in ("survival", "discovery", "record"):
            _require(0 < float(factors[key]) <= 1, f"{mode}/{key}: probability outside (0,1]")

    condensation = profile["condensation"]
    _require(int(condensation["catalogue"]) == 30000, "catalogue must remain exactly 30000")
    _require(0 <= float(condensation["importance_exponent"]) <= 1, "importance exponent outside [0,1]")

    career = profile["career"]
    _require(int(career["objects"]) == 300, "career must remain exactly 300 objects")
    expected_p = {"early": -1, "middle": 0, "late": 1, "integrated": 2}
    _require({k: int(v) for k, v in career["p_schedule"].items()} == expected_p,
             "POARI p schedule must remain -1,0,1,2")
    for phase, weights in career["phase_weights"].items():
        _require(abs(sum(float(v) for v in weights.values()) - 1.0) <= 2e-3,
                 f"{phase}: POARI dimension weights must sum to 1")

    return {
        "schema": profile["schema"],
        "valid": True,
        "objects": int(career["objects"]),
        "catalogue": int(condensation["catalogue"]),
        "carrier_nodes": int(world["carrier_nodes"]),
        "temporary_editor": bool(profile["temporary_editor"]),
        "note": "Passing validation does not validate the historical hypothesis; it validates calibration-contract integrity.",
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="Validate an exported Atolia calibration profile")
    ap.add_argument("profile", type=Path)
    args = ap.parse_args()
    data = json.loads(args.profile.read_text(encoding="utf-8"))
    print(json.dumps(validate(data), indent=2))


if __name__ == "__main__":
    main()
