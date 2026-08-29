from __future__ import annotations

"""Atolia v3 phase-02 conditional metal biographies.

This module sits *after* the proven v1 intensity/loss propagation spine.
It never reruns circulation and never chooses archaeological objects. Each
v1 ``LossStratum`` is materialized as one weighted representative lineage,
with ``loss_intensity`` retained as the statistical weight.

Phase 02 introduces only metal/object bookkeeping:
- stable particle, metal-batch and object-episode identities;
- exact parent-mass accounting at full remelt;
- sparse source ancestry carried through parent mixing;
- repair/remelt event chronology along the already-known v1 route distance;
- distinct ore, cumulative-metal and current-object distances.

Element chemistry, Pb inventories, workshop/guild/tool assignment, hydrology,
external exchange and deposition pools belong to later v3 phases.
"""

from dataclasses import dataclass
import hashlib
import math
from typing import Any, Iterable, Mapping, Sequence

import provenance_field as base


BIOGRAPHY_MODEL_VERSION = "atolia-v3-metal-biography-v1"
MIXING_ASSUMPTION = (
    "conditional recycle-pool partition; mass-conserving within each remelt; "
    "no elemental process-loss coefficients"
)
MAX_EVENTS_PER_KIND = 64


@dataclass(frozen=True)
class MetalBatchState:
    batch_id: str
    particle_id: str
    role: str
    metal_mass_kg: float
    date_bc: int
    route_position_km: float
    node_id: str | None
    recycle_generation: int
    ancestry_mass_kg: Mapping[str, float]
    parent_contributions_kg: Mapping[str, float]
    retained_mass_fraction: float


@dataclass(frozen=True)
class ObjectEpisode:
    episode_id: str
    particle_id: str
    batch_id: str
    life_index: int
    object_class: str
    start_position_km: float
    end_position_km: float
    start_node_id: str | None
    end_node_id: str | None
    end_event_kind: str


@dataclass(frozen=True)
class BiographyEvent:
    event_id: str
    particle_id: str
    ordinal: int
    kind: str
    route_position_km: float
    node_id: str | None
    object_episode_id: str
    input_batch_ids: tuple[str, ...]
    output_batch_id: str | None
    retained_mass_fraction: float | None


@dataclass(frozen=True)
class MetalLineage:
    particle_id: str
    represented_weight: float
    production_cell_index: int
    production_cell_id: str
    cell_loss_index: int
    loss_site_id: str
    bundle_id: str
    object_class: str
    date_bc: int
    loss_node_id: str
    loss_step: int
    batches: tuple[MetalBatchState, ...]
    episodes: tuple[ObjectEpisode, ...]
    events: tuple[BiographyEvent, ...]
    final_batch_id: str
    final_object_episode_id: str
    ore_distance_km: float
    cumulative_metal_distance_km: float
    current_object_distance_km: float
    remelt_count: int
    repair_count: int
    source_entropy: float


def _seed64(*parts: object) -> int:
    raw = "|".join(str(part) for part in parts).encode("utf-8")
    return int.from_bytes(hashlib.sha256(raw).digest()[:8], "big")


def _uniform01(*parts: object) -> float:
    x = _seed64(*parts)
    return (x + 0.5) / (2**64)


def _stable_id(prefix: str, *parts: object) -> str:
    raw = "|".join(str(part) for part in parts).encode("utf-8")
    return f"{prefix}_{hashlib.sha256(raw).hexdigest()[:20]}"


def _normalize_mix(mix: Mapping[str, float]) -> dict[str, float]:
    out = {str(k): max(0.0, float(v)) for k, v in mix.items()}
    total = sum(out.values())
    if total <= 0.0:
        raise ValueError("metal biography requires a positive source mix")
    return {k: v / total for k, v in sorted(out.items()) if v > 0.0}


def _normalized_entropy_fraction(mix: Mapping[str, float]) -> float:
    vals = [float(v) for v in mix.values() if float(v) > 0.0]
    if len(vals) <= 1:
        return 0.0
    total = sum(vals)
    p = [v / total for v in vals]
    return float(-sum(x * math.log(x) for x in p) / math.log(len(p)))


