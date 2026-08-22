from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Dict, Iterable, Mapping, Sequence

import numpy as np


@dataclass(frozen=True)
class GuildProfile:
    guild_id: str
    developer_name: str
    operations: Mapping[str, float]
    classes: Mapping[str, float]
    channels: Mapping[str, float]
    mobility_scale: float
    convergence_prior: float
    status_bias: float
    persistence_years: float


# These are developer-only latent communities of practice. They are deliberately
# not player-facing factions, ethnic groups or literal historical corporations.
GUILD_PROFILES: Dict[str, GuildProfile] = {
    "G-01": GuildProfile(
        "G-01", "Split-Mould",
        {"casting": 1.0, "moulding": 1.0, "structural_geometry": .42, "finishing": .18},
        {"axe": .85, "spearhead": .85, "dagger": .72, "sword": .72, "fitting": .68, "figurine": .64, "ingot": .35},
        {"visual": .38, "morphometrics": .92, "ct": .86, "metallography": .26},
        310.0, .34, .06, 540.0,
    ),
    "G-02": GuildProfile(
        "G-02", "Socket-Rib",
        {"structural_geometry": 1.0, "casting": .74, "moulding": .63, "edge_treatment": .20},
        {"axe": 1.0, "spearhead": 1.0, "fitting": .72, "chisel": .38, "dagger": .30},
        {"visual": .62, "morphometrics": 1.0, "ct": .91, "metallography": .20},
        390.0, .42, .04, 510.0,
    ),
    "G-03": GuildProfile(
        "G-03", "Raised-Sheet",
        {"sheetwork": 1.0, "deformation": .92, "thermal": .53, "finishing": .44, "joining": .24},
        {"vessel": 1.0, "ornament": .72, "fitting": .63, "ring": .31},
        {"visual": .44, "morphometrics": .71, "metallography": .84, "microscopy": .66, "ct": .45},
        440.0, .27, .18, 760.0,
    ),
    "G-04": GuildProfile(
        "G-04", "Anneal-Line",
        {"thermal": 1.0, "deformation": .81, "sheetwork": .66, "wirework": .58, "edge_treatment": .34},
        {"vessel": .82, "ornament": .72, "ring": .68, "pin": .62, "knife": .55, "sickle": .55, "axe": .42, "sword": .42},
        {"metallography": 1.0, "hardness": .88, "microscopy": .72, "visual": .08},
        360.0, .49, .02, 820.0,
    ),
    "G-05": GuildProfile(
        "G-05", "Cold-Edge",
        {"edge_treatment": 1.0, "deformation": .78, "thermal": .51, "finishing": .48},
        {"knife": 1.0, "sickle": .92, "axe": .88, "chisel": .88, "dagger": .85, "sword": .85, "spearhead": .71},
        {"hardness": 1.0, "metallography": .91, "morphometrics": .48, "microscopy": .62},
        410.0, .61, .03, 920.0,
    ),
    "G-06": GuildProfile(
        "G-06", "Rivet-Knot",
        {"joining": 1.0, "assembly": .93, "sheetwork": .44, "repair": .34},
        {"vessel": 1.0, "fitting": .91, "dagger": .52, "spearhead": .42, "ornament": .48, "sword": .38},
        {"visual": .55, "morphometrics": .91, "ct": .79, "microscopy": .68, "xrf": .30},
        470.0, .31, .09, 680.0,
    ),
    "G-07": GuildProfile(
        "G-07", "Repair-Loop",
        {"repair": 1.0, "joining": .71, "reworking": .88, "edge_treatment": .46, "recycling": .51},
        {"vessel": .88, "sword": .82, "dagger": .73, "axe": .78, "knife": .70, "fitting": .77, "sickle": .63, "ornament": .52},
        {"visual": .47, "xrf": .66, "metallography": .64, "ct": .74, "microscopy": .76, "morphometrics": .51},
        520.0, .36, -.03, 740.0,
    ),
    "G-08": GuildProfile(
        "G-08", "Surface-Skin",
        {"surface": 1.0, "decoration": .90, "finishing": .56, "joining": .18},
        {"ornament": 1.0, "vessel": .91, "figurine": .84, "fitting": .75, "ring": .68, "sword": .37},
        {"surface_xrf": 1.0, "microscopy": .93, "visual": .68, "xrf": .45, "ct": .22},
        610.0, .39, .34, 980.0,
    ),
    "G-09": GuildProfile(
        "G-09", "Wire-Ring",
        {"wirework": 1.0, "deformation": .74, "thermal": .42, "finishing": .39},
        {"ring": 1.0, "pin": .92, "ornament": .91, "bead": .73, "fitting": .57},
        {"morphometrics": 1.0, "visual": .62, "metallography": .57, "microscopy": .52},
        650.0, .52, .12, 860.0,
    ),
    "G-10": GuildProfile(
        "G-10", "Wax-Branch",
        {"lost_wax": 1.0, "casting": .90, "moulding": .72, "structural_geometry": .48, "finishing": .43},
        {"figurine": 1.0, "ornament": .88, "vessel": .72, "fitting": .67, "sword": .18},
        {"ct": 1.0, "visual": .47, "morphometrics": .61, "microscopy": .44, "metallography": .32},
        720.0, .24, .29, 940.0,
    ),
    "G-11": GuildProfile(
        "G-11", "Scrap-Sum",
        {"recycling": 1.0, "batching": .96, "repair": .42, "casting": .34, "refining": .45},
        {"scrap": 1.0, "ingot": .87, "fitting": .61, "axe": .52, "sickle": .46, "vessel": .42, "spearhead": .41},
        {"xrf": .81, "isotopes": 1.0, "metallography": .34, "visual": .12},
        290.0, .22, -.18, 690.0,
    ),
    "G-12": GuildProfile(
        "G-12", "Fine-Polish",
        {"finishing": 1.0, "surface": .54, "edge_treatment": .52, "decoration": .41},
        {"sword": .82, "dagger": .73, "knife": .72, "vessel": .83, "ornament": .91, "figurine": .78, "axe": .48},
        {"microscopy": 1.0, "visual": .53, "morphometrics": .48, "surface_xrf": .28},
        560.0, .58, .27, 910.0,
    ),
}

