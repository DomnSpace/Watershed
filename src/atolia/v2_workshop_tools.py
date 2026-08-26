from __future__ import annotations

"""Physical workshop/tool ecology for Atolia v2.

The 12 guilds remain developer-facing communities of practice. Capability is
built from operator skill, tool geometry, support, thermal/material fit and
measurement/fixture control. There is no binary ``can_hammer`` switch.
"""

from dataclasses import dataclass, field
import hashlib
import math
from typing import Any, Dict, Mapping, Sequence

import numpy as np
import guild_model
import v2_config as cfg

@dataclass(frozen=True)
class ToolArchetype:
    family: str
    subtype: str
    mass_kg: float
    face_area_mm2: float
    face_radius_mm: float
    handle_length_mm: float
    precision_bias: float
    force_bias: float
    portability: float
    operation_weights: Mapping[str, float]

@dataclass
class ToolInstance:
    tool_id: str
    workshop_id: str
    family: str
    subtype: str
    lineage_depth: int
    mass_kg: float
    face_area_mm2: float
    face_radius_mm: float
    handle_length_mm: float
    precision_bias: float
    force_bias: float
    portability: float
    wear: float
    repair_count: int
    nickname: str = ""

@dataclass
class WorkshopEcology:
    workshop_id: str
    node_id: str
    start_bc: int
    end_bc: int
    workers: int
    guild_affinities: Dict[str, float]
    tools: list[ToolInstance] = field(default_factory=list)
    tool_capabilities: Dict[str, float] = field(default_factory=dict)
    quality_memory: float = 0.5
    recent_volume: float = 0.0

TOOL_ARCHETYPES = (
    ToolArchetype("hammer", "heavy_forging", 2.40, 520, 70, 390, .34, .95, .38, {"deformation": .90, "edge_treatment": .62, "repair": .48}),
    ToolArchetype("hammer", "medium_forging", 1.05, 310, 48, 340, .50, .72, .58, {"deformation": .82, "edge_treatment": .72, "repair": .58}),
    ToolArchetype("hammer", "small_forging", .48, 150, 28, 275, .67, .48, .76, {"deformation": .68, "wirework": .48, "repair": .62}),
    ToolArchetype("hammer", "planishing", .36, 190, 85, 245, .82, .34, .78, {"sheetwork": 1.0, "finishing": .72, "surface": .42}),
    ToolArchetype("hammer", "raising", .42, 118, 34, 255, .78, .42, .76, {"sheetwork": 1.0, "deformation": .72}),
    ToolArchetype("hammer", "cross_peen", .62, 96, 18, 300, .69, .62, .68, {"deformation": .82, "edge_treatment": .78, "wirework": .44}),
    ToolArchetype("hammer", "round_finish", .23, 72, 16, 220, .92, .22, .88, {"finishing": 1.0, "wirework": .72, "decoration": .42}),
    ToolArchetype("hammer", "fine_precious", .16, 38, 8, 185, .98, .14, .92, {"wirework": .92, "finishing": 1.0, "decoration": .78}),
    ToolArchetype("hammer", "riveting", .31, 64, 12, 230, .86, .30, .86, {"joining": 1.0, "assembly": .82, "repair": .58}),
    ToolArchetype("support", "flat_anvil", 18.0, 4200, 1000, 0, .72, .94, .08, {"deformation": .92, "edge_treatment": .82, "repair": .74}),
    ToolArchetype("support", "raising_stake", 5.2, 850, 38, 0, .90, .66, .22, {"sheetwork": 1.0, "finishing": .58}),
    ToolArchetype("support", "ring_mandrel", 2.2, 380, 16, 0, .94, .45, .40, {"wirework": 1.0, "finishing": .62}),
    ToolArchetype("punch", "medium_punch", .18, 24, 2.5, 145, .88, .50, .95, {"joining": .72, "decoration": .60, "wirework": .38}),
    ToolArchetype("punch", "fine_punch", .07, 8, 1.0, 120, .97, .22, .98, {"decoration": 1.0, "wirework": .62, "joining": .35}),
    ToolArchetype("abrasive", "fine_stone", .32, 600, 1000, 0, .94, .08, .92, {"finishing": 1.0, "edge_treatment": .72, "surface": .72}),
    ToolArchetype("measurement", "balance_weights", .90, 0, 0, 0, .94, 0, .72, {"batching": .90, "refining": .62, "wirework": .48}),
    ToolArchetype("thermal", "small_crucible", 1.1, 0, 0, 0, .78, 0, .55, {"casting": .68, "batching": .84, "refining": .62}),
    ToolArchetype("thermal", "large_crucible", 5.5, 0, 0, 0, .52, 0, .18, {"casting": .92, "batching": .72, "recycling": .84}),
)