def _mix_toward_entropy(
    base_mix: Mapping[str, float],
    target_entropy: float,
) -> dict[str, float]:
    """Increase entropy over the existing source support only."""
    base_norm = _normalize_mix(base_mix)
    if len(base_norm) <= 1:
        return base_norm
    h0 = _normalized_entropy_fraction(base_norm)
    target = min(1.0, max(h0, float(target_entropy)))
    if target <= h0 + 1e-15:
        return base_norm

    keys = list(base_norm)
    uniform = 1.0 / len(keys)
    lo, hi = 0.0, 1.0
    for _ in range(64):
        alpha = 0.5 * (lo + hi)
        candidate = {
            k: (1.0 - alpha) * base_norm[k] + alpha * uniform for k in keys
        }
        if _normalized_entropy_fraction(candidate) < target:
            lo = alpha
        else:
            hi = alpha
    alpha = 0.5 * (lo + hi)
    return {
        k: (1.0 - alpha) * base_norm[k] + alpha * uniform for k in keys
    }


def _ancestry_from_mix(mass_kg: float, mix: Mapping[str, float]) -> dict[str, float]:
    norm = _normalize_mix(mix)
    return {source_id: mass_kg * fraction for source_id, fraction in norm.items()}


def source_entropy_from_mass(ancestry_mass_kg: Mapping[str, float]) -> float:
    total = sum(max(0.0, float(v)) for v in ancestry_mass_kg.values())
    if total <= 0.0:
        return 0.0
    return _normalized_entropy_fraction(
        {k: max(0.0, float(v)) / total for k, v in ancestry_mass_kg.items()}
    )


def _stochastic_round(expectation: float, *seed_parts: object) -> int:
    value = max(0.0, float(expectation))
    whole = int(math.floor(value))
    fraction = value - whole
    count = whole + int(_uniform01(*seed_parts, "round") < fraction)
    return min(MAX_EVENTS_PER_KIND, count)


def _event_positions(
    total_distance_km: float,
    count: int,
    *seed_parts: object,
) -> list[float]:
    total = max(0.0, float(total_distance_km))
    if count <= 0:
        return []
    if total <= 0.0:
        return [0.0] * count
    positions = [
        total * _uniform01(*seed_parts, i, "position")
        for i in range(count)
    ]
    positions.sort()
    return positions


def _node_at_position(
    position_km: float,
    total_distance_km: float,
    origin_node_id: str,
    loss_node_id: str,
) -> str | None:
    if position_km <= 1e-12:
        return origin_node_id
    if abs(position_km - total_distance_km) <= 1e-12:
        return loss_node_id
    return None


def ore_distance_km(world: Any, cell: Any) -> float:
    """Source-weighted source -> production-origin geodesic distance."""
    if cell.origin not in world.nodes:
        return 0.0
    origin = world.nodes[cell.origin]
    weighted = 0.0
    known = 0.0
    for source_id, fraction in _normalize_mix(cell.source_mix).items():
        source = world.sources.get(source_id)
        if source is None:
            continue
        w = float(fraction)
        weighted += w * base.haversine_km(source.lon, source.lat, origin.lon, origin.lat)
        known += w
    return float(weighted / known) if known > 0.0 else 0.0


def _retained_fraction(
    world_seed: int,
    particle_id: str,
    remelt_index: int,
) -> float:
    u = _uniform01(world_seed, particle_id, remelt_index, "retained")
    return 0.62 + 0.28 * u


