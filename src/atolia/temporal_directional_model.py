from __future__ import annotations

import math
from typing import Any, Dict, Mapping

import numpy as np

import provenance_field_mediterranean as med
import transport_fields as fields


TEMPORAL_DIRECTIONAL_VERSION = "temporal-directional-v1"

# Gaussian activation pulses are broad calibration priors, not claims of exact event dates.
# amplitude is added to a baseline of 1.0.
FIELD_TEMPORAL_PULSES: Dict[str, tuple[Dict[str, float], ...]] = {
    "padanic_adriatic": ({"center_bc": 1325.0, "sigma_years": 180.0, "amplitude": .28},),
    "rhine_north_sea": ({"center_bc": 1275.0, "sigma_years": 190.0, "amplitude": .34},),
    "rhone_west_med": ({"center_bc": 1275.0, "sigma_years": 210.0, "amplitude": .22},),
    "danube_sava_morava": ({"center_bc": 1325.0, "sigma_years": 210.0, "amplitude": .30},),
    "mediterranean_littoral": ({"center_bc": 1225.0, "sigma_years": 190.0, "amplitude": .48},),
    # Deliberately broad Adriatic -> Sicily/Ionian/Aegean opening pulse. This is the
    # calibration knob for the user's desired outbursting exchange hypothesis.
    "adriatic_ionian_aegean": ({"center_bc": 1225.0, "sigma_years": 145.0, "amplitude": .95},),
    "aegean_anatolia_cyprus": ({"center_bc": 1200.0, "sigma_years": 165.0, "amplitude": .50},),
    "britain_channel_continental": ({"center_bc": 1300.0, "sigma_years": 205.0, "amplitude": .28},),
    "west_med_island_chain": ({"center_bc": 1225.0, "sigma_years": 190.0, "amplitude": .44},),
    "alpine_pass_transfer": ({"center_bc": 1375.0, "sigma_years": 220.0, "amplitude": .18},),
    "open_sea_prestige": ({"center_bc": 1175.0, "sigma_years": 150.0, "amplitude": .62},),
    "local_catchment_reuse": (),
}

# Positive means movement along the curated edge's a->b orientation; negative means
# against it. On river_down edges the a->b orientation is explicitly downstream;
# on river_up it is explicitly upstream and is corrected by edge_direction_sign().
FIELD_DIRECTION_BIAS: Dict[str, float] = {
    "padanic_adriatic": .52,
    "rhine_north_sea": .78,
    "rhone_west_med": .56,
    "danube_sava_morava": .20,
    "mediterranean_littoral": .04,
    "adriatic_ionian_aegean": .62,
    "aegean_anatolia_cyprus": .36,
    "britain_channel_continental": .18,
    "west_med_island_chain": .08,
    "alpine_pass_transfer": .02,
    "open_sea_prestige": .05,
    "local_catchment_reuse": 0.0,
}

# Object-specific direction response. Swords strongly express Rhine export direction,
# but only weakly force Danubian direction because Danubian production is broader/local.
OBJECT_DIRECTION_RESPONSE: Dict[str, Dict[str, float]] = {
    "sword": {"rhine_north_sea": 1.35, "danube_sava_morava": .48, "padanic_adriatic": 1.02,
              "adriatic_ionian_aegean": 1.18, "aegean_anatolia_cyprus": .92},
    "dagger": {"rhine_north_sea": .88, "danube_sava_morava": .70, "padanic_adriatic": .92,
               "adriatic_ionian_aegean": .92},
    "spearhead": {"rhine_north_sea": .82, "danube_sava_morava": .72, "padanic_adriatic": .82},
    "ingot": {"rhine_north_sea": 1.05, "danube_sava_morava": .90, "padanic_adriatic": 1.08,
              "adriatic_ionian_aegean": .94},
    "ornament": {"mediterranean_littoral": .35, "adriatic_ionian_aegean": .62,
                 "aegean_anatolia_cyprus": .56, "west_med_island_chain": .22},
    "awl": {"rhine_north_sea": .18, "danube_sava_morava": .16, "padanic_adriatic": .20},
    "scrap": {"rhine_north_sea": .20, "danube_sava_morava": .18, "padanic_adriatic": .24},
}

