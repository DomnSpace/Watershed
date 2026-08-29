from __future__ import annotations

"""Atolia v3 phase-04 workshop, guild, tool and operation truth.

Phase 04 is strictly downstream of the proven phase-01 propagation, phase-02
metal genealogy and phase-03 chemistry.  It does not change any of those rows.

The model deliberately distinguishes three cases:

* a phase-02 event has a known node and an active workshop physically registered
  at that node -> phase 04 may assign one of those workshops deterministically;
* a known node has no active registered workshop -> the operation remains
  unassigned rather than borrowing a random workshop from elsewhere;
* a phase-02 event lies in the route interior and therefore has ``node_id=None``
  -> phase 04 preserves that ignorance and never fabricates a route node.

The workshop/tool ecology reuses the v2 Step-4.9 machinery, but it calls
``seed_workshop_ecology`` directly.  It intentionally does NOT call
``seed_all_workshop_ecologies`` because that helper rewrites workshop date spans
for the abandoned v2 2000--1000 BCE world.

Person agents are not yet instantiated in v3.  Operator skill is therefore a
workshop/guild-tradition projection and is explicitly labelled as such.
"""

from dataclasses import dataclass
import hashlib
import json
import math
from typing import Any, Mapping, Sequence

import guild_model
import v2_workshop_tools as workshop_tools
import v3_metal_biography as biography
import v3_source_metallurgy as metallurgy


WORKSHOP_MODEL_VERSION = "atolia-v3-workshop-guild-tools-v1"
WORKSHOP_ASSIGNMENT_POLICY = "known-node-active-workshop-only-v1"
OPERATOR_MODEL_STATUS = "workshop-guild-projection-no-person-agent"
MATERIAL_FIT_STATUS = "neutral-placeholder-pending-process-calibration"
MAX_TOOLS_PER_OPERATION = 4

SUPPORT_REQUIRED = {
    "deformation", "sheetwork", "edge_treatment", "wirework", "joining",
    "assembly", "repair", "reworking", "finishing", "decoration", "surface",
}
THERMAL_REQUIRED = {
    "casting", "moulding", "lost_wax", "thermal", "recycling", "batching",
    "refining",
}
MEASUREMENT_RELEVANT = {
    "batching", "refining", "wirework", "joining", "assembly", "finishing",
    "decoration", "structural_geometry",
}


@dataclass(frozen=True)
class OperationEpisode:
    operation_id: str
    particle_id: str
    phase02_event_id: str | None
    event_kind: str
    object_episode_id: str
    batch_id: str
    object_class: str
    operation_type: str
    route_position_km: float
    node_id: str | None
    workshop_id: str | None
    assignment_basis: str
    primary_guild_id: str | None
    primary_guild_affinity: float
    tool_set_id: str | None
    tool_ids: tuple[str, ...]
    capability: float | None
    operator_skill: float | None
    tool_fit: float | None
    support_fit: float | None
    thermal_fit: float | None
    measurement_fit: float | None
    material_fit: float | None
    represented_weight: float
    workpiece_mass_kg: float


@dataclass(frozen=True)
class WorkshopLayer:
    workshop_rows: tuple[Mapping[str, Any], ...]
    guild_rows: tuple[Mapping[str, Any], ...]
    membership_rows: tuple[Mapping[str, Any], ...]
    archetype_rows: tuple[Mapping[str, Any], ...]
    archetype_operation_rows: tuple[Mapping[str, Any], ...]
    tool_rows: tuple[Mapping[str, Any], ...]
    operations: tuple[OperationEpisode, ...]


class _GuildDistanceView:
    """Adapter for the old helper's ``_shortest_distance`` name."""

    def __init__(self, world: Any):
        self._world = world

    def __getattr__(self, name: str) -> Any:
        return getattr(self._world, name)

    def _shortest_distance(self, start: str, goal: str) -> float:
        if hasattr(self._world, "_shortest_distance"):
            return float(self._world._shortest_distance(start, goal))
        if hasattr(self._world, "_network_distance"):
            return float(self._world._network_distance(start, goal))
        return 9999.0