# Weak co-occurrence biases; these do not make packages or factions. They merely
# encode that some skills are more often learned/used together than others.
CO_AFFINITY = {
    ("G-01", "G-02"): .20,
    ("G-03", "G-04"): .24,
    ("G-03", "G-06"): .18,
    ("G-04", "G-05"): .17,
    ("G-04", "G-09"): .16,
    ("G-06", "G-07"): .18,
    ("G-07", "G-11"): .27,
    ("G-08", "G-12"): .24,
    ("G-10", "G-12"): .14,
}


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-max(-30.0, min(30.0, x))))


def _cosine(a: Sequence[float], b: Sequence[float]) -> float:
    aa = np.asarray(a, dtype=float)
    bb = np.asarray(b, dtype=float)
    denom = float(np.linalg.norm(aa) * np.linalg.norm(bb))
    return 0.0 if denom <= 0 else float(np.dot(aa, bb) / denom)


def workshop_affinities(world: Any, workshop: Any) -> Dict[str, float]:
    """Return non-exclusive guild affinities for one workshop.

    The current Mediterranean world already seeds twelve guild prototypes and a
    primary convenience guild. Here we recover the richer continuous vector from
    technical similarity, network distance and weak co-affinity.
    """
    assigned = getattr(world, "workshop_guild", {}).get(workshop.id)
    raw: Dict[str, float] = {}
    for guild_id, profile in GUILD_PROFILES.items():
        data = getattr(world, "guilds", {}).get(guild_id)
        if not data:
            raw[guild_id] = 0.02
            continue
        prototype = data["prototype"]
        sim = _cosine(workshop.technical_vector, prototype)
        try:
            distance = float(world._shortest_distance(workshop.node_id, data["anchor_node"]))
        except Exception:
            distance = 9999.0
        spatial = math.exp(-distance / max(80.0, profile.mobility_scale))
        technical = _sigmoid(10.0 * (sim - 0.78))
        affinity = 0.72 * technical + 0.28 * spatial
        if assigned == guild_id:
            affinity += 0.16
        raw[guild_id] = float(np.clip(affinity, 0.0, 0.98))

    # Allow related practices to pull each other up weakly without making them a
    # fixed bundle. This is deliberately one small pass, not iterative diffusion.
    enriched = dict(raw)
    for (a, b), strength in CO_AFFINITY.items():
        enriched[a] = float(np.clip(enriched[a] + strength * raw[b] * 0.25, 0.0, .99))
        enriched[b] = float(np.clip(enriched[b] + strength * raw[a] * 0.25, 0.0, .99))
    return enriched