def validate_lineage(lineage: MetalLineage, *, tolerance: float = 1e-10) -> None:
    if not math.isfinite(lineage.represented_weight) or lineage.represented_weight <= 0.0:
        raise ValueError("lineage weight must be positive and finite")
    if lineage.current_object_distance_km < -tolerance:
        raise ValueError("current object distance is negative")
    if lineage.cumulative_metal_distance_km < -tolerance:
        raise ValueError("cumulative metal distance is negative")
    if lineage.current_object_distance_km > lineage.cumulative_metal_distance_km + tolerance:
        raise ValueError("current object distance exceeds cumulative metal distance")
    if lineage.ore_distance_km < -tolerance or not math.isfinite(lineage.ore_distance_km):
        raise ValueError("ore distance must be nonnegative and finite")

    by_id: dict[str, MetalBatchState] = {}
    order: dict[str, int] = {}
    for index, batch in enumerate(lineage.batches):
        if batch.batch_id in by_id:
            raise ValueError(f"duplicate batch id {batch.batch_id}")
        by_id[batch.batch_id] = batch
        order[batch.batch_id] = index
        if batch.metal_mass_kg <= 0.0 or not math.isfinite(batch.metal_mass_kg):
            raise ValueError("batch mass must be positive and finite")
        ancestry_mass = sum(float(v) for v in batch.ancestry_mass_kg.values())
        if abs(ancestry_mass - batch.metal_mass_kg) > max(tolerance, batch.metal_mass_kg * 1e-10):
            raise ValueError(f"ancestry mass does not close for {batch.batch_id}")
        if any(float(v) < 0.0 for v in batch.ancestry_mass_kg.values()):
            raise ValueError("negative ancestry mass")
        parent_mass = sum(float(v) for v in batch.parent_contributions_kg.values())
        if batch.parent_contributions_kg:
            if abs(parent_mass - batch.metal_mass_kg) > max(tolerance, batch.metal_mass_kg * 1e-10):
                raise ValueError(f"parent contributions do not close for {batch.batch_id}")
            for parent_id in batch.parent_contributions_kg:
                if parent_id not in by_id:
                    raise ValueError(f"parent batch {parent_id} must precede child")
                if order[parent_id] >= index:
                    raise ValueError("parent graph is not acyclic/topologically ordered")

    if lineage.final_batch_id not in by_id:
        raise ValueError("missing final batch")
    episode_ids = {episode.episode_id for episode in lineage.episodes}
    if lineage.final_object_episode_id not in episode_ids:
        raise ValueError("missing final object episode")
    if lineage.remelt_count != sum(event.kind == "remelt" for event in lineage.events):
        raise ValueError("remelt count mismatch")
    if lineage.repair_count != sum(event.kind == "repair" for event in lineage.events):
        raise ValueError("repair count mismatch")
    if not lineage.events or lineage.events[-1].kind != "loss":
        raise ValueError("lineage must terminate in the v1 loss event")
    positions = [float(event.route_position_km) for event in lineage.events]
    if any(not math.isfinite(x) or x < -tolerance for x in positions):
        raise ValueError("event route position invalid")
    if positions != sorted(positions):
        raise ValueError("event chronology is not monotone")
    if any(
        episode.end_position_km + tolerance < episode.start_position_km
        for episode in lineage.episodes
    ):
        raise ValueError("object episode has negative route extent")


