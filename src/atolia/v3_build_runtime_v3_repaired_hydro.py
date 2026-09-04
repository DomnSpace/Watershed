from __future__ import annotations

"""Stable R17 build entry.

Install the release invariants before importing/running the repaired-field
builder.  The implementation then overrides ``intensity.production_cells``
with the repaired Phase-08 cell hydrator.  Calling ``install()`` later inside
the core builder is consequently a no-op and cannot silently replace the
frozen-cell readout with a freshly regenerated production population.

The core semantic fingerprint walks NetCDF string variables as well as numeric
arrays.  Keep its string decoder installed here until it is folded into the
core builder itself; this is serialization plumbing only and does not alter the
scientific field.
"""

import release_candidate_invariants as release_invariants

# Ordering is part of the R17 correctness contract.  Do this before importing
# the implementation module and before it captures/restores production_cells.
release_invariants.install()

import v3_build_runtime_v3 as core


def _strings(var):
    values = var[:]
    return [
        value.decode("utf-8") if isinstance(value, bytes) else str(value)
        for value in values
    ]


# ``_semantic_runtime_fingerprint`` resolves this name in the core module's
# globals.  The helper was omitted there, so install the exact simple decoder
# before the implementation invokes ``core.build_runtime``.
core._strings = _strings

from v3_build_runtime_v3_repaired_hydro_impl import main


if __name__ == "__main__":
    main()
