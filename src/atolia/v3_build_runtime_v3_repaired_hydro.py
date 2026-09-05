from __future__ import annotations

"""Stable final R17 build entry.

Release invariants are installed before the repaired field implementation so its
Phase-08 production-cell override cannot be replaced later.  The final builder
then appends the retained joint empirical representatives directly into the same
R17 NetCDF; no compact JSON fragment is shipped at runtime.
"""

import release_candidate_invariants as release_invariants

release_invariants.install()

import v3_build_runtime_v3 as core


def _strings(var):
    values = var[:]
    return [
        value.decode("utf-8") if isinstance(value, bytes) else str(value)
        for value in values
    ]


# Serialization plumbing used by the core semantic fingerprint.
core._strings = _strings

from v3_build_runtime_v3_joint import main


if __name__ == "__main__":
    main()
