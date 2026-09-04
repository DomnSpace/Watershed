from __future__ import annotations

"""Stable R17 build entry.

Install the release invariants before importing/running the repaired-field
builder.  The implementation then overrides ``intensity.production_cells``
with the repaired Phase-08 cell hydrator.  Calling ``install()`` later inside
the core builder is consequently a no-op and cannot silently replace the
frozen-cell readout with a freshly regenerated production population.
"""

import release_candidate_invariants as release_invariants

# Ordering is part of the R17 correctness contract.  Do this before importing
# the implementation module and before it captures/restores production_cells.
release_invariants.install()

from v3_build_runtime_v3_repaired_hydro_impl import main


if __name__ == "__main__":
    main()