# Region-specific production mass-share multipliers. Values are relative priors that
# renormalize object-class shares inside each bundle/time slice; they do not create
# extra tonnes. Missing classes/regions default to 1.0.
PRODUCTION_REGION_PRIORS: Dict[str, Dict[str, float]] = {
    "sword": {
        "atolia_core": 1.30, "lower_danube": 1.20, "aegean": 1.02, "crete": .70,
        "western_anatolia": .62, "central_mediterranean": .60, "western_mediterranean": .48,
        "rhone": .54, "rhine": .42, "severn_britain": .25, "cyprus": .36,
        "levant_egypt": .28, "other": .55,
    },
    "dagger": {"atolia_core": 1.18, "lower_danube": 1.05, "aegean": .98, "rhine": .70,
               "rhone": .74, "western_mediterranean": .68, "central_mediterranean": .76},
    "spearhead": {"atolia_core": 1.08, "lower_danube": 1.12, "rhine": .92, "rhone": .84,
                  "severn_britain": .78, "aegean": .86},
    "ingot": {"atolia_core": 1.22, "lower_danube": 1.00, "rhine": .76, "rhone": .78,
              "western_mediterranean": .82, "central_mediterranean": .92, "cyprus": 1.10},
    "awl": {"atolia_core": 1.08, "lower_danube": 1.00, "rhine": 1.00, "rhone": 1.00,
            "severn_britain": 1.00, "western_mediterranean": .98, "central_mediterranean": .98,
            "aegean": .98, "western_anatolia": .98, "levant_egypt": .98, "other": 1.0},
    "scrap": {"atolia_core": 1.12, "lower_danube": 1.05, "rhine": 1.0, "rhone": 1.0,
              "severn_britain": 1.0, "western_mediterranean": 1.0, "central_mediterranean": 1.0,
              "aegean": 1.0, "western_anatolia": 1.0, "other": 1.0},
}

# Broad object production pulses. Again, calibration priors rather than exact dates.
PRODUCTION_TEMPORAL_PULSES: Dict[str, tuple[Dict[str, float], ...]] = {
    "sword": (
        {"region": "atolia_core", "center_bc": 1350.0, "sigma_years": 170.0, "amplitude": .42},
        {"region": "lower_danube", "center_bc": 1300.0, "sigma_years": 190.0, "amplitude": .36},
        {"region": "aegean", "center_bc": 1200.0, "sigma_years": 160.0, "amplitude": .28},
    ),
    "ornament": ({"region": "central_mediterranean", "center_bc": 1200.0, "sigma_years": 180.0, "amplitude": .20},),
    "ingot": ({"region": "cyprus", "center_bc": 1225.0, "sigma_years": 190.0, "amplitude": .24},),
}

# Soft destination-origin priors for later intensity propagation. They are intentionally
# not consumed as hard counts in Round 1. Western Anatolia is the Troy-like calibration sink.
DESTINATION_ORIGIN_PRIORS: Dict[str, Dict[str, float]] = {
    "western_anatolia": {"danubian": .30, "aegean_greek": .30, "adriatic_padanic": .30, "other": .10},
    "aegean": {"aegean_greek": .40, "adriatic_padanic": .24, "danubian": .20, "other": .16},
    "severn_britain": {"britain_channel": .52, "rhine_continental": .30, "other": .18},
}

# Route temperature controls biography entropy. Sea/coast are intentionally more permissive.
OBJECT_ROUTE_TEMPERATURE: Dict[str, float] = {
    "ingot": .18, "scrap": .16, "sickle": .16, "chisel": .17, "awl": .14,
    "axe": .20, "fitting": .18, "knife": .22, "pin": .24, "ring": .27,
    "spearhead": .28, "dagger": .34, "vessel": .48, "ornament": .52,
    "sword": .46, "figurine": .54, "bead": .38,
}
MODE_TEMPERATURE_MULTIPLIER = {"river": .72, "land": .82, "pass": .88, "coast": 1.28, "sea": 1.62}


