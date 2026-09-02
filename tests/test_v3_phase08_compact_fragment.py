from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ATOLIA = ROOT / "src" / "atolia"
if str(ATOLIA) not in sys.path:
    sys.path.insert(0, str(ATOLIA))

import v3_phase08_compact_fragment as compact
from test_v3_phase08_runtime_fragment import _joint_inputs


def test_compact_profile_conserves_weights_keeps_real_joint_rep_and_hides_ids() -> None:
    inputs = _joint_inputs()
    payload = compact.build_compact_payload(
        world_build_id="world-08",
        ordinal=0,
        record={
            "global_cell_start": 10,
            "global_cell_stop": 11,
            "chunk_sha256": "chunk",
            "phase01_spine_sha256": "p1",
            "phase02_biography_sha256": "p2",
            "phase03_metallurgy_sha256": "p3",
            "phase04_workshop_sha256": "p4",
            "phase05_sha256": "p5",
        },
        recovery={"action": "RETAIN_CANONICAL_SOURCE"},
        representatives_per_profile=2,
        **inputs,
    )

    assert payload["counts"] == {
        "cells": 1,
        "lineages": 1,
        "profiles": 1,
        "representatives": 1,
        "external_tails": 1,
    }
    assert payload["totals"]["loss_intensity"] == 0.8
    assert payload["totals"]["represented_weight"] == 0.8
    assert payload["totals"]["recorded_weight"] == 0.01008
    assert payload["representatives"][0][0] == 0
    assert payload["external_tails"][0][0] == 0
    assert payload["fragment_sha256"] == compact.logical_hash(payload)

    serialized = json.dumps(payload, sort_keys=True)
    for forbidden in (
        "secret-particle",
        "secret-bundle",
        "secret-origin",
        "secret-destination",
        "secret-loss-node",
        "secret-source",
        "secret-pool",
        "secret-field",
    ):
        assert forbidden not in serialized


def test_weighted_representative_selection_is_deterministic() -> None:
    acc_a = compact.ProfileAccumulator(1, "node")
    acc_b = compact.ProfileAccumulator(1, "node")
    rows = [
        ("a", 0.2, {"v": "a"}),
        ("b", 0.7, {"v": "b"}),
        ("c", 0.1, {"v": "c"}),
        ("d", 0.4, {"v": "d"}),
    ]
    for identity, weight, row in rows:
        acc_a.add_rep(identity, weight, row, 2)
    for identity, weight, row in reversed(rows):
        acc_b.add_rep(identity, weight, row, 2)
    assert acc_a.representatives() == acc_b.representatives()