def infer_operations(sequence: Sequence[str], object_class: str, recycle_fraction: float = 0.0) -> list[str]:
    ops: list[str] = []
    text = " ".join(sequence).lower()
    if any(k in text for k in ("cast", "runner", "gate")):
        ops.append("casting")
    if any(k in text for k in ("mould", "core")):
        ops.append("moulding")
    if "lost-wax" in text or "wax" in text:
        ops.append("lost_wax")
    if any(k in text for k in ("hammer", "worked", "planished", "raised", "drawn")):
        ops.append("deformation")
    if any(k in text for k in ("raised", "sheet", "planished")) or object_class == "vessel":
        ops.append("sheetwork")
    if any(k in text for k in ("anneal", "hot", "warm")):
        ops.append("thermal")
    if object_class in {"knife", "sickle", "axe", "chisel", "dagger", "sword", "spearhead"}:
        ops.append("edge_treatment")
    if object_class in {"ring", "pin", "ornament", "bead"} or "wire" in text:
        ops.append("wirework")
    if any(k in text for k in ("rivet", "solder", "braz", "join", "seam", "clinched")):
        ops.extend(["joining", "assembly"])
    if any(k in text for k in ("surface", "tinned", "gild", "inlay", "decor")):
        ops.extend(["surface", "decoration"])
    if any(k in text for k in ("ground", "polish", "finish", "sharpen")):
        ops.append("finishing")
    if "repair" in text or "rework" in text:
        ops.extend(["repair", "reworking"])
    if recycle_fraction >= .42 or "recycl" in text or "remelt" in text:
        ops.extend(["recycling", "batching"])
    if object_class in {"axe", "spearhead", "fitting"} and "cast" in text:
        ops.append("structural_geometry")
    # preserve order, remove duplicates
    return list(dict.fromkeys(ops or ["batching"]))


def operation_relevance(profile: GuildProfile, operation: str, object_class: str) -> float:
    op = float(profile.operations.get(operation, 0.0))
    cls = float(profile.classes.get(object_class, 0.22))
    return op * (0.58 + 0.42 * cls)


def transform_affinities(
    affinities: Mapping[str, float],
    relation: str,
    heritage_strength: float,
    material_family: str,
    rng: np.random.Generator,
) -> Dict[str, float]:
    """Transform Bronze-workshop affinities into precursor/parallel/descendant shells."""
    out: Dict[str, float] = {}
    for guild_id, value in affinities.items():
        profile = GUILD_PROFILES[guild_id]
        persistence = math.exp(-max(0.0, 1.0 - heritage_strength) * 500.0 / profile.persistence_years)
        v = float(value) * float(heritage_strength) * persistence
        if relation == "pre_network_precursor":
            v *= .72
        elif relation == "coeval_parallel_craft":
            v *= .82
        elif relation == "post_network_descendant":
            v *= .76
        # Material transitions shift, rather than copy, craft competence.
        if material_family == "iron_steel":
            if guild_id in {"G-04", "G-05", "G-07", "G-12"}:
                v *= 1.22
            elif guild_id in {"G-01", "G-02", "G-10"}:
                v *= .58
        elif material_family in {"gold_precious", "silver_precious"}:
            if guild_id in {"G-03", "G-06", "G-08", "G-09", "G-10", "G-12"}:
                v *= 1.18
            elif guild_id == "G-11":
                v *= .62
        v *= float(rng.lognormal(0.0, .10))
        out[guild_id] = float(np.clip(v, 0.0, .97))
    return out