def _seed64(*parts: object) -> int:
    raw = "|".join(str(p) for p in parts).encode("utf-8")
    return int.from_bytes(hashlib.sha256(raw).digest()[:8], "big")

def generalized_mean(values: Sequence[float], p: float, weights: Sequence[float] | None = None) -> float:
    x = np.asarray(values, dtype=float)
    if x.size == 0:
        return 0.0
    x = np.clip(x, 1e-12, None)
    if weights is None:
        w = np.full(x.size, 1.0 / x.size)
    else:
        w = np.asarray(weights, dtype=float)
        w = np.clip(w, 0.0, None)
        if w.sum() <= 0:
            w[:] = 1.0
        w /= w.sum()
    if abs(p) < 1e-12:
        return float(np.exp(np.sum(w * np.log(x))))
    return float(np.sum(w * np.power(x, p)) ** (1.0 / p))

def weak_link_capability(components: Sequence[float], weights: Sequence[float] | None = None) -> float:
    return generalized_mean(components, -1.0, weights)

def _archetype_relevance(archetype: ToolArchetype, affinities: Mapping[str, float]) -> float:
    score = norm = 0.0
    for gid, affinity in affinities.items():
        profile = guild_model.GUILD_PROFILES[gid]
        a = max(0.0, float(affinity))
        for op, weight in archetype.operation_weights.items():
            score += a * float(profile.operations.get(op, 0.0)) * float(weight)
            norm += a * float(weight)
    return 0.0 if norm <= 0 else score / norm

def _nickname(archetype: ToolArchetype, depth: int, affinities: Mapping[str, float], rng: np.random.Generator) -> str:
    if archetype.subtype == "fine_precious" and depth >= 8:
        stem = "Goldringfinehammer"
    elif archetype.subtype == "heavy_forging" and rng.random() < .10:
        stem = "Hufschmiedhammer"
    else:
        stems = {"planishing":"Planishhammer","raising":"Raisinghammer","cross_peen":"Peenhammer","round_finish":"Finehammer","riveting":"Rivethammer","flat_anvil":"Flatanvil","raising_stake":"Sheetstake","ring_mandrel":"Ringmandrel","medium_punch":"Punch","fine_punch":"Finepunch","fine_stone":"Polishstone","balance_weights":"Balancekit","small_crucible":"Smallcrucible","large_crucible":"Largecrucible"}
        stem = stems.get(archetype.subtype, archetype.subtype.replace("_", "-"))
    return f"{stem} v{max(1, int(depth))}"

