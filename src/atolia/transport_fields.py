from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Dict, Mapping, Sequence

import numpy as np

import provenance_field_mediterranean as med


FIELD_MODEL_VERSION = "transport-fields-v1"

FIELD_NAMES = (
    "padanic_adriatic",
    "rhine_north_sea",
    "rhone_west_med",
    "danube_sava_morava",
    "mediterranean_littoral",
    "adriatic_ionian_aegean",
    "aegean_anatolia_cyprus",
    "britain_channel_continental",
    "west_med_island_chain",
    "alpine_pass_transfer",
    "open_sea_prestige",
    "local_catchment_reuse",
)

REGION_FIELD_PRIORS: Dict[str, Dict[str, float]] = {
    "atolia_core": {"padanic_adriatic": 1.0, "alpine_pass_transfer": .42, "local_catchment_reuse": .72},
    "rhone": {"rhone_west_med": 1.0, "mediterranean_littoral": .38, "alpine_pass_transfer": .22},
    "rhine": {"rhine_north_sea": 1.0, "britain_channel_continental": .30, "alpine_pass_transfer": .20},
    "severn_britain": {"britain_channel_continental": 1.0, "rhine_north_sea": .22},
    "western_mediterranean": {"west_med_island_chain": .85, "mediterranean_littoral": .80, "rhone_west_med": .30},
    "central_mediterranean": {"mediterranean_littoral": .86, "west_med_island_chain": .52, "adriatic_ionian_aegean": .28},
    "aegean": {"adriatic_ionian_aegean": .86, "aegean_anatolia_cyprus": .72, "mediterranean_littoral": .40},
    "crete": {"adriatic_ionian_aegean": .66, "aegean_anatolia_cyprus": .72, "open_sea_prestige": .30},
    "cyprus": {"aegean_anatolia_cyprus": 1.0, "open_sea_prestige": .32},
    "western_anatolia": {"aegean_anatolia_cyprus": 1.0, "danube_sava_morava": .16},
    "hatti_anatolia": {"aegean_anatolia_cyprus": .72, "danube_sava_morava": .18},
    "lower_danube": {"danube_sava_morava": 1.0, "adriatic_ionian_aegean": .22},
    "levant_egypt": {"aegean_anatolia_cyprus": .60, "open_sea_prestige": .38, "mediterranean_littoral": .45},
    "other": {"local_catchment_reuse": .40},
}

MODE_FEATURES: Dict[str, Dict[str, float]] = {
    "river": {"river": 1.0, "shore": .05, "pass": 0.0, "sea": 0.0},
    "river_down": {"river": 1.0}, "river_up": {"river": .92}, "river_plain": {"river": .84},
    "plain_river": {"river": .82}, "lagoon": {"shore": .94, "river": .25},
    "coast": {"shore": 1.0, "sea": .18}, "coast_land": {"shore": .78, "pass": .18},
    "coastal_transfer": {"shore": .82, "sea": .16}, "sea": {"sea": 1.0, "shore": .08},
    "pass": {"pass": 1.0}, "mountain": {"pass": .92}, "mountain_local": {"pass": .76, "local": .32},
    "jura_alpine_transfer": {"pass": 1.0}, "plain": {"local": .62},
}