def _stable_id(prefix: str, *parts: object) -> str:
    raw = "|".join(str(part) for part in parts).encode("utf-8")
    return f"{prefix}_{hashlib.sha256(raw).hexdigest()[:20]}"


def _stable_u01(*parts: object) -> float:
    raw = "|".join(str(part) for part in parts).encode("utf-8")
    x = int.from_bytes(hashlib.sha256(raw).digest()[:8], "big")
    return (x + 0.5) / 2**64


def _weighted_choice(rows: Sequence[Any], weights: Sequence[float], *seed: object) -> Any:
    if not rows:
        raise ValueError("weighted choice requires rows")
    clean = [max(0.0, float(w)) for w in weights]
    total = sum(clean)
    if total <= 0.0:
        return rows[0]
    target = _stable_u01(WORKSHOP_MODEL_VERSION, *seed) * total
    running = 0.0
    for row, weight in zip(rows, clean):
        running += weight
        if target <= running:
            return row
    return rows[-1]


def _archetype_index() -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
    dict[str, tuple[int, workshop_tools.ToolArchetype]],
]:
    archetypes: list[dict[str, Any]] = []
    operations: list[dict[str, Any]] = []
    by_subtype: dict[str, tuple[int, workshop_tools.ToolArchetype]] = {}
    for index, archetype in enumerate(workshop_tools.TOOL_ARCHETYPES):
        archetypes.append({
            "archetype_index": index,
            "family": archetype.family,
            "subtype": archetype.subtype,
            "mass_kg": float(archetype.mass_kg),
            "face_area_mm2": float(archetype.face_area_mm2),
            "face_radius_mm": float(archetype.face_radius_mm),
            "handle_length_mm": float(archetype.handle_length_mm),
            "precision_bias": float(archetype.precision_bias),
            "force_bias": float(archetype.force_bias),
            "portability": float(archetype.portability),
        })
        by_subtype[archetype.subtype] = (index, archetype)
        for operation, weight in sorted(archetype.operation_weights.items()):
            operations.append({
                "archetype_operation_index": len(operations),
                "archetype_index": index,
                "operation_type": str(operation),
                "weight": float(weight),
            })
    return archetypes, operations, by_subtype


def _seed_ecologies(world: Any, world_seed: int) -> dict[str, workshop_tools.WorkshopEcology]:
    """Seed Step-4.9 ecology without mutating the v1 workshop chronology."""
    before = {
        str(w.id): (int(w.start_bc), int(w.end_bc), str(w.node_id))
        for w in world.workshops
    }
    view = _GuildDistanceView(world)
    out = {
        str(w.id): workshop_tools.seed_workshop_ecology(view, w, int(world_seed))
        for w in world.workshops
    }
    after = {
        str(w.id): (int(w.start_bc), int(w.end_bc), str(w.node_id))
        for w in world.workshops
    }
    if before != after:
        raise RuntimeError("phase-04 workshop seeding mutated the frozen v1 workshop chronology")
    return out


def _guild_rows(world: Any) -> tuple[list[dict[str, Any]], dict[str, int]]:
    rows: list[dict[str, Any]] = []
    index: dict[str, int] = {}
    for guild_id, profile in guild_model.GUILD_PROFILES.items():
        world_guild = getattr(world, "guilds", {}).get(guild_id, {})
        i = len(rows)
        index[guild_id] = i
        rows.append({
            "guild_index": i,
            "guild_id": guild_id,
            "developer_name": profile.developer_name,
            "anchor_node": str(world_guild.get("anchor_node", "")),
            "world_mobility_scale": float(world_guild.get("mobility_scale", profile.mobility_scale)),
            "profile_mobility_scale": float(profile.mobility_scale),
            "convergence_prior": float(profile.convergence_prior),
            "status_bias": float(profile.status_bias),
            "persistence_years": float(profile.persistence_years),
            "technical_prototype_json": json.dumps(
                [float(x) for x in world_guild.get("prototype", ())],
                separators=(",", ":"),
            ),
            "operations_json": json.dumps(dict(profile.operations), sort_keys=True, separators=(",", ":")),
            "classes_json": json.dumps(dict(profile.classes), sort_keys=True, separators=(",", ":")),
            "channels_json": json.dumps(dict(profile.channels), sort_keys=True, separators=(",", ":")),
        })
    return rows, index