def build_event_biography(
    *,
    affinities: Mapping[str, float],
    sequence: Sequence[str],
    object_class: str,
    date_bc: int,
    relation: str,
    recycle_fraction: float,
    repair_count: int,
    rng: np.random.Generator,
) -> list[Dict[str, Any]]:
    operations = infer_operations(sequence, object_class, recycle_fraction)
    events: list[Dict[str, Any]] = []
    ordinal = 0
    for operation in operations:
        scored = []
        for guild_id, affinity in affinities.items():
            profile = GUILD_PROFILES[guild_id]
            relevance = operation_relevance(profile, operation, object_class)
            if relevance <= 0:
                continue
            strength = float(affinity) * relevance * float(rng.lognormal(0.0, .08))
            if strength >= .10:
                scored.append((guild_id, min(.99, strength)))
        scored.sort(key=lambda pair: pair[1], reverse=True)
        if not scored:
            continue
        ordinal += 1
        date_offset = 0 if operation not in {"repair", "reworking"} else -int(rng.integers(5, 85))
        influences = [
            {"guild_id": guild_id, "strength": round(float(strength), 4)}
            for guild_id, strength in scored[:3]
        ]
        events.append({
            "event_id": f"E-{ordinal:02d}",
            "operation": operation,
            "date_bc": int(date_bc + date_offset),
            "temporal_relation": relation,
            "guild_influences": influences,
        })

    # Repairs are episodic and can be performed by a different technical milieu.
    existing_repairs = sum(event["operation"] in {"repair", "reworking"} for event in events)
    for _ in range(max(0, repair_count - existing_repairs)):
        ordinal += 1
        candidates = []
        for guild_id in ("G-07", "G-06", "G-11", "G-12"):
            strength = affinities.get(guild_id, 0.0) * operation_relevance(GUILD_PROFILES[guild_id], "repair", object_class)
            strength *= float(rng.lognormal(0.0, .16))
            if strength > .08:
                candidates.append((guild_id, min(.99, strength)))
        candidates.sort(key=lambda x: x[1], reverse=True)
        events.append({
            "event_id": f"E-{ordinal:02d}",
            "operation": "repair",
            "date_bc": int(date_bc - int(rng.integers(8, 130))),
            "temporal_relation": relation,
            "guild_influences": [
                {"guild_id": guild_id, "strength": round(float(strength), 4)}
                for guild_id, strength in candidates[:3]
            ],
        })
    return events


def guild_vector_from_events(events: Sequence[Mapping[str, Any]]) -> Dict[str, float]:
    values = {guild_id: 0.0 for guild_id in GUILD_PROFILES}
    for event in events:
        for influence in event.get("guild_influences", []):
            guild_id = influence["guild_id"]
            strength = float(influence["strength"])
            values[guild_id] = max(values.get(guild_id, 0.0), strength)
    return values


def observability(events: Sequence[Mapping[str, Any]]) -> Dict[str, float]:
    channels: Dict[str, float] = {}
    for event in events:
        for influence in event.get("guild_influences", []):
            guild_id = influence["guild_id"]
            strength = float(influence["strength"])
            profile = GUILD_PROFILES[guild_id]
            for channel, sensitivity in profile.channels.items():
                evidence = strength * float(sensitivity)
                channels[channel] = max(channels.get(channel, 0.0), evidence)
    return {key: round(float(value), 4) for key, value in sorted(channels.items())}


def guild_overlap(a: Sequence[Mapping[str, Any]], b: Sequence[Mapping[str, Any]]) -> float:
    va = guild_vector_from_events(a)
    vb = guild_vector_from_events(b)
    aa = np.array([va[guild_id] for guild_id in GUILD_PROFILES], dtype=float)
    bb = np.array([vb[guild_id] for guild_id in GUILD_PROFILES], dtype=float)
    return _cosine(aa, bb)