OBJECT_FIELD_MIX: Dict[str, Dict[str, float]] = {
    "sword": {"rhine_north_sea": .17, "danube_sava_morava": .20, "padanic_adriatic": .14,
              "mediterranean_littoral": .12, "adriatic_ionian_aegean": .12, "rhone_west_med": .08,
              "aegean_anatolia_cyprus": .06, "britain_channel_continental": .04,
              "alpine_pass_transfer": .04, "open_sea_prestige": .03},
    "dagger": {"padanic_adriatic": .20, "danube_sava_morava": .14, "rhone_west_med": .10,
               "mediterranean_littoral": .14, "adriatic_ionian_aegean": .11,
               "alpine_pass_transfer": .08, "local_catchment_reuse": .13, "open_sea_prestige": .10},
    "spearhead": {"danube_sava_morava": .18, "rhine_north_sea": .14, "padanic_adriatic": .18,
                  "britain_channel_continental": .08, "alpine_pass_transfer": .10,
                  "mediterranean_littoral": .10, "local_catchment_reuse": .22},
    "ornament": {"mediterranean_littoral": .25, "west_med_island_chain": .13,
                 "adriatic_ionian_aegean": .17, "aegean_anatolia_cyprus": .12,
                 "open_sea_prestige": .13, "rhone_west_med": .08, "local_catchment_reuse": .12},
    "vessel": {"mediterranean_littoral": .24, "adriatic_ionian_aegean": .18,
               "padanic_adriatic": .12, "aegean_anatolia_cyprus": .12,
               "open_sea_prestige": .10, "local_catchment_reuse": .16, "rhone_west_med": .08},
    "figurine": {"mediterranean_littoral": .20, "aegean_anatolia_cyprus": .18,
                 "open_sea_prestige": .20, "adriatic_ionian_aegean": .14,
                 "local_catchment_reuse": .18, "west_med_island_chain": .10},
    "ingot": {"padanic_adriatic": .22, "danube_sava_morava": .14, "rhone_west_med": .10,
              "mediterranean_littoral": .12, "adriatic_ionian_aegean": .10,
              "aegean_anatolia_cyprus": .08, "alpine_pass_transfer": .08,
              "local_catchment_reuse": .16},
    "scrap": {"local_catchment_reuse": .60, "padanic_adriatic": .18,
              "alpine_pass_transfer": .08, "danube_sava_morava": .06, "rhone_west_med": .04,
              "rhine_north_sea": .04},
    "axe": {"local_catchment_reuse": .35, "padanic_adriatic": .16, "danube_sava_morava": .13,
            "rhine_north_sea": .11, "rhone_west_med": .08, "britain_channel_continental": .07,
            "alpine_pass_transfer": .10},
    "sickle": {"local_catchment_reuse": .55, "padanic_adriatic": .15, "danube_sava_morava": .10,
               "rhine_north_sea": .06, "rhone_west_med": .05, "alpine_pass_transfer": .09},
    "chisel": {"local_catchment_reuse": .55, "padanic_adriatic": .15, "alpine_pass_transfer": .10,
               "danube_sava_morava": .08, "rhine_north_sea": .07, "rhone_west_med": .05},
    "knife": {"local_catchment_reuse": .42, "padanic_adriatic": .14, "danube_sava_morava": .10,
              "rhine_north_sea": .08, "rhone_west_med": .07, "mediterranean_littoral": .08,
              "alpine_pass_transfer": .07, "britain_channel_continental": .04},
    "fitting": {"local_catchment_reuse": .50, "padanic_adriatic": .16, "danube_sava_morava": .08,
                "rhine_north_sea": .06, "rhone_west_med": .06, "mediterranean_littoral": .06,
                "alpine_pass_transfer": .08},
    "ring": {"local_catchment_reuse": .35, "mediterranean_littoral": .14, "padanic_adriatic": .13,
             "rhone_west_med": .09, "rhine_north_sea": .08, "danube_sava_morava": .08,
             "adriatic_ionian_aegean": .07, "britain_channel_continental": .06},
    "pin": {"local_catchment_reuse": .42, "padanic_adriatic": .13, "rhine_north_sea": .09,
            "danube_sava_morava": .09, "rhone_west_med": .08, "mediterranean_littoral": .07,
            "britain_channel_continental": .06, "alpine_pass_transfer": .06},
    "awl": {"local_catchment_reuse": .66, "padanic_adriatic": .12, "alpine_pass_transfer": .07,
            "danube_sava_morava": .06, "rhine_north_sea": .05, "rhone_west_med": .04},
    "bead": {"local_catchment_reuse": .36, "mediterranean_littoral": .14, "padanic_adriatic": .12,
             "rhone_west_med": .08, "rhine_north_sea": .07, "adriatic_ionian_aegean": .08,
             "west_med_island_chain": .07, "open_sea_prestige": .08},
}

