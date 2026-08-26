from __future__ import annotations

"""Canonical configuration for the direct-NetCDF Atolia v2 world.

This module contains world-scale targets and compact enumerations. The simulation
must treat these as accounting/calibration targets, not archaeological observations.

The v2 world intentionally extends the structural horizon to 2000--1000 BCE.
The inherited v1 object catalogue began at 1800 BCE, so importing this module
installs a v2-only availability overlay before the structural world is built.
These are broad simulation priors, not typological first-appearance claims.
"""

from dataclasses import asdict, dataclass
from typing import Dict, Tuple

import provenance_field as _base

V2_MASTER_SCHEMA = "atolia.ecmwf-master.v2-metal-lineage"
V2_RUNTIME_SCHEMA = "atolia.ecmwf-runtime.v2-metal-lineage"
V2_MODEL_VERSION = "atolia-direct-v2-step5-a3"

ELEMENTS: Tuple[str, ...] = ("Cu", "Sn", "As", "Pb", "Ag", "Au", "Fe", "Zn")
PB_ISOTOPES: Tuple[str, ...] = ("Pb204", "Pb206", "Pb207", "Pb208")
STATE_MOMENTS: Tuple[str, ...] = (
    "ore_distance_km",
    "cumulative_metal_distance_km",
    "current_object_distance_km",
    "remelt_count",
    "repair_count",
    "workshop_transition_count",
    "broker_cycle_count",
    "source_entropy",
    "technical_memory_fraction",
    "network_embedding",
    "water_mode_count",
    "ownership_transfer_count",
    "metal_lineage_age_years",
    "current_object_age_years",
    "external_exchange_fraction",
    "atesis_crossing_count",
    "manufacture_quality",
    "guild_exposure_entropy",
    "workshop_tool_depth_mean",
    "workshop_tool_depth_max",
)
COVARIANCE_MOMENTS: Tuple[str, ...] = (
    "cumulative_metal_distance_km",
    "current_object_distance_km",
    "remelt_count",
    "source_entropy",
    "technical_memory_fraction",
    "network_embedding",
    "water_mode_count",
    "broker_cycle_count",
    "manufacture_quality",
)

CARRIER_ROLES: Tuple[str, ...] = (
    "household_local", "farmer_craft_local", "warrior_frontier", "mounted_retinue",
    "mobile_pastoral", "merchant_pack", "river_boat_cargo", "coastal_boat_cargo",
    "open_sea_cargo", "court_gift_prestige", "marriage_inheritance_personal",
    "repairer_mobile", "workshop_stock", "broker_scrap_stock",
)

TERMINAL_KINDS: Tuple[str, ...] = (
    "loss", "retire", "grave", "ritual", "hoard_failed_retrieval", "boat_wreck",
    "combat_loss", "workshop_debris", "catastrophic_abandonment",
)

ATESIS_SOURCE_IDS = frozenset({"upper_atesis", "trentino_east"})
ATESIS_NODE_HINTS = ("atesis", "trento", "bolzano", "merano", "salorno", "verona_plain", "legnago")

# Broad v2 process-availability priors.  They exist to keep the 2000--1000 BCE
# simulation physically populated without pretending these are exact archaeological
# first-appearance dates.  Later regional typology can further suppress a class.
V2_OBJECT_CLASS_START_BC: Dict[str, int] = {
    "bead": 2000,
    "awl": 2000,
    "pin": 2000,
    "ring": 2000,
    "fitting": 2000,
    "knife": 2000,
    "sickle": 1900,
    "chisel": 2000,
    "axe": 2000,
    "spearhead": 1900,
    "dagger": 2000,
    "sword": 1650,
    "vessel": 1600,
    "ornament": 2000,
    "figurine": 1800,
    "ingot": 2000,
    "scrap": 2000,
}


def install_v2_object_chronology() -> None:
    """Install the v2-only class availability overlay into the shared v1 table.

    The release mass transform calls ``world._class_weights`` which ultimately
    reads ``provenance_field.OBJECT_CLASSES``.  A 2000 BCE structural slice must
    therefore have at least one physically valid class before conservation is
    evaluated.  We mutate only the start bound and preserve every v1 mass/weight,
    survival and status parameter.
    """
    missing = sorted(set(V2_OBJECT_CLASS_START_BC) - set(_base.OBJECT_CLASSES))
    if missing:
        raise RuntimeError(f"v2 chronology refers to unknown object classes: {missing}")
    for name, start_bc in V2_OBJECT_CLASS_START_BC.items():
        _base.OBJECT_CLASSES[name]["start"] = int(start_bc)


# v2_config is imported by the v2 builder before world.build(), so install the
# horizon overlay immediately.  No v1 entry point imports this module.
install_v2_object_chronology()