def _tool_effective(tool: workshop_tools.ToolInstance) -> float:
    return max(
        0.01,
        (1.0 - 0.55 * float(tool.wear))
        * (0.55 * float(tool.precision_bias) + 0.45 * max(0.05, float(tool.force_bias))),
    )


def _family_fit(ecology: workshop_tools.WorkshopEcology, family: str) -> float:
    values = [_tool_effective(tool) for tool in ecology.tools if tool.family == family]
    return max(values) if values else 0.02


def _operator_skill(
    ecology: workshop_tools.WorkshopEcology,
    operation: str,
    object_class: str,
) -> float:
    numerator = 0.0
    denominator = 0.0
    for guild_id, affinity in ecology.guild_affinities.items():
        if guild_id not in guild_model.GUILD_PROFILES:
            continue
        a = max(0.0, float(affinity))
        if a <= 0.0:
            continue
        numerator += a * guild_model.operation_relevance(
            guild_model.GUILD_PROFILES[guild_id],
            operation,
            object_class,
        )
        denominator += a
    return max(0.02, numerator / denominator) if denominator > 0.0 else 0.02


def _primary_guild(ecology: workshop_tools.WorkshopEcology) -> tuple[str | None, float]:
    if not ecology.guild_affinities:
        return None, 0.0
    guild_id, affinity = max(ecology.guild_affinities.items(), key=lambda item: item[1])
    return str(guild_id), float(affinity)


def _operation_tokens(event_kind: str, object_class: str) -> tuple[list[str], float]:
    if event_kind == "repair":
        tokens = ["repair", "rework", "finish"]
        if object_class in {"vessel", "fitting", "sword", "dagger", "spearhead"}:
            tokens.append("join")
        return tokens, 0.0
    if event_kind == "remelt":
        return ["recycl", "remelt", "batch", "cast", "mould", "finish"], 1.0

    if object_class == "vessel":
        return ["cast", "raised", "anneal", "rivet", "finish"], 0.0
    if object_class in {"ring", "pin", "bead", "ornament"}:
        return ["cast", "wire", "anneal", "decor", "finish"], 0.0
    if object_class == "figurine":
        return ["wax", "cast", "mould", "decor", "finish"], 0.0
    if object_class in {"axe", "spearhead", "dagger", "sword", "chisel", "knife", "sickle"}:
        return ["cast", "mould", "hammer", "anneal", "sharpen", "finish"], 0.0
    if object_class in {"fitting"}:
        return ["cast", "mould", "rivet", "finish"], 0.0
    if object_class == "scrap":
        return ["recycl", "batch"], 1.0
    if object_class == "ingot":
        return ["batch", "cast", "mould"], 0.0
    return ["cast", "finish"], 0.0


def operations_for_event(event_kind: str, object_class: str) -> list[str]:
    tokens, recycle_fraction = _operation_tokens(event_kind, object_class)
    operations = guild_model.infer_operations(
        tokens,
        object_class,
        recycle_fraction=recycle_fraction,
    )
    if event_kind == "remelt":
        for required in ("recycling", "batching", "casting"):
            if required not in operations:
                operations.append(required)
    if event_kind == "repair" and "repair" not in operations:
        operations.insert(0, "repair")
    return operations


def _active_local_ecology(
    world: Any,
    ecologies: Mapping[str, workshop_tools.WorkshopEcology],
    node_id: str | None,
    date_bc: int,
    object_class: str,
    operation_hint: str,
    *seed: object,
) -> tuple[workshop_tools.WorkshopEcology | None, str]:
    if node_id is None:
        return None, "unlocalized_phase02_route_interior"
    indices = list(getattr(world, "workshops_by_node", {}).get(node_id, ()))
    candidates = []
    weights = []
    for index in indices:
        workshop = world.workshops[int(index)]
        if not (int(workshop.end_bc) <= int(date_bc) <= int(workshop.start_bc)):
            continue
        ecology = ecologies.get(str(workshop.id))
        if ecology is None:
            continue
        skill = _operator_skill(ecology, operation_hint, object_class)
        candidates.append(ecology)
        weights.append(max(1e-9, float(workshop.capacity_weight)) * (0.20 + skill))
    if not candidates:
        return None, "known_node_no_active_registered_workshop"
    return (
        _weighted_choice(candidates, weights, node_id, date_bc, object_class, operation_hint, *seed),
        "same_node_active_workshop",
    )