BUNDLE_FIELD_MIX: Dict[str, Dict[str, float]] = {
    "upper_atesis_south": {"padanic_adriatic": .72, "local_catchment_reuse": .18, "alpine_pass_transfer": .10},
    "trentino_to_trunk": {"padanic_adriatic": .72, "alpine_pass_transfer": .18, "local_catchment_reuse": .10},
    "cross_alpine_import": {"alpine_pass_transfer": .50, "padanic_adriatic": .28, "danube_sava_morava": .12, "rhine_north_sea": .10},
    "po_redistribution": {"padanic_adriatic": .60, "local_catchment_reuse": .20, "rhone_west_med": .10, "mediterranean_littoral": .10},
    "adriatic_export": {"padanic_adriatic": .35, "adriatic_ionian_aegean": .45, "mediterranean_littoral": .20},
    "adriatic_return": {"adriatic_ionian_aegean": .45, "padanic_adriatic": .35, "danube_sava_morava": .20},
    "tyrrhenian_crossfeed": {"rhone_west_med": .30, "mediterranean_littoral": .35, "padanic_adriatic": .20, "alpine_pass_transfer": .15},
    "danubian_competitor": {"danube_sava_morava": .60, "alpine_pass_transfer": .20, "adriatic_ionian_aegean": .20},
    "local_recycling": {"local_catchment_reuse": .78, "padanic_adriatic": .22},
    "prestige_long_distance": {"open_sea_prestige": .25, "mediterranean_littoral": .18, "adriatic_ionian_aegean": .15,
                              "danube_sava_morava": .12, "rhine_north_sea": .10, "rhone_west_med": .10,
                              "padanic_adriatic": .10},
    "western_med_tail": {"west_med_island_chain": .45, "mediterranean_littoral": .35, "rhone_west_med": .20},
    "rhone_atolia_tail": {"rhone_west_med": .48, "alpine_pass_transfer": .18, "padanic_adriatic": .34},
    "rhine_rhone_tail": {"rhine_north_sea": .38, "rhone_west_med": .38, "alpine_pass_transfer": .24},
    "severn_continental_tail": {"britain_channel_continental": .56, "rhine_north_sea": .28, "rhone_west_med": .16},
    "central_med_tail": {"mediterranean_littoral": .42, "west_med_island_chain": .22, "adriatic_ionian_aegean": .24, "open_sea_prestige": .12},
    "aegean_adriatic_tail": {"adriatic_ionian_aegean": .55, "aegean_anatolia_cyprus": .20, "mediterranean_littoral": .25},
    "cyprus_aegean_tail": {"aegean_anatolia_cyprus": .65, "adriatic_ionian_aegean": .20, "open_sea_prestige": .15},
    "hatti_aegean_tail": {"aegean_anatolia_cyprus": .72, "open_sea_prestige": .18, "adriatic_ionian_aegean": .10},
    "lower_danube_tail": {"danube_sava_morava": .60, "adriatic_ionian_aegean": .22, "alpine_pass_transfer": .18},
    "levant_egypt_tail": {"aegean_anatolia_cyprus": .42, "mediterranean_littoral": .28, "open_sea_prestige": .30},
}


def normalize_mix(mix: Mapping[str, float]) -> Dict[str, float]:
    arr = {name: max(0.0, float(mix.get(name, 0.0))) for name in FIELD_NAMES}
    total = sum(arr.values())
    if total <= 0:
        return {name: 1.0 / len(FIELD_NAMES) for name in FIELD_NAMES}
    return {name: value / total for name, value in arr.items()}


def blend_mixes(*weighted: tuple[Mapping[str, float], float]) -> Dict[str, float]:
    out = {name: 0.0 for name in FIELD_NAMES}
    for mix, weight in weighted:
        for name, value in normalize_mix(mix).items():
            out[name] += max(0.0, float(weight)) * value
    return normalize_mix(out)


def object_field_mix(object_class: str, bundle_family: str, phase: float = .5) -> Dict[str, float]:
    obj = OBJECT_FIELD_MIX.get(object_class, OBJECT_FIELD_MIX["fitting"])
    bundle = BUNDLE_FIELD_MIX.get(bundle_family, {"local_catchment_reuse": 1.0})
    # Early production/corridor identity matters more initially; later biographies
    # permit object-class circulation to dominate more strongly.
    class_weight = float(np.clip(.48 + .22 * phase, .42, .76))
    return blend_mixes((obj, class_weight), (bundle, 1.0 - class_weight))


def _phase_from_bc(date_bc: int) -> float:
    return float(np.clip((1800.0 - float(date_bc)) / 800.0, 0.0, 1.0))


