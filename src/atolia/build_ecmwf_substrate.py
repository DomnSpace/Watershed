#!/usr/bin/env python3
from __future__ import annotations

"""Canonical entry point for converting the giant JSON developer substrate.

This deliberately defines the nine current deposition coordinates explicitly
before invoking the field writer.  They are the modes emitted by the current
intensity/deposition model; compatibility aliases in older condensation tables
are not extra dimensions of the release substrate.
"""

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


if __name__ == "__main__":
    ecmwf.main()