def _select_tools(
    ecology: workshop_tools.WorkshopEcology,
    operation: str,
    archetype_by_subtype: Mapping[str, tuple[int, workshop_tools.ToolArchetype]],
) -> tuple[str, ...]:
    scored: list[tuple[float, str]] = []
    for tool in ecology.tools:
        pair = archetype_by_subtype.get(tool.subtype)
        if pair is None:
            continue
        _, archetype = pair
        relevance = float(archetype.operation_weights.get(operation, 0.0))
        if relevance <= 0.0:
            continue
        score = relevance * _tool_effective(tool)
        scored.append((score, str(tool.tool_id)))
    scored.sort(key=lambda item: (-item[0], item[1]))
    return tuple(tool_id for _, tool_id in scored[:MAX_TOOLS_PER_OPERATION])


def _operation_capability(
    ecology: workshop_tools.WorkshopEcology,
    operation: str,
    object_class: str,
) -> tuple[float, float, float, float, float, float, float]:
    operator = _operator_skill(ecology, operation, object_class)
    tool_fit = float(ecology.tool_capabilities.get(operation, 0.02))
    support = _family_fit(ecology, "support") if operation in SUPPORT_REQUIRED else 1.0
    thermal = _family_fit(ecology, "thermal") if operation in THERMAL_REQUIRED else 1.0
    measurement = _family_fit(ecology, "measurement") if operation in MEASUREMENT_RELEVANT else 1.0
    material = 1.0
    capability = workshop_tools.operation_capability(
        ecology,
        operation,
        operator_skill=operator,
        material_fit=material,
        support_fit=support,
        thermal_fit=thermal,
        measurement_fit=measurement,
    )
    return capability, operator, tool_fit, support, thermal, measurement, material


def _event_batch_and_episode(
    lineage: biography.MetalLineage,
    event: biography.BiographyEvent,
) -> tuple[str, str]:
    if event.kind == "remelt" and event.output_batch_id is not None:
        target_batch = event.output_batch_id
        for episode in lineage.episodes:
            if episode.batch_id == target_batch:
                return target_batch, episode.episode_id
        raise ValueError("remelt output batch has no phase-02 object episode")
    if not event.input_batch_ids:
        raise ValueError("phase-02 operation event has no input batch")
    return event.input_batch_ids[0], event.object_episode_id