def _region_activation(region: str) -> Dict[str, float]:
    base = {name: .025 for name in FIELD_NAMES}
    for name, value in REGION_FIELD_PRIORS.get(region, REGION_FIELD_PRIORS["other"]).items():
        base[name] += float(value)
    return base


def edge_field_vector(world: Any, edge: Any, date_bc: int = 1300) -> Dict[str, float]:
    """Return positive basis-field activation for one physical edge."""
    ra = med.REGION_BY_NODE.get(edge.a, "other")
    rb = med.REGION_BY_NODE.get(edge.b, "other")
    va, vb = _region_activation(ra), _region_activation(rb)
    vec = {name: math.sqrt(va[name] * vb[name]) for name in FIELD_NAMES}
    mode = MODE_FEATURES.get(str(edge.mode), {})
    m = str(edge.mode).lower()
    river = float(mode.get("river", 1.0 if "river" in m else 0.0))
    shore = float(mode.get("shore", 1.0 if any(x in m for x in ("coast", "lagoon")) else 0.0))
    sea = float(mode.get("sea", 1.0 if "sea" in m else 0.0))
    pas = float(mode.get("pass", 1.0 if any(x in m for x in ("pass", "mountain", "alpine", "jura")) else 0.0))
    local = float(mode.get("local", 0.0))

    vec["padanic_adriatic"] *= 1.0 + .35 * river + .22 * shore
    vec["rhine_north_sea"] *= 1.0 + .52 * river + .18 * shore
    vec["rhone_west_med"] *= 1.0 + .48 * river + .25 * shore
    vec["danube_sava_morava"] *= 1.0 + .56 * river
    vec["mediterranean_littoral"] *= 1.0 + .62 * shore + .20 * sea
    vec["adriatic_ionian_aegean"] *= 1.0 + .48 * shore + .34 * sea
    vec["aegean_anatolia_cyprus"] *= 1.0 + .34 * shore + .48 * sea
    vec["britain_channel_continental"] *= 1.0 + .38 * river + .34 * shore + .12 * sea
    vec["west_med_island_chain"] *= 1.0 + .35 * shore + .54 * sea
    vec["alpine_pass_transfer"] *= 1.0 + .90 * pas
    vec["open_sea_prestige"] *= 1.0 + 1.10 * sea
    vec["local_catchment_reuse"] *= 1.0 + .46 * river + .52 * local - .22 * sea

    # Mild temporal opening of maritime fields through the Bronze Age; this is a
    # generic world prior, not a claim that every specific corridor grew monotonically.
    phase = _phase_from_bc(date_bc)
    for name in ("mediterranean_littoral", "adriatic_ionian_aegean", "aegean_anatolia_cyprus", "open_sea_prestige"):
        vec[name] *= .88 + .28 * phase
    return {name: max(1e-6, float(value)) for name, value in vec.items()}


def effective_edge_weight(world: Any, edge: Any, mix: Mapping[str, float], date_bc: int = 1300) -> float:
    """Geometric mixture of positive basis fields; higher means easier movement."""
    alpha = normalize_mix(mix)
    fields = edge_field_vector(world, edge, date_bc)
    log_w = sum(alpha[name] * math.log(max(1e-9, fields[name])) for name in FIELD_NAMES)
    return float(math.exp(log_w))


def field_signature(world: Any, edge: Any, mix: Mapping[str, float], date_bc: int = 1300) -> np.ndarray:
    fields = edge_field_vector(world, edge, date_bc)
    alpha = normalize_mix(mix)
    arr = np.asarray([alpha[name] * fields[name] for name in FIELD_NAMES], dtype=float)
    arr = np.clip(arr, 1e-12, None)
    return arr / arr.sum()


def js_divergence(p: Sequence[float], q: Sequence[float]) -> float:
    a = np.asarray(p, dtype=float); b = np.asarray(q, dtype=float)
    a = np.clip(a, 1e-12, None); b = np.clip(b, 1e-12, None)
    a /= a.sum(); b /= b.sum(); m = .5 * (a + b)
    return float(.5 * np.sum(a * np.log(a / m)) + .5 * np.sum(b * np.log(b / m)))