def materialize_loss_lineage(
    world: Any,
    stratum: Any,
    *,
    world_seed: int,
    production_cell_index: int,
    cell_loss_index: int,
) -> MetalLineage:
    """Turn one v1 loss stratum into one weighted deterministic metal biography."""
    cell = stratum.production_cell
    weight = float(stratum.loss_intensity)
    if weight <= 0.0 or not math.isfinite(weight):
        raise ValueError("loss stratum intensity must be positive and finite")

    mass_kg = float(base.OBJECT_CLASSES[str(cell.object_class)]["mean_kg"])
    total_distance = max(0.0, float(stratum.route_distance_from_origin_km))
    production_cell_id = _stable_id(
        "pc",
        BIOGRAPHY_MODEL_VERSION,
        cell.bundle_id,
        cell.bundle_family,
        cell.object_class,
        cell.date_bc,
        cell.origin,
        cell.destination,
    )
    loss_site_id = _stable_id(
        "ls",
        production_cell_id,
        int(cell_loss_index),
        stratum.node_id,
        stratum.step,
    )
    particle_id = _stable_id(
        "p",
        BIOGRAPHY_MODEL_VERSION,
        int(world_seed),
        int(production_cell_index),
        loss_site_id,
    )

    remelt_count = _stochastic_round(
        stratum.expected_recycle_count,
        world_seed,
        particle_id,
        "remelts",
    )
    repair_count = _stochastic_round(
        stratum.expected_repair_count,
        world_seed,
        particle_id,
        "repairs",
    )
    remelt_positions = _event_positions(
        total_distance, remelt_count, world_seed, particle_id, "remelts"
    )
    repair_positions = _event_positions(
        total_distance, repair_count, world_seed, particle_id, "repairs"
    )

    base_mix = _normalize_mix(cell.source_mix)
    addition_mix = _mix_toward_entropy(base_mix, stratum.expected_source_entropy)
    initial_batch_id = _stable_id("mb", particle_id, 0, "initial")
    initial_batch = MetalBatchState(
        batch_id=initial_batch_id,
        particle_id=particle_id,
        role="initial_object",
        metal_mass_kg=mass_kg,
        date_bc=int(cell.date_bc),
        route_position_km=0.0,
        node_id=str(cell.origin),
        recycle_generation=0,
        ancestry_mass_kg=_ancestry_from_mix(mass_kg, base_mix),
        parent_contributions_kg={},
        retained_mass_fraction=1.0,
    )
    batches: list[MetalBatchState] = [initial_batch]
    episodes: list[ObjectEpisode] = []
    events: list[BiographyEvent] = []

    current_batch = initial_batch
    current_episode_id = _stable_id("oe", particle_id, 0)
    episode_start = 0.0
    episode_start_node: str | None = str(cell.origin)
    life_index = 0
    last_remelt_position = 0.0

    timeline = (
        [(position, 0, i, "remelt") for i, position in enumerate(remelt_positions)]
        + [(position, 1, i, "repair") for i, position in enumerate(repair_positions)]
    )
    timeline.sort(key=lambda row: (row[0], row[1], row[2]))

    ordinal = 0
    remelt_seen = 0
    for position, _, local_index, kind in timeline:
        node_id = _node_at_position(
            position, total_distance, str(cell.origin), str(stratum.node_id)
        )
        if kind == "repair":
            events.append(
                BiographyEvent(
                    event_id=_stable_id("ev", particle_id, ordinal, "repair"),
                    particle_id=particle_id,
                    ordinal=ordinal,
                    kind="repair",
                    route_position_km=float(position),
                    node_id=node_id,
                    object_episode_id=current_episode_id,
                    input_batch_ids=(current_batch.batch_id,),
                    output_batch_id=current_batch.batch_id,
                    retained_mass_fraction=1.0,
                )
            )
            ordinal += 1
            continue

        remelt_seen += 1
        retained = _retained_fraction(world_seed, particle_id, remelt_seen)
        old_contribution = mass_kg * retained
        addition_mass = mass_kg - old_contribution

        addition_batch_id = _stable_id(
            "mb", particle_id, remelt_seen, "recycle-pool-addition"
        )
        addition_batch = MetalBatchState(
            batch_id=addition_batch_id,
            particle_id=particle_id,
            role="recycle_pool_addition",
            metal_mass_kg=addition_mass,
            date_bc=int(cell.date_bc),
            route_position_km=float(position),
            node_id=node_id,
            recycle_generation=remelt_seen,
            ancestry_mass_kg=_ancestry_from_mix(addition_mass, addition_mix),
            parent_contributions_kg={},
            retained_mass_fraction=1.0,
        )
        batches.append(addition_batch)

        child_ancestry = {
            source_id: float(source_mass) * retained
            for source_id, source_mass in current_batch.ancestry_mass_kg.items()
        }
        for source_id, source_mass in addition_batch.ancestry_mass_kg.items():
            child_ancestry[source_id] = child_ancestry.get(source_id, 0.0) + float(
                source_mass
            )

        child_batch_id = _stable_id("mb", particle_id, remelt_seen, "remelt-output")
        child_batch = MetalBatchState(
            batch_id=child_batch_id,
            particle_id=particle_id,
            role="remelt_output",
            metal_mass_kg=mass_kg,
            date_bc=int(cell.date_bc),
            route_position_km=float(position),
            node_id=node_id,
            recycle_generation=remelt_seen,
            ancestry_mass_kg=child_ancestry,
            parent_contributions_kg={
                current_batch.batch_id: old_contribution,
                addition_batch.batch_id: addition_mass,
            },
            retained_mass_fraction=retained,
        )
        batches.append(child_batch)

        episodes.append(
            ObjectEpisode(
                episode_id=current_episode_id,
                particle_id=particle_id,
                batch_id=current_batch.batch_id,
                life_index=life_index,
                object_class=str(cell.object_class),
                start_position_km=float(episode_start),
                end_position_km=float(position),
                start_node_id=episode_start_node,
                end_node_id=node_id,
                end_event_kind="remelt",
            )
        )
        events.append(
            BiographyEvent(
                event_id=_stable_id("ev", particle_id, ordinal, "remelt"),
                particle_id=particle_id,
                ordinal=ordinal,
                kind="remelt",
                route_position_km=float(position),
                node_id=node_id,
                object_episode_id=current_episode_id,
                input_batch_ids=(current_batch.batch_id, addition_batch.batch_id),
                output_batch_id=child_batch.batch_id,
                retained_mass_fraction=retained,
            )
        )
        ordinal += 1

        current_batch = child_batch
        life_index += 1
        current_episode_id = _stable_id("oe", particle_id, life_index)
        episode_start = float(position)
        episode_start_node = node_id
        last_remelt_position = float(position)

    episodes.append(
        ObjectEpisode(
            episode_id=current_episode_id,
            particle_id=particle_id,
            batch_id=current_batch.batch_id,
            life_index=life_index,
            object_class=str(cell.object_class),
            start_position_km=float(episode_start),
            end_position_km=total_distance,
            start_node_id=episode_start_node,
            end_node_id=str(stratum.node_id),
            end_event_kind="loss",
        )
    )
    events.append(
        BiographyEvent(
            event_id=_stable_id("ev", particle_id, ordinal, "loss"),
            particle_id=particle_id,
            ordinal=ordinal,
            kind="loss",
            route_position_km=total_distance,
            node_id=str(stratum.node_id),
            object_episode_id=current_episode_id,
            input_batch_ids=(current_batch.batch_id,),
            output_batch_id=None,
            retained_mass_fraction=None,
        )
    )

    lineage = MetalLineage(
        particle_id=particle_id,
        represented_weight=weight,
        production_cell_index=int(production_cell_index),
        production_cell_id=production_cell_id,
        cell_loss_index=int(cell_loss_index),
        loss_site_id=loss_site_id,
        bundle_id=str(cell.bundle_id),
        object_class=str(cell.object_class),
        date_bc=int(cell.date_bc),
        loss_node_id=str(stratum.node_id),
        loss_step=int(stratum.step),
        batches=tuple(batches),
        episodes=tuple(episodes),
        events=tuple(events),
        final_batch_id=current_batch.batch_id,
        final_object_episode_id=current_episode_id,
        ore_distance_km=ore_distance_km(world, cell),
        cumulative_metal_distance_km=total_distance,
        current_object_distance_km=max(0.0, total_distance - last_remelt_position),
        remelt_count=remelt_count,
        repair_count=repair_count,
        source_entropy=source_entropy_from_mass(current_batch.ancestry_mass_kg),
    )
    validate_lineage(lineage)
    return lineage