def materialize_workshop_layer(
    world: Any,
    lineages: Sequence[biography.MetalLineage],
    chemistry: Sequence[metallurgy.MetallurgyLineage],
    *,
    world_seed: int,
) -> WorkshopLayer:
    if len(lineages) != len(chemistry):
        raise ValueError("phase-02 and phase-03 lineage counts differ")

    chemistry_by_particle = {row.particle_id: row for row in chemistry}
    ecologies = _seed_ecologies(world, int(world_seed))
    archetype_rows, archetype_operation_rows, archetype_by_subtype = _archetype_index()
    guild_rows, guild_index = _guild_rows(world)

    workshop_rows: list[dict[str, Any]] = []
    membership_rows: list[dict[str, Any]] = []
    tool_rows: list[dict[str, Any]] = []

    for workshop in world.workshops:
        wid = str(workshop.id)
        ecology = ecologies[wid]
        wi = len(workshop_rows)
        primary = getattr(world, "workshop_guild", {}).get(wid)
        primary_strength = float(getattr(world, "guild_strength", {}).get(wid, 0.0))
        workshop_rows.append({
            "workshop_index": wi,
            "workshop_id": wid,
            "node_id": str(workshop.node_id),
            "start_bc": int(workshop.start_bc),
            "end_bc": int(workshop.end_bc),
            "workers": int(workshop.workers),
            "lineage_id": str(workshop.lineage_id),
            "capacity_weight": float(workshop.capacity_weight),
            "quality_memory": float(ecology.quality_memory),
            "tool_count": len(ecology.tools),
            "primary_guild_id": None if primary is None else str(primary),
            "primary_guild_strength": primary_strength,
        })
        for guild_id, affinity in sorted(ecology.guild_affinities.items()):
            if guild_id not in guild_index:
                continue
            membership_rows.append({
                "membership_index": len(membership_rows),
                "workshop_index": wi,
                "guild_index": guild_index[guild_id],
                "guild_id": str(guild_id),
                "affinity": float(affinity),
                "primary": bool(primary == guild_id),
            })
        for tool in ecology.tools:
            ti = len(tool_rows)
            pair = archetype_by_subtype.get(tool.subtype)
            archetype_index_value = -1 if pair is None else int(pair[0])
            tool_rows.append({
                "tool_index": ti,
                "tool_id": str(tool.tool_id),
                "workshop_index": wi,
                "workshop_id": wid,
                "archetype_index": archetype_index_value,
                "family": str(tool.family),
                "subtype": str(tool.subtype),
                "lineage_depth": int(tool.lineage_depth),
                "mass_kg": float(tool.mass_kg),
                "face_area_mm2": float(tool.face_area_mm2),
                "face_radius_mm": float(tool.face_radius_mm),
                "handle_length_mm": float(tool.handle_length_mm),
                "precision_bias": float(tool.precision_bias),
                "force_bias": float(tool.force_bias),
                "portability": float(tool.portability),
                "wear": float(tool.wear),
                "repair_count": int(tool.repair_count),
                "nickname": str(tool.nickname),
            })

    operations: list[OperationEpisode] = []
    for lineage in lineages:
        chem_lineage = chemistry_by_particle.get(lineage.particle_id)
        if chem_lineage is None:
            raise ValueError("phase-03 chemistry missing phase-02 particle")
        phase3_batch_ids = {batch.batch_id for batch in chem_lineage.batches}
        if any(batch.batch_id not in phase3_batch_ids for batch in lineage.batches):
            raise ValueError("phase-04 cannot link all phase-02 batches to phase-03 chemistry")

        initial = lineage.episodes[0]
        event_specs: list[tuple[str | None, str, str, str, float, str | None, int]] = [
            (
                None,
                "manufacture",
                initial.batch_id,
                initial.episode_id,
                float(initial.start_position_km),
                initial.start_node_id,
                0,
            )
        ]
        for event in lineage.events:
            if event.kind not in {"repair", "remelt"}:
                continue
            batch_id, episode_id = _event_batch_and_episode(lineage, event)
            event_specs.append((
                event.event_id,
                event.kind,
                batch_id,
                episode_id,
                float(event.route_position_km),
                event.node_id,
                int(event.ordinal) + 1,
            ))

        for phase02_event_id, event_kind, batch_id, episode_id, position, node_id, event_ordinal in event_specs:
            op_types = operations_for_event(event_kind, lineage.object_class)
            hint = op_types[0] if op_types else "batching"
            ecology, assignment_basis = _active_local_ecology(
                world,
                ecologies,
                node_id,
                lineage.date_bc,
                lineage.object_class,
                hint,
                lineage.particle_id,
                event_ordinal,
            )
            primary_guild_id: str | None = None
            primary_guild_affinity = 0.0
            if ecology is not None:
                primary_guild_id, primary_guild_affinity = _primary_guild(ecology)

            phase2_batch = next(batch for batch in lineage.batches if batch.batch_id == batch_id)
            for local_ordinal, operation_type in enumerate(op_types):
                tool_ids: tuple[str, ...] = ()
                capability = operator = tool_fit = support = thermal = measurement = material = None
                if ecology is not None:
                    tool_ids = _select_tools(ecology, operation_type, archetype_by_subtype)
                    (
                        capability,
                        operator,
                        tool_fit,
                        support,
                        thermal,
                        measurement,
                        material,
                    ) = _operation_capability(ecology, operation_type, lineage.object_class)

                tool_set_id = (
                    None
                    if not tool_ids
                    else _stable_id(
                        "ts",
                        ecology.workshop_id if ecology is not None else "",
                        operation_type,
                        *tool_ids,
                    )
                )
                operation_id = _stable_id(
                    "op",
                    WORKSHOP_MODEL_VERSION,
                    lineage.particle_id,
                    phase02_event_id or "initial-manufacture",
                    event_ordinal,
                    local_ordinal,
                    operation_type,
                )
                operations.append(OperationEpisode(
                    operation_id=operation_id,
                    particle_id=lineage.particle_id,
                    phase02_event_id=phase02_event_id,
                    event_kind=event_kind,
                    object_episode_id=episode_id,
                    batch_id=batch_id,
                    object_class=lineage.object_class,
                    operation_type=operation_type,
                    route_position_km=float(position),
                    node_id=node_id,
                    workshop_id=None if ecology is None else str(ecology.workshop_id),
                    assignment_basis=assignment_basis,
                    primary_guild_id=primary_guild_id,
                    primary_guild_affinity=float(primary_guild_affinity),
                    tool_set_id=tool_set_id,
                    tool_ids=tool_ids,
                    capability=capability,
                    operator_skill=operator,
                    tool_fit=tool_fit,
                    support_fit=support,
                    thermal_fit=thermal,
                    measurement_fit=measurement,
                    material_fit=material,
                    represented_weight=float(lineage.represented_weight),
                    workpiece_mass_kg=float(phase2_batch.metal_mass_kg),
                ))

    layer = WorkshopLayer(
        workshop_rows=tuple(workshop_rows),
        guild_rows=tuple(guild_rows),
        membership_rows=tuple(membership_rows),
        archetype_rows=tuple(archetype_rows),
        archetype_operation_rows=tuple(archetype_operation_rows),
        tool_rows=tuple(tool_rows),
        operations=tuple(operations),
    )
    validate_workshop_layer(layer)
    return layer