def _install_v2_workshop_spans(world: Any, world_seed: int) -> None:
    """Spread inherited v1 workshop cohorts across the full 2000--1000 BCE v2 horizon.

    The v1 generator hard-clamped workshop starts to 1800 BCE.  V2 needs active
    practitioners during its 2000--1800 prelude as well.  Preserve each workshop's
    existing duration scale and all node/technical/capacity properties, but place
    its cohort deterministically across the full millennium.
    """
    start_bc = int(cfg.DEFAULT_CONFIG.world_start_bc)
    end_bc = int(cfg.DEFAULT_CONFIG.world_end_bc)
    span = max(100, start_bc - end_bc)
    for workshop in world.workshops:
        rng = np.random.default_rng(_seed64(world_seed, workshop.id, "v2-workshop-span"))
        old_duration = max(35, int(workshop.start_bc) - int(workshop.end_bc))
        duration = int(np.clip(old_duration * np.exp(rng.normal(0.0, .10)), 35, 340))
        margin = max(20, min(80, duration // 3))
        low = end_bc + margin
        high = start_bc - margin
        midpoint = int(rng.integers(low, high + 1)) if high > low else (start_bc + end_bc) // 2
        workshop.start_bc = min(start_bc, midpoint + duration // 2)
        workshop.end_bc = max(end_bc, midpoint - duration // 2)


def seed_workshop_ecology(world: Any, workshop: Any, world_seed: int) -> WorkshopEcology:
    affinities = guild_model.workshop_affinities(world, workshop)
    rng = np.random.default_rng(_seed64(world_seed, workshop.id, "v2-tools"))
    years = max(25, int(workshop.start_bc) - int(workshop.end_bc))
    tools: list[ToolInstance] = []
    cap_sum: Dict[str, float] = {}
    cap_n: Dict[str, int] = {}
    for idx, a in enumerate(TOOL_ARCHETYPES):
        relevance = _archetype_relevance(a, affinities)
        floor = .70 if a.subtype in {"medium_forging", "flat_anvil", "fine_stone", "small_crucible"} else .10
        p_have = np.clip(floor + .55 * relevance + .04 * math.log1p(max(1, workshop.workers)), .04, .995)
        if rng.random() > p_have:
            continue
        expected_depth = 1.0 + relevance * (years / 18.0) * (.45 + .55 * min(1.0, workshop.capacity_weight))
        depth = max(1, int(rng.poisson(max(.2, expected_depth))))
        jitter = lambda scale: float(np.exp(rng.normal(0.0, scale)))
        wear = float(np.clip(rng.beta(1.6, 5.0) * (1.1 - .45 * min(1.0, .25 + .75 * relevance)), 0.0, .95))
        precision = float(np.clip(a.precision_bias * jitter(.08) * (1.0 + .006 * min(depth, 30)), .02, 1.5))
        force = float(np.clip(a.force_bias * jitter(.07), 0.0, 1.5))
        tool = ToolInstance(f"{workshop.id}:T{idx:02d}", str(workshop.id), a.family, a.subtype, depth, float(a.mass_kg*jitter(.09)), float(a.face_area_mm2*jitter(.08)) if a.face_area_mm2 else 0.0, float(a.face_radius_mm*jitter(.08)) if a.face_radius_mm else 0.0, float(a.handle_length_mm*jitter(.07)) if a.handle_length_mm else 0.0, precision, force, float(np.clip(a.portability*jitter(.06),.01,1.0)), wear, int(rng.poisson(.35+wear*2.2)))
        tool.nickname = _nickname(a, depth, affinities, rng)
        tools.append(tool)
        effective = max(.02, (1.0-.55*wear) * (.55*precision + .45*max(.05,force)))
        for op, weight in a.operation_weights.items():
            cap_sum[op] = cap_sum.get(op,0.0) + effective*float(weight)
            cap_n[op] = cap_n.get(op,0) + 1
    return WorkshopEcology(str(workshop.id), str(workshop.node_id), int(workshop.start_bc), int(workshop.end_bc), int(workshop.workers), {k:float(v) for k,v in affinities.items()}, tools, {op:cap_sum[op]/max(1,cap_n[op]) for op in cap_sum}, float(np.clip(.38+.42*np.mean(list(affinities.values()))+rng.normal(0,.07),.05,.95)), float(max(0.0,workshop.capacity_weight)))

def seed_all_workshop_ecologies(world: Any, world_seed: int) -> list[WorkshopEcology]:
    _install_v2_workshop_spans(world, world_seed)
    return [seed_workshop_ecology(world, w, world_seed) for w in world.workshops]

def operation_capability(ecology: WorkshopEcology, operation: str, *, operator_skill: float, material_fit: float, support_fit: float=1.0, thermal_fit: float=1.0, measurement_fit: float=1.0) -> float:
    tool_fit = float(ecology.tool_capabilities.get(operation, .02))
    components = (max(.01,operator_skill), max(.01,tool_fit), max(.01,material_fit), max(.01,support_fit), max(.01,thermal_fit), max(.01,measurement_fit))
    return float(np.clip(weak_link_capability(components), 0.0, 1.5))