def iter_loss_lineages(
    world: Any,
    reports: Sequence[Any],
    *,
    world_seed: int,
) -> Iterable[MetalLineage]:
    for cell_index, report in enumerate(reports):
        for cell_loss_index, stratum in enumerate(report.loss_strata):
            yield materialize_loss_lineage(
                world,
                stratum,
                world_seed=world_seed,
                production_cell_index=cell_index,
                cell_loss_index=cell_loss_index,
            )


def materialize_loss_lineages(
    world: Any,
    reports: Sequence[Any],
    *,
    world_seed: int,
) -> list[MetalLineage]:
    return list(iter_loss_lineages(world, reports, world_seed=world_seed))


def flatten_lineages(
    lineages: Sequence[MetalLineage],
) -> dict[str, list[dict[str, Any]]]:
    particles: list[dict[str, Any]] = []
    batches: list[dict[str, Any]] = []
    ancestry: list[dict[str, Any]] = []
    parents: list[dict[str, Any]] = []
    episodes: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []

    batch_index_by_id: dict[str, int] = {}
    episode_index_by_id: dict[str, int] = {}

    for particle_index, lineage in enumerate(lineages):
        for batch in lineage.batches:
            batch_index = len(batches)
            batch_index_by_id[batch.batch_id] = batch_index
            batches.append({
                "batch_index": batch_index,
                "particle_index": particle_index,
                "batch_id": batch.batch_id,
                "role": batch.role,
                "metal_mass_kg": float(batch.metal_mass_kg),
                "date_bc": int(batch.date_bc),
                "route_position_km": float(batch.route_position_km),
                "node_id": batch.node_id,
                "recycle_generation": int(batch.recycle_generation),
                "retained_mass_fraction": float(batch.retained_mass_fraction),
            })
            for source_id, source_mass in sorted(batch.ancestry_mass_kg.items()):
                ancestry.append({
                    "ancestry_index": len(ancestry),
                    "batch_index": batch_index,
                    "source_id": str(source_id),
                    "mass_kg": float(source_mass),
                    "fraction": float(source_mass) / float(batch.metal_mass_kg),
                })

        for batch in lineage.batches:
            if not batch.parent_contributions_kg:
                continue
            child_index = batch_index_by_id[batch.batch_id]
            for parent_id, contribution in batch.parent_contributions_kg.items():
                parents.append({
                    "parent_link_index": len(parents),
                    "child_batch_index": child_index,
                    "parent_batch_index": batch_index_by_id[parent_id],
                    "contribution_kg": float(contribution),
                    "fraction_of_child": float(contribution) / float(batch.metal_mass_kg),
                })

        for episode in lineage.episodes:
            episode_index = len(episodes)
            episode_index_by_id[episode.episode_id] = episode_index
            episodes.append({
                "episode_index": episode_index,
                "particle_index": particle_index,
                "episode_id": episode.episode_id,
                "batch_index": batch_index_by_id[episode.batch_id],
                "life_index": int(episode.life_index),
                "object_class": episode.object_class,
                "start_position_km": float(episode.start_position_km),
                "end_position_km": float(episode.end_position_km),
                "start_node_id": episode.start_node_id,
                "end_node_id": episode.end_node_id,
                "end_event_kind": episode.end_event_kind,
            })

        for event in lineage.events:
            events.append({
                "event_index": len(events),
                "particle_index": particle_index,
                "event_id": event.event_id,
                "ordinal": int(event.ordinal),
                "kind": event.kind,
                "route_position_km": float(event.route_position_km),
                "node_id": event.node_id,
                "episode_index": episode_index_by_id[event.object_episode_id],
                "input_batch_indices": [
                    batch_index_by_id[batch_id] for batch_id in event.input_batch_ids
                ],
                "output_batch_index": (
                    -1
                    if event.output_batch_id is None
                    else batch_index_by_id[event.output_batch_id]
                ),
                "retained_mass_fraction": (
                    None
                    if event.retained_mass_fraction is None
                    else float(event.retained_mass_fraction)
                ),
            })

        final_batch = batch_index_by_id[lineage.final_batch_id]
        final_episode = episode_index_by_id[lineage.final_object_episode_id]
        particles.append({
            "particle_index": particle_index,
            "particle_id": lineage.particle_id,
            "represented_weight": float(lineage.represented_weight),
            "production_cell_index": int(lineage.production_cell_index),
            "production_cell_id": lineage.production_cell_id,
            "cell_loss_index": int(lineage.cell_loss_index),
            "loss_site_id": lineage.loss_site_id,
            "bundle_id": lineage.bundle_id,
            "object_class": lineage.object_class,
            "date_bc": int(lineage.date_bc),
            "loss_node_id": lineage.loss_node_id,
            "loss_step": int(lineage.loss_step),
            "final_batch_index": final_batch,
            "final_episode_index": final_episode,
            "metal_batch_id": lineage.final_batch_id,
            "object_episode_id": lineage.final_object_episode_id,
            "metal_mass_kg": float(lineage.batches[-1].metal_mass_kg),
            "ore_distance_km": float(lineage.ore_distance_km),
            "cumulative_metal_distance_km": float(
                lineage.cumulative_metal_distance_km
            ),
            "current_object_distance_km": float(lineage.current_object_distance_km),
            "remelt_count": int(lineage.remelt_count),
            "repair_count": int(lineage.repair_count),
            "source_entropy": float(lineage.source_entropy),
        })

    return {
        "particles": particles,
        "batches": batches,
        "ancestry": ancestry,
        "parents": parents,
        "episodes": episodes,
        "events": events,
    }