def validate_workshop_layer(layer: WorkshopLayer) -> None:
    workshop_ids = {str(row["workshop_id"]) for row in layer.workshop_rows}
    tool_ids = {str(row["tool_id"]) for row in layer.tool_rows}
    if len(workshop_ids) != len(layer.workshop_rows):
        raise ValueError("duplicate phase-04 workshop id")
    if len(tool_ids) != len(layer.tool_rows):
        raise ValueError("duplicate phase-04 tool id")

    seen_ops: set[str] = set()
    for operation in layer.operations:
        if operation.operation_id in seen_ops:
            raise ValueError("duplicate operation id")
        seen_ops.add(operation.operation_id)
        if operation.represented_weight <= 0.0:
            raise ValueError("operation represented weight must be positive")
        if operation.workpiece_mass_kg <= 0.0:
            raise ValueError("operation workpiece mass must be positive")
        if operation.node_id is None:
            if operation.workshop_id is not None:
                raise ValueError("unlocalized phase-02 event acquired a fabricated workshop")
            if operation.assignment_basis != "unlocalized_phase02_route_interior":
                raise ValueError("unlocalized phase-02 event has wrong assignment basis")
        if operation.workshop_id is None:
            if operation.tool_ids or operation.tool_set_id is not None:
                raise ValueError("unassigned operation acquired tools")
            if operation.capability is not None:
                raise ValueError("unassigned operation acquired a capability")
        else:
            if operation.workshop_id not in workshop_ids:
                raise ValueError("operation points to unknown workshop")
            if any(tool_id not in tool_ids for tool_id in operation.tool_ids):
                raise ValueError("operation points to unknown tool")
            if operation.capability is None or not math.isfinite(operation.capability):
                raise ValueError("localized operation lacks finite capability")
            if operation.capability < 0.0 or operation.capability > 1.5 + 1e-12:
                raise ValueError("operation capability outside Step-4.9 envelope")


