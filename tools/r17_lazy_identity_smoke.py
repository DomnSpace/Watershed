from __future__ import annotations

"""Prove lazy cell->profile lookup is exactly the former global-CDF lookup.

This is an optimization gate, not a new sampling policy.  It deliberately builds
one eager reference CDF in the test process and compares it against the lazy R17
reader for many canonical PRF draws.  The shipped generator never builds this
reference array.
"""

import argparse
import math
from pathlib import Path
import sys

import numpy as np
from netCDF4 import Dataset

ROOT = Path(__file__).resolve().parents[1]
ATOLIA = ROOT / "src" / "atolia"
if str(ATOLIA) not in sys.path:
    sys.path.insert(0, str(ATOLIA))

import v3_lazy_profile_store as lazy
import v3_player_crystallizer as crystallizer


KEYS = ("r17-local-player-A", "r17-local-player-B")


def eager_cdf(weights: np.ndarray) -> np.ndarray:
    out = np.empty(len(weights), dtype=np.float64)
    running = 0.0
    for i, raw in enumerate(weights):
        weight = float(raw)
        if not math.isfinite(weight) or weight < 0.0:
            raise RuntimeError("invalid eager reference weight")
        running += weight
        out[i] = running
    return out


def eager_index(cdf: np.ndarray, draw: float) -> int:
    total = float(cdf[-1])
    target = min(math.nextafter(total, 0.0), max(0.0, float(draw)) * total)
    return min(int(np.searchsorted(cdf, target, side="right")), len(cdf) - 1)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--runtime", type=Path, required=True)
    ap.add_argument("--attempts-per-slot", type=int, default=64)
    args = ap.parse_args()

    runtime = args.runtime.resolve()
    with Dataset(runtime, "r") as ds:
        fingerprint = str(ds.runtime_fingerprint)
        weights = np.asarray(ds.groups["profiles"].variables["recorded_weight"][:], dtype=np.float64)
    reference = eager_cdf(weights)

    store = lazy.LazyRuntimeV3(runtime)
    try:
        if float(reference[-1]).hex() != store.profile_cdf.total.hex():
            raise RuntimeError(
                "lazy cell boundary CDF changed total mass: "
                f"{store.profile_cdf.total.hex()} != {float(reference[-1]).hex()}"
            )
        checked = 0
        for key in KEYS:
            for slot in range(300):
                for attempt in range(args.attempts_per_slot):
                    draw = crystallizer._slot_uniform(
                        key, fingerprint, slot, attempt, "profile"
                    )
                    old = eager_index(reference, draw)
                    new = store.profile_cdf.index(draw)
                    if old != new:
                        raise RuntimeError(
                            f"profile identity changed for key={key} slot={slot} attempt={attempt}: "
                            f"eager={old} lazy={new}"
                        )
                    checked += 1
        print({
            "result": "PASS",
            "runtime_fingerprint": fingerprint,
            "draws_compared": checked,
            "profiles": len(reference),
            "lazy_cdf_resident_bytes": store.profile_cdf.resident_bytes,
            "eager_reference_bytes_test_only": int(reference.nbytes + weights.nbytes),
        })
    finally:
        store.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
