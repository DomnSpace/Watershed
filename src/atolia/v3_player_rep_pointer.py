from __future__ import annotations

"""Persist and validate the direct R17 representative coordinate in player_17."""

from pathlib import Path
from typing import Any

import numpy as np
from netCDF4 import Dataset


def append_player_representative_pointers(state: Any, player_path: Path) -> None:
    pointers = np.asarray(
        [int(row.candidate.cell_loss_index) for row in state.selected],
        dtype=np.int64,
    )
    if pointers.size != 300 or np.any(pointers < 0):
        raise RuntimeError("player representative pointer set is incomplete")
    with Dataset(Path(state.runtime_path), "r") as runtime:
        group = runtime.groups.get("representatives")
        if group is None:
            raise RuntimeError("R17 lacks packed joint representatives")
        total = int(group.representative_count)
        profile_ptr = np.asarray(group.variables["profile_ptr"][:], dtype=np.int64)
        profile_of_rep = group.variables["profile_index"]
        if np.any(pointers >= total):
            raise RuntimeError("player representative pointer lies outside R17")
        for selected, rep in zip(state.selected, pointers):
            p = int(selected.runtime_profile_index)
            if p < 0 or p + 1 >= len(profile_ptr):
                raise RuntimeError("player profile pointer lies outside R17 representative CSR")
            if not (int(profile_ptr[p]) <= int(rep) < int(profile_ptr[p + 1])):
                raise RuntimeError("player representative pointer does not belong to its selected R17 profile")
            if int(profile_of_rep[int(rep)]) != p:
                raise RuntimeError("R17 representative/profile foreign key is inconsistent")

    with Dataset(Path(player_path), "r+") as ds:
        objects = ds.groups["objects"]
        if "runtime_representative_index" in objects.variables:
            raise RuntimeError("player_17 already contains representative pointers")
        var = objects.createVariable("runtime_representative_index", "i8", ("object",), zlib=True, complevel=6, shuffle=True)
        var[:] = pointers
        ds.r17_pointer_policy = "global-cell + runtime-profile + joint-representative"