def flatten_workshop_layer(layer: WorkshopLayer) -> dict[str, list[dict[str, Any]]]:
    workshop_index = {str(row["workshop_id"]): int(row["workshop_index"]) for row in layer.workshop_rows}
    tool_index = {str(row["tool_id"]): int(row["tool_index"]) for row in layer.tool_rows}

    operations: list[dict[str, Any]] = []
    operation_tools: list[dict[str, Any]] = []
    tool_use: dict[int, dict[str, Any]] = {
        int(row["tool_index"]): {
            "tool_use_index": int(row["tool_index"]),
            "tool_index": int(row["tool_index"]),
            "tool_id": str(row["tool_id"]),
            "localized_operation_count": 0,
            "represented_operation_weight": 0.0,
            "represented_mass_kg": 0.0,
        }
        for row in layer.tool_rows
    }

    archetype_by_subtype = {
        str(row["subtype"]): int(row["archetype_index"]) for row in layer.archetype_rows
    }
    archetype_weights = {
        (int(row["archetype_index"]), str(row["operation_type"])): float(row["weight"])
        for row in layer.archetype_operation_rows
    }

    for operation_index, operation in enumerate(layer.operations):
        wi = -1 if operation.workshop_id is None else workshop_index[operation.workshop_id]
        operations.append({
            "operation_index": operation_index,
            "operation_id": operation.operation_id,
            "particle_id": operation.particle_id,
            "phase02_event_id": operation.phase02_event_id,
            "event_kind": operation.event_kind,
            "object_episode_id": operation.object_episode_id,
            "batch_id": operation.batch_id,
            "object_class": operation.object_class,
            "operation_type": operation.operation_type,
            "route_position_km": float(operation.route_position_km),
            "node_id": operation.node_id,
            "workshop_index": wi,
            "workshop_id": operation.workshop_id,
            "assignment_basis": operation.assignment_basis,
            "primary_guild_id": operation.primary_guild_id,
            "primary_guild_affinity": float(operation.primary_guild_affinity),
            "tool_set_id": operation.tool_set_id,
            "capability": -1.0 if operation.capability is None else float(operation.capability),
            "operator_skill": -1.0 if operation.operator_skill is None else float(operation.operator_skill),
            "tool_fit": -1.0 if operation.tool_fit is None else float(operation.tool_fit),
            "support_fit": -1.0 if operation.support_fit is None else float(operation.support_fit),
            "thermal_fit": -1.0 if operation.thermal_fit is None else float(operation.thermal_fit),
            "measurement_fit": -1.0 if operation.measurement_fit is None else float(operation.measurement_fit),
            "material_fit": -1.0 if operation.material_fit is None else float(operation.material_fit),
            "represented_weight": float(operation.represented_weight),
            "workpiece_mass_kg": float(operation.workpiece_mass_kg),
            "localized": bool(operation.workshop_id is not None),
        })
        for rank, tool_id in enumerate(operation.tool_ids):
            ti = tool_index[tool_id]
            tool_row = layer.tool_rows[ti]
            ai = archetype_by_subtype.get(str(tool_row["subtype"]), -1)
            score = (
                archetype_weights.get((ai, operation.operation_type), 0.0)
                * max(
                    0.01,
                    (1.0 - 0.55 * float(tool_row["wear"]))
                    * (
                        0.55 * float(tool_row["precision_bias"])
                        + 0.45 * max(0.05, float(tool_row["force_bias"]))
                    ),
                )
            )
            operation_tools.append({
                "operation_tool_index": len(operation_tools),
                "operation_index": operation_index,
                "tool_index": ti,
                "tool_id": tool_id,
                "rank": rank,
                "selection_score": float(score),
            })
            summary = tool_use[ti]
            summary["localized_operation_count"] += 1
            summary["represented_operation_weight"] += float(operation.represented_weight)
            summary["represented_mass_kg"] += (
                float(operation.represented_weight) * float(operation.workpiece_mass_kg)
            )

    return {
        "workshops": [dict(row) for row in layer.workshop_rows],
        "guilds": [dict(row) for row in layer.guild_rows],
        "memberships": [dict(row) for row in layer.membership_rows],
        "tool_archetypes": [dict(row) for row in layer.archetype_rows],
        "archetype_operations": [dict(row) for row in layer.archetype_operation_rows],
        "tools": [dict(row) for row in layer.tool_rows],
        "operations": operations,
        "operation_tools": operation_tools,
        "tool_use": [tool_use[i] for i in sorted(tool_use)],
    }
