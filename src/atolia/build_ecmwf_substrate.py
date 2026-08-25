#!/usr/bin/env python3
from __future__ import annotations

"""Canonical entry point for the Atolia ECMWF-style substrate products.

The expensive JSON -> master conversion and the compact master -> runtime copy
are deliberately separate phases.  The original converter's inline runtime
copy could apply HDF5 compression filters to NetCDF4 VLEN string coordinates on
some netCDF4 releases.  The canonical entry point therefore always writes the
master first and, unless --no-runtime is requested, delegates the runtime phase
to ``build_runtime_from_master`` whose copier handles VLEN strings and
``_FillValue`` correctly.

This also pins the nine current deposition coordinates explicitly.  They are
the modes emitted by the release intensity/deposition model; compatibility
aliases in older condensation tables are not extra dimensions of the release
substrate.
"""

import argparse
import json
from pathlib import Path

import build_runtime_from_master as runtime_builder
import ecmwf_substrate as ecmwf


CANONICAL_DEPOSITION_MODES = (
    "founder_scrap_hoard",
    "finished_object_hoard",
    "selective_ritual_deposit",
    "personal_wealth_deposit",
    "grave_assemblage",
    "settlement_loss",
    "river_wetland_deposit",
    "workshop_debris",
    "catastrophic_abandonment",
)

# ecmwf_substrate intentionally uses provenance_field as the shared model
# namespace.  Pin the release coordinate here so conversion cannot accidentally
# grow dimensions from legacy compatibility aliases.
ecmwf.base.DEPOSITION_MODES = CANONICAL_DEPOSITION_MODES


def main() -> None:
    ap = argparse.ArgumentParser(
        description=(
            "Convert the giant Atolia JSON substrate into a lossless NetCDF "
            "master and a compact installer/runtime field product."
        )
    )
    ap.add_argument("--source", type=Path, default=ecmwf.DEFAULT_JSON)
    ap.add_argument("--master", type=Path, default=ecmwf.DEFAULT_MASTER)
    ap.add_argument("--runtime", type=Path, default=ecmwf.DEFAULT_RUNTIME)
    ap.add_argument("--vocabulary", type=Path, default=ecmwf.DEFAULT_VOCAB)
    ap.add_argument("--release-invariants", default=ecmwf.DEFAULT_RELEASE_INVARIANTS)
    ap.add_argument("--chunk-rows", type=int, default=ecmwf.DEFAULT_CHUNK)
    ap.add_argument("--no-runtime", action="store_true", help="Create only the lossless master product.")
    args = ap.parse_args()

    chunk_rows = max(4096, int(args.chunk_rows))
    master_report = ecmwf.convert(
        args.source,
        args.master,
        args.runtime,
        args.vocabulary,
        release_invariants=args.release_invariants,
        chunk_rows=chunk_rows,
        build_runtime=False,
    )

    report = dict(master_report)
    report["canonical_deposition_modes"] = list(CANONICAL_DEPOSITION_MODES)
    report["runtime_copy"] = "skipped"
    if not args.no_runtime:
        runtime_report = runtime_builder.build_runtime(
            args.master,
            args.runtime,
            chunk_rows=chunk_rows,
        )
        report["runtime"] = runtime_report["runtime"]
        report["runtime_bytes"] = runtime_report["runtime_bytes"]
        report["runtime_sha256"] = runtime_report["runtime_sha256"]
        report["runtime_copy"] = "build_runtime_from_master"
        report["exact_master_states"] = runtime_report["exact_master_states"]
        report["runtime_profiles"] = runtime_report["runtime_profiles"]
        report["production_cells"] = runtime_report["production_cells"]

    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