def gaussian_pulse(date_bc: int | float, center_bc: float, sigma_years: float, amplitude: float) -> float:
    sigma = max(1.0, float(sigma_years))
    return float(amplitude) * math.exp(-0.5 * ((float(date_bc) - float(center_bc)) / sigma) ** 2)


def field_temporal_activation(field_name: str, date_bc: int) -> float:
    value = 1.0
    for pulse in FIELD_TEMPORAL_PULSES.get(field_name, ()):
        value += gaussian_pulse(date_bc, **pulse)
    return max(.05, float(value))


def production_multiplier(object_class: str, region: str, date_bc: int) -> float:
    priors = PRODUCTION_REGION_PRIORS.get(object_class, {})
    value = float(priors.get(region, priors.get("other", 1.0)))
    for pulse in PRODUCTION_TEMPORAL_PULSES.get(object_class, ()):
        if pulse["region"] == region:
            value *= 1.0 + gaussian_pulse(
                date_bc, pulse["center_bc"], pulse["sigma_years"], pulse["amplitude"]
            )
    return float(np.clip(value, .08, 3.0))


def production_multiplier_for_bundle(object_class: str, bundle: Any, date_bc: int) -> float:
    # Round 1 uses production at the bundle origin. Round 3 will replace this with
    # distributed production cells over the full carrier manifold.
    region = med.REGION_BY_NODE.get(bundle.origin, "other")
    return production_multiplier(object_class, region, date_bc)


def _physical_type(mode: str) -> str:
    m = str(mode).lower()
    if "river" in m or "lagoon" in m:
        return "river"
    if "sea" in m:
        return "sea"
    if "coast" in m:
        return "coast"
    if any(x in m for x in ("pass", "mountain", "alpine", "jura")):
        return "pass"
    return "land"


def edge_direction_sign(edge: Any, from_node: str, to_node: str) -> float:
    """Signed movement relative to the edge's semantic forward orientation."""
    forward = 1.0 if (from_node == edge.a and to_node == edge.b) else -1.0
    mode = str(edge.mode).lower()
    # A river_up edge is stored origin->destination upstream, so reverse it to make
    # positive sign consistently mean hydrological downstream.
    if "river_up" in mode:
        forward *= -1.0
    return forward


def directional_log_bias(
    object_class: str,
    mix: Mapping[str, float],
    edge: Any,
    from_node: str,
    to_node: str,
    date_bc: int,
) -> float:
    sign = edge_direction_sign(edge, from_node, to_node)
    response = OBJECT_DIRECTION_RESPONSE.get(object_class, {})
    total = 0.0
    for name, alpha in fields.normalize_mix(mix).items():
        base_bias = FIELD_DIRECTION_BIAS.get(name, 0.0)
        object_response = float(response.get(name, 1.0))
        temporal = field_temporal_activation(name, date_bc)
        # Activation changes the strength of a directional regime only mildly;
        # it does not flip its orientation.
        total += float(alpha) * base_bias * object_response * (temporal ** .35)
    ptype = _physical_type(edge.mode)
    if ptype == "river":
        scale = 1.0
    elif ptype == "coast":
        scale = .72
    elif ptype == "sea":
        scale = .58
    else:
        scale = .34
    return float(np.clip(sign * scale * total, -1.8, 1.8))


def route_temperature(object_class: str, edge_mode: str, date_bc: int) -> float:
    base = OBJECT_ROUTE_TEMPERATURE.get(object_class, .28)
    ptype = _physical_type(edge_mode)
    temp = base * MODE_TEMPERATURE_MULTIPLIER.get(ptype, 1.0)
    # Slight late-Bronze-age increase in maritime lateral option entropy.
    phase = float(np.clip((1800.0 - date_bc) / 800.0, 0.0, 1.0))
    if ptype in {"coast", "sea"}:
        temp *= .92 + .32 * phase
    return float(np.clip(temp, .05, 1.25))


def destination_origin_prior(region: str) -> Dict[str, float]:
    prior = DESTINATION_ORIGIN_PRIORS.get(region, {"other": 1.0})
    total = sum(float(v) for v in prior.values()) or 1.0
    return {k: float(v) / total for k, v in prior.items()}