CARRIER_BY_CLASS: Dict[str, Tuple[Tuple[str, float], ...]] = {
    "sword": (("warrior_frontier", .62), ("mounted_retinue", .18), ("court_gift_prestige", .12), ("merchant_pack", .08)),
    "dagger": (("warrior_frontier", .46), ("marriage_inheritance_personal", .22), ("merchant_pack", .12), ("household_local", .20)),
    "spearhead": (("warrior_frontier", .55), ("mounted_retinue", .13), ("household_local", .20), ("merchant_pack", .12)),
    "fitting": (("mounted_retinue", .34), ("farmer_craft_local", .26), ("merchant_pack", .18), ("household_local", .22)),
    "sickle": (("farmer_craft_local", .72), ("household_local", .20), ("merchant_pack", .08)),
    "chisel": (("farmer_craft_local", .60), ("repairer_mobile", .16), ("household_local", .18), ("merchant_pack", .06)),
    "awl": (("farmer_craft_local", .56), ("household_local", .34), ("repairer_mobile", .10)),
    "axe": (("farmer_craft_local", .46), ("warrior_frontier", .20), ("household_local", .22), ("merchant_pack", .12)),
    "knife": (("household_local", .42), ("farmer_craft_local", .28), ("warrior_frontier", .15), ("merchant_pack", .15)),
    "ring": (("marriage_inheritance_personal", .54), ("household_local", .22), ("merchant_pack", .16), ("court_gift_prestige", .08)),
    "pin": (("marriage_inheritance_personal", .52), ("household_local", .30), ("merchant_pack", .18)),
    "bead": (("marriage_inheritance_personal", .52), ("merchant_pack", .22), ("household_local", .20), ("court_gift_prestige", .06)),
    "ornament": (("marriage_inheritance_personal", .44), ("court_gift_prestige", .28), ("merchant_pack", .20), ("household_local", .08)),
    "vessel": (("household_local", .38), ("court_gift_prestige", .25), ("merchant_pack", .22), ("river_boat_cargo", .15)),
    "figurine": (("court_gift_prestige", .50), ("merchant_pack", .22), ("household_local", .18), ("open_sea_cargo", .10)),
    "ingot": (("broker_scrap_stock", .38), ("merchant_pack", .22), ("river_boat_cargo", .22), ("coastal_boat_cargo", .18)),
    "scrap": (("broker_scrap_stock", .60), ("workshop_stock", .24), ("river_boat_cargo", .10), ("merchant_pack", .06)),
}

@dataclass(frozen=True)
class V2WorldConfig:
    world_start_bc: int = 2000
    world_end_bc: int = 1000
    primary_cu_tonnes: float = 1_000_000.0
    atesis_primary_cu_tonnes: float = 200_000.0
    primary_sn_tonnes: float = 30_000.0
    primary_ag_tonnes: float = 0.0
    primary_au_tonnes: float = 0.0
    target_atesis_crossing_object_episodes: float = 50_000_000.0
    pristine_recovery_probability: float = 0.60
    recycled_recovery_probability: float = 0.85
    atesis_crossing_share_prior: float = 0.30
    hydro_candidate_density_multiplier: float = 5.0
    hydro_snapshot_years: int = 25
    benchmark_particles_per_cell: int = 2
    full_particles_per_cell: int = 16
    benchmark_cell_limit: int = 256
    max_life_events: int = 128
    netcdf_chunk_rows: int = 65536
    compression_level: int = 4

    def expected_object_lives_per_metal_lineage(self) -> float:
        r0, r1 = float(self.pristine_recovery_probability), float(self.recycled_recovery_probability)
        if not 0 <= r0 < 1 or not 0 <= r1 < 1:
            raise ValueError("recovery probabilities must be in [0,1)")
        return 1.0 + r0 / max(1e-12, 1.0 - r1)

    def objectization_fraction_prior(self, representative_object_mass_kg: float) -> float:
        mean_mass = max(1e-6, float(representative_object_mass_kg))
        lives = self.expected_object_lives_per_metal_lineage()
        crossing = max(1e-6, min(1.0, float(self.atesis_crossing_share_prior)))
        primary_kg = max(1.0, float(self.primary_cu_tonnes) * 1000.0)
        required_primary_objectized_kg = float(self.target_atesis_crossing_object_episodes) * mean_mass / (lives * crossing)
        return min(1.0, max(0.0, required_primary_objectized_kg / primary_kg))

    def as_dict(self) -> dict:
        out = asdict(self)
        out["expected_object_lives_per_metal_lineage"] = self.expected_object_lives_per_metal_lineage()
        return out

DEFAULT_CONFIG = V2WorldConfig()
