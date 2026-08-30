from __future__ import annotations

"""Atolia v3 phase-05 hydrology, sparse exchange, deposition and observation.

This layer is strictly downstream of the proven v1 loss strata and the phase-02
weighted metal biographies. It does not rerun circulation, change batch genealogy,
change chemistry, or choose player-visible archaeological objects.

The separation is explicit:
- evidence: observed/model-input statements about possible water connections;
- ensemble: candidate hydrological edges with realization probabilities;
- realization: one deterministic world realization drawn from that ensemble;
- exchange: sparse external-network contacts that do not alter metal mass;
- deposition: one terminal mode per weighted lineage plus shared late-stage pools;
- archaeology: conditional survival -> discovery -> recording expected weights.

When no converted palaeohydrology/GIS product is supplied, the model is marked
provisional and uses only the existing structural world graph plus transparent
short-range water-connector priors. Those priors are not empirical evidence.
"""

from dataclasses import dataclass
import hashlib
import math
from typing import Any, Mapping, Sequence

import provenance_field as base


PHASE05_MODEL_VERSION = "atolia-v3-hydro-exchange-deposition-v1"
HYDRO_EVIDENCE_STATUS_STRUCTURAL_ONLY = (
    "structural-world-graph-plus-provisional-connectors-no-external-palaeohydrology"
)
HYDRO_EVIDENCE_STATUS_SUPPLIED = "supplied-evidence-plus-structural-world-graph"
EXCHANGE_STATUS = "sparse-model-tail-no-external-traffic-calibration"
DEPOSITION_STATUS = "v1-loss-stratum-mode-priors-shared-node-date-pools"
OBSERVATION_STATUS = "conditional-priors-not-empirical-calibration"
CANDIDATE_DENSITY_MULTIPLIER = 5.0
MAX_CANDIDATE_CONNECTOR_KM = 95.0


MODE_SURVIVAL = {
    "founder_scrap_hoard": .74,
    "finished_object_hoard": .80,
    "selective_ritual_deposit": .69,
    "personal_wealth_deposit": .63,
    "grave_assemblage": .66,
    "settlement_loss": .44,
    "river_wetland_deposit": .83,
    "workshop_debris": .38,
    "catastrophic_abandonment": .57,
    "wetland": .83,
    "river": .78,
    "hoard": .76,
    "wreck": .84,
    "funerary": .66,
    "settlement": .44,
    "workshop": .38,
    "fortification": .50,
    "field_loss": .34,
    "ritual": .69,
    "unknown": .46,
}

MODE_DISCOVERY = {
    "founder_scrap_hoard": .030,
    "finished_object_hoard": .026,
    "selective_ritual_deposit": .013,
    "personal_wealth_deposit": .020,
    "grave_assemblage": .031,
    "settlement_loss": .024,
    "river_wetland_deposit": .008,
    "workshop_debris": .036,
    "catastrophic_abandonment": .033,
    "wetland": .008,
    "river": .010,
    "hoard": .028,
    "wreck": .006,
    "funerary": .031,
    "settlement": .024,
    "workshop": .036,
    "fortification": .026,
    "field_loss": .018,
    "ritual": .013,
    "unknown": .018,
}

MODE_RECORD = {
    "founder_scrap_hoard": .66,
    "finished_object_hoard": .72,
    "selective_ritual_deposit": .63,
    "personal_wealth_deposit": .62,
    "grave_assemblage": .76,
    "settlement_loss": .48,
    "river_wetland_deposit": .55,
    "workshop_debris": .40,
    "catastrophic_abandonment": .67,
    "wetland": .55,
    "river": .56,
    "hoard": .70,
    "wreck": .58,
    "funerary": .76,
    "settlement": .48,
    "workshop": .40,
    "fortification": .60,
    "field_loss": .35,
    "ritual": .63,
    "unknown": .44,
}

PRESTIGE_CLASSES = {"sword", "dagger", "ornament", "figurine", "vessel", "spearhead"}

_EXTERNAL_TOKEN_COMPONENT = (
    (("cyprus", "levant", "egypt"), "external_eastern_med"),
    (("aegean", "hatti", "anatol"), "external_aegean_anatolian"),
    (("western_med",), "external_western_med"),
    (("britain", "severn"), "external_atlantic"),
)


@dataclass(frozen=True)
class HydroEvidenceRecord:
    evidence_id: str
    a: str
    b: str
    evidence_kind: str
    provenance: str
    mode: str
    confidence: float
    navigability: float
    empirical: bool


@dataclass(frozen=True)
class HydroEnsembleEdge:
    edge_id: str
    a: str
    b: str
    mode: str
    probability: float
    navigability: float
    structural: bool
    evidence_ids: tuple[str, ...]
    empirical_evidence_count: int
    probability_basis: str


@dataclass(frozen=True)
class HydroRealizationEdge:
    realization_id: str
    edge_id: str
    a: str
    b: str
    mode: str
    realized: bool
    draw: float
    probability: float
    navigability: float
    structural: bool


@dataclass(frozen=True)
class ExternalExchangeRecord:
    exchange_id: str
    particle_id: str
    external_component_id: str
    trigger: str
    contact_probability: float
    contact_intensity: float
    node_id: str
    date_bc: int
    represented_weight: float


@dataclass(frozen=True)
class DepositionAssignment:
    particle_id: str
    loss_site_id: str
    deposition_pool_id: str
    hydro_realization_id: str
    node_id: str
    date_bc: int
    mode: str
    mode_probability: float
    mode_weights: Mapping[str, float]
    represented_weight: float
    expected_field_crossings: float
    expected_physical_crossings: float
    hydro_context_score: float


@dataclass(frozen=True)
class DepositionPool:
    deposition_pool_id: str
    node_id: str
    date_bc: int
    mode: str
    member_count: int
    represented_weight: float
    hydro_realization_id: str
    hydro_context_score: float


@dataclass(frozen=True)
class ArchaeologyObservation:
    particle_id: str
    deposition_pool_id: str
    represented_loss_weight: float
    p_survival: float
    survival_weight: float
    p_discovery: float
    discovery_weight: float
    p_record: float
    recorded_weight: float


@dataclass(frozen=True)
class Phase05Layer:
    hydro_evidence_status: str
    exchange_status: str
    deposition_status: str
    observation_status: str
    hydro_evidence: tuple[HydroEvidenceRecord, ...]
    hydro_ensemble: tuple[HydroEnsembleEdge, ...]
    hydro_realization: tuple[HydroRealizationEdge, ...]
    external_exchange: tuple[ExternalExchangeRecord, ...]
    deposition_assignments: tuple[DepositionAssignment, ...]
    deposition_pools: tuple[DepositionPool, ...]
    archaeology: tuple[ArchaeologyObservation, ...]


def _seed64(*parts: object) -> int:
    raw = "|".join(str(part) for part in parts).encode("utf-8")
    return int.from_bytes(hashlib.sha256(raw).digest()[:8], "big")


def _uniform01(*parts: object) -> float:
    return (_seed64(*parts) + 0.5) / (2**64)


def _stable_id(prefix: str, *parts: object) -> str:
    raw = "|".join(str(part) for part in parts).encode("utf-8")
    return f"{prefix}_{hashlib.sha256(raw).hexdigest()[:20]}"


def _clip(x: float, lo: float, hi: float) -> float:
    return min(hi, max(lo, float(x)))


def _edge_key(a: str, b: str) -> tuple[str, str]:
    aa, bb = str(a), str(b)
    return (aa, bb) if aa <= bb else (bb, aa)


def _edge_km(world: Any, a: str, b: str) -> float:
    na, nb = world.nodes[a], world.nodes[b]
    return float(base.haversine_km(na.lon, na.lat, nb.lon, nb.lat))


def _is_water_mode(mode: str) -> bool:
    text = str(mode).lower()
    return any(token in text for token in ("river", "sea", "coast", "lagoon", "wetland", "channel"))


def _water_node(kind: str) -> bool:
    return str(kind) in {"river", "coast", "hub"}


def _normalize_weights(weights: Mapping[str, float]) -> dict[str, float]:
    rows = {str(k): max(0.0, float(v)) for k, v in weights.items()}
    total = sum(rows.values())
    if total <= 0.0:
        return {"unknown": 1.0}
    return {k: rows[k] / total for k in sorted(rows) if rows[k] > 0.0}


def _weighted_choice(weights: Mapping[str, float], draw: float) -> tuple[str, float]:
    norm = _normalize_weights(weights)
    u = _clip(draw, 0.0, 1.0)
    cumulative = 0.0
    last = next(iter(norm))
    for key, probability in norm.items():
        last = key
        cumulative += probability
        if u <= cumulative:
            return key, probability
    return last, norm[last]


def _structural_hydro_evidence(world: Any) -> list[HydroEvidenceRecord]:
    rows: list[HydroEvidenceRecord] = []
    seen: set[tuple[str, str, str]] = set()
    for edge in world.edges:
        mode = str(edge.mode)
        if not _is_water_mode(mode):
            continue
        a, b = str(edge.a), str(edge.b)
        key = (*_edge_key(a, b), mode)
        if key in seen:
            continue
        seen.add(key)
        eid = _stable_id("hev", a, b, mode, "world-structural-graph")
        rows.append(HydroEvidenceRecord(
            evidence_id=eid,
            a=a,
            b=b,
            evidence_kind="model_graph_edge",
            provenance="world-structural-graph",
            mode=mode,
            confidence=1.0,
            navigability=.85,
            empirical=False,
        ))
    return rows


def _supplied_hydro_evidence(world: Any, supplied: Sequence[Mapping[str, Any]]) -> list[HydroEvidenceRecord]:
    rows: list[HydroEvidenceRecord] = []
    for index, raw in enumerate(supplied):
        a, b = str(raw["a"]), str(raw["b"])
        if a not in world.nodes or b not in world.nodes:
            raise ValueError(f"hydro evidence references unknown node: {a} - {b}")
        mode = str(raw.get("mode", raw.get("mechanism", "palaeochannel_candidate")))
        confidence = _clip(raw.get("confidence", raw.get("probability", .5)), 0.0, 1.0)
        navigability = _clip(raw.get("navigability", .45), 0.0, 1.0)
        provenance = str(raw.get("provenance", "supplied-hydro-evidence"))
        eid = str(raw.get("evidence_id") or _stable_id("hev", a, b, mode, provenance, index))
        rows.append(HydroEvidenceRecord(
            evidence_id=eid,
            a=a,
            b=b,
            evidence_kind=str(raw.get("evidence_kind", "supplied_feature")),
            provenance=provenance,
            mode=mode,
            confidence=confidence,
            navigability=navigability,
            empirical=bool(raw.get("empirical", True)),
        ))
    return rows


def _candidate_prior(world: Any, a: str, b: str) -> tuple[float, float, float]:
    km = _edge_km(world, a, b)
    na, nb = world.nodes[a], world.nodes[b]
    kind_bonus = (
        .22 * float(str(na.kind) == "river")
        + .22 * float(str(nb.kind) == "river")
        + .15 * float(str(na.kind) == "hub" or str(nb.kind) == "hub")
    )
    probability = _clip(.07 + .62 * math.exp(-km / 38.0) + kind_bonus, .03, .88)
    navigability = _clip(.18 + .55 * probability, .05, .95)
    score = probability * (.55 + .45 * navigability)
    return probability, navigability, score


def build_hydro_ensemble(
    world: Any,
    *,
    supplied_evidence: Sequence[Mapping[str, Any]] = (),
    candidate_density_multiplier: float = CANDIDATE_DENSITY_MULTIPLIER,
) -> tuple[str, tuple[HydroEvidenceRecord, ...], tuple[HydroEnsembleEdge, ...]]:
    evidence = _structural_hydro_evidence(world)
    supplied_rows = _supplied_hydro_evidence(world, supplied_evidence)
    evidence.extend(supplied_rows)
    evidence.sort(key=lambda r: (r.a, r.b, r.evidence_id))

    by_pair: dict[tuple[str, str], list[HydroEvidenceRecord]] = {}
    for row in evidence:
        by_pair.setdefault(_edge_key(row.a, row.b), []).append(row)

    structural_pairs = {
        _edge_key(row.a, row.b)
        for row in evidence
        if row.evidence_kind == "model_graph_edge"
    }
    candidates: list[tuple[float, str, str, float, float]] = []
    water_nodes = [str(node.id) for node in world.nodes.values() if _water_node(node.kind)]
    water_nodes.sort()
    for i, a in enumerate(water_nodes):
        for b in water_nodes[i + 1:]:
            key = _edge_key(a, b)
            if key in structural_pairs:
                continue
            km = _edge_km(world, a, b)
            if km > MAX_CANDIDATE_CONNECTOR_KM:
                continue
            p, nav, score = _candidate_prior(world, a, b)
            candidates.append((score, a, b, p, nav))
    candidates.sort(key=lambda row: (-row[0], row[1], row[2]))
    target_extra = max(
        len([key for key in by_pair if key not in structural_pairs]),
        int(round(max(0.0, candidate_density_multiplier - 1.0) * max(1, len(structural_pairs)))),
    )
    for _, a, b, p, nav in candidates[:target_extra]:
        key = _edge_key(a, b)
        by_pair.setdefault(key, [])

    ensemble: list[HydroEnsembleEdge] = []
    for key in sorted(by_pair):
        a, b = key
        rows = by_pair[key]
        structural = any(r.evidence_kind == "model_graph_edge" for r in rows)
        empirical_rows = [r for r in rows if r.empirical]
        if structural:
            probability = 1.0
            navigability = max([r.navigability for r in rows] or [.85])
            mode = next((r.mode for r in rows if r.evidence_kind == "model_graph_edge"), "water_structural")
            basis = "structural-world-edge"
        else:
            prior, prior_nav, _ = _candidate_prior(world, a, b)
            probability = prior
            navigability = prior_nav
            if rows:
                for row in rows:
                    probability = 1.0 - (1.0 - probability) * (1.0 - .90 * row.confidence)
                navigability = sum(r.navigability * max(.05, r.confidence) for r in rows) / sum(max(.05, r.confidence) for r in rows)
                mode = rows[0].mode
                basis = "connector-prior-plus-supplied-evidence"
            else:
                mode = "minor_channel_or_wetland_connector"
                basis = "provisional-short-range-water-connector-prior"
        edge_id = _stable_id("hed", a, b, mode)
        ensemble.append(HydroEnsembleEdge(
            edge_id=edge_id,
            a=a,
            b=b,
            mode=mode,
            probability=_clip(probability, 0.0, 1.0),
            navigability=_clip(navigability, 0.0, 1.0),
            structural=structural,
            evidence_ids=tuple(sorted(r.evidence_id for r in rows)),
            empirical_evidence_count=len(empirical_rows),
            probability_basis=basis,
        ))

    status = HYDRO_EVIDENCE_STATUS_SUPPLIED if supplied_rows else HYDRO_EVIDENCE_STATUS_STRUCTURAL_ONLY
    return status, tuple(evidence), tuple(ensemble)


def realize_hydro(
    ensemble: Sequence[HydroEnsembleEdge],
    *,
    world_seed: int,
) -> tuple[HydroRealizationEdge, ...]:
    ensemble_signature = hashlib.sha256(
        "|".join(f"{r.edge_id}:{r.probability:.12g}" for r in ensemble).encode("utf-8")
    ).hexdigest()[:20]
    realization_id = _stable_id("hyr", world_seed, ensemble_signature)
    out: list[HydroRealizationEdge] = []
    for row in ensemble:
        draw = 0.0 if row.structural else _uniform01(world_seed, row.edge_id, "hydro-realization")
        realized = True if row.structural else bool(draw < row.probability)
        out.append(HydroRealizationEdge(
            realization_id=realization_id,
            edge_id=row.edge_id,
            a=row.a,
            b=row.b,
            mode=row.mode,
            realized=realized,
            draw=draw,
            probability=row.probability,
            navigability=row.navigability,
            structural=row.structural,
        ))
    return tuple(out)


def _hydro_context(realization: Sequence[HydroRealizationEdge]) -> dict[str, float]:
    values: dict[str, list[float]] = {}
    for row in realization:
        if not row.realized:
            continue
        values.setdefault(row.a, []).append(row.navigability)
        values.setdefault(row.b, []).append(row.navigability)
    return {
        node: sum(rows) / len(rows)
        for node, rows in values.items()
        if rows
    }


def _external_component(cell: Any) -> tuple[str, str]:
    source_ids = " ".join(str(k) for k in getattr(cell, "source_mix", {}).keys())
    text = f"{cell.bundle_family} {cell.bundle_id} {source_ids}".lower()
    for tokens, component in _EXTERNAL_TOKEN_COMPONENT:
        if any(token in text for token in tokens):
            return component, "source-or-bundle-tagged"
    return "external_unspecified_network", "rare-network-prior"


def materialize_external_exchange(
    reports: Sequence[Any],
    lineages: Sequence[Any],
    hydro_context: Mapping[str, float],
    *,
    world_seed: int,
) -> tuple[ExternalExchangeRecord, ...]:
    out: list[ExternalExchangeRecord] = []
    for lineage in lineages:
        cell = reports[int(lineage.production_cell_index)].production_cell
        component, trigger = _external_component(cell)
        prestige = float(str(lineage.object_class) in PRESTIGE_CLASSES)
        distance = min(1500.0, max(0.0, float(lineage.cumulative_metal_distance_km)))
        water = _clip(hydro_context.get(str(lineage.loss_node_id), 0.0), 0.0, 1.0)
        tagged = float(trigger == "source-or-bundle-tagged")
        probability = _clip(
            .006 + .010 * prestige + .010 * min(1.0, distance / 700.0) + .008 * water + .025 * tagged,
            .001,
            .065,
        )
        draw = _uniform01(world_seed, lineage.particle_id, "external-exchange-tail")
        if draw >= probability:
            continue
        intensity = .02 + .10 * _uniform01(world_seed, lineage.particle_id, "external-exchange-intensity")
        out.append(ExternalExchangeRecord(
            exchange_id=_stable_id("ex", lineage.particle_id, component),
            particle_id=str(lineage.particle_id),
            external_component_id=component,
            trigger=trigger,
            contact_probability=probability,
            contact_intensity=float(intensity),
            node_id=str(lineage.loss_node_id),
            date_bc=int(lineage.date_bc),
            represented_weight=float(lineage.represented_weight),
        ))
    return tuple(out)


def _loss_strata_by_lineage_key(reports: Sequence[Any]) -> dict[tuple[int, int], Any]:
    out: dict[tuple[int, int], Any] = {}
    for cell_index, report in enumerate(reports):
        for loss_index, stratum in enumerate(report.loss_strata):
            out[(cell_index, loss_index)] = stratum
    return out


def materialize_deposition(
    reports: Sequence[Any],
    lineages: Sequence[Any],
    realization: Sequence[HydroRealizationEdge],
    *,
    world_seed: int,
) -> tuple[tuple[DepositionAssignment, ...], tuple[DepositionPool, ...]]:
    strata = _loss_strata_by_lineage_key(reports)
    context = _hydro_context(realization)
    realization_ids = {row.realization_id for row in realization}
    hydro_realization_id = next(iter(realization_ids)) if realization_ids else _stable_id("hyr", world_seed, "empty")
    if len(realization_ids) > 1:
        raise ValueError("phase-05 expects one hydro realization per world build")

    assignments: list[DepositionAssignment] = []
    pool_members: dict[tuple[str, int, str], list[DepositionAssignment]] = {}
    for lineage in lineages:
        key = (int(lineage.production_cell_index), int(lineage.cell_loss_index))
        if key not in strata:
            raise ValueError(f"missing v1 LossStratum for phase-02 lineage {lineage.particle_id}")
        stratum = strata[key]
        weights = _normalize_weights(stratum.deposition_mode_weights)
        mode, mode_probability = _weighted_choice(
            weights,
            _uniform01(world_seed, lineage.particle_id, "deposition-mode"),
        )
        pool_id = _stable_id("dep", lineage.loss_node_id, lineage.date_bc, mode)
        assignment = DepositionAssignment(
            particle_id=str(lineage.particle_id),
            loss_site_id=str(lineage.loss_site_id),
            deposition_pool_id=pool_id,
            hydro_realization_id=hydro_realization_id,
            node_id=str(lineage.loss_node_id),
            date_bc=int(lineage.date_bc),
            mode=mode,
            mode_probability=float(mode_probability),
            mode_weights=weights,
            represented_weight=float(lineage.represented_weight),
            expected_field_crossings=float(stratum.expected_field_crossings),
            expected_physical_crossings=float(stratum.expected_physical_crossings),
            hydro_context_score=float(context.get(str(lineage.loss_node_id), 0.0)),
        )
        assignments.append(assignment)
        pool_members.setdefault((assignment.node_id, assignment.date_bc, assignment.mode), []).append(assignment)

    pools: list[DepositionPool] = []
    for pool_key in sorted(pool_members):
        rows = pool_members[pool_key]
        first = rows[0]
        total_weight = sum(row.represented_weight for row in rows)
        weighted_hydro = sum(row.represented_weight * row.hydro_context_score for row in rows) / max(1e-30, total_weight)
        pools.append(DepositionPool(
            deposition_pool_id=first.deposition_pool_id,
            node_id=first.node_id,
            date_bc=first.date_bc,
            mode=first.mode,
            member_count=len(rows),
            represented_weight=float(total_weight),
            hydro_realization_id=hydro_realization_id,
            hydro_context_score=float(weighted_hydro),
        ))
    return tuple(assignments), tuple(pools)


def survival_probability(lineage: Any, mode: str) -> float:
    base_p = MODE_SURVIVAL.get(str(mode), .46)
    integrity = math.exp(-.045 * float(lineage.remelt_count) - .025 * float(lineage.repair_count))
    obj = str(lineage.object_class)
    class_factor = 1.07 if obj in PRESTIGE_CLASSES else (.94 if obj in {"bead", "pin", "awl"} else 1.0)
    return _clip(base_p * integrity * class_factor, .03, .97)


def discovery_probability(lineage: Any, assignment: DepositionAssignment) -> float:
    mode = str(assignment.mode)
    obj = str(lineage.object_class)
    base_p = MODE_DISCOVERY.get(mode, .018)
    mass = float(base.OBJECT_CLASSES.get(obj, {"mean_kg": .2})["mean_kg"])
    visibility = .65 + .55 * min(1.0, math.log1p(7.0 * mass) / math.log(34.6))
    remoteness = math.exp(-.00011 * float(lineage.cumulative_metal_distance_km)) * math.exp(
        -.018 * min(5.0, assignment.expected_physical_crossings + 2.0 * assignment.expected_field_crossings)
    )
    return _clip(base_p * visibility * remoteness, .0003, .08)


def record_probability(lineage: Any, mode: str) -> float:
    base_p = MODE_RECORD.get(str(mode), .44)
    prestige = 1.10 if str(lineage.object_class) in PRESTIGE_CLASSES else 1.0
    workshop_fragment_penalty = .88 if str(mode) in {"workshop_debris", "workshop"} else 1.0
    repair_bonus = 1.0 + .015 * min(4.0, float(lineage.repair_count))
    return _clip(base_p * prestige * workshop_fragment_penalty * repair_bonus, .08, .92)


def materialize_archaeology(
    lineages: Sequence[Any],
    assignments: Sequence[DepositionAssignment],
) -> tuple[ArchaeologyObservation, ...]:
    by_particle = {row.particle_id: row for row in assignments}
    out: list[ArchaeologyObservation] = []
    for lineage in lineages:
        assignment = by_particle[str(lineage.particle_id)]
        loss_weight = float(lineage.represented_weight)
        p_survival = survival_probability(lineage, assignment.mode)
        survival_weight = loss_weight * p_survival
        p_discovery = discovery_probability(lineage, assignment)
        discovery_weight = survival_weight * p_discovery
        p_record = record_probability(lineage, assignment.mode)
        recorded_weight = discovery_weight * p_record
        out.append(ArchaeologyObservation(
            particle_id=str(lineage.particle_id),
            deposition_pool_id=assignment.deposition_pool_id,
            represented_loss_weight=loss_weight,
            p_survival=p_survival,
            survival_weight=survival_weight,
            p_discovery=p_discovery,
            discovery_weight=discovery_weight,
            p_record=p_record,
            recorded_weight=recorded_weight,
        ))
    return tuple(out)


def materialize_phase05(
    world: Any,
    reports: Sequence[Any],
    lineages: Sequence[Any],
    *,
    world_seed: int,
    supplied_hydro_evidence: Sequence[Mapping[str, Any]] = (),
) -> Phase05Layer:
    hydro_status, evidence, ensemble = build_hydro_ensemble(
        world,
        supplied_evidence=supplied_hydro_evidence,
    )
    realization = realize_hydro(ensemble, world_seed=world_seed)
    context = _hydro_context(realization)
    external = materialize_external_exchange(
        reports,
        lineages,
        context,
        world_seed=world_seed,
    )
    assignments, pools = materialize_deposition(
        reports,
        lineages,
        realization,
        world_seed=world_seed,
    )
    archaeology = materialize_archaeology(lineages, assignments)
    validate_phase05(
        lineages,
        evidence,
        ensemble,
        realization,
        external,
        assignments,
        pools,
        archaeology,
    )
    return Phase05Layer(
        hydro_evidence_status=hydro_status,
        exchange_status=EXCHANGE_STATUS,
        deposition_status=DEPOSITION_STATUS,
        observation_status=OBSERVATION_STATUS,
        hydro_evidence=evidence,
        hydro_ensemble=ensemble,
        hydro_realization=realization,
        external_exchange=external,
        deposition_assignments=assignments,
        deposition_pools=pools,
        archaeology=archaeology,
    )


def validate_phase05(
    lineages: Sequence[Any],
    evidence: Sequence[HydroEvidenceRecord],
    ensemble: Sequence[HydroEnsembleEdge],
    realization: Sequence[HydroRealizationEdge],
    external: Sequence[ExternalExchangeRecord],
    assignments: Sequence[DepositionAssignment],
    pools: Sequence[DepositionPool],
    archaeology: Sequence[ArchaeologyObservation],
) -> None:
    particle_ids = {str(row.particle_id) for row in lineages}
    if len(assignments) != len(lineages) or len(archaeology) != len(lineages):
        raise ValueError("phase-05 requires exactly one deposition and archaeology row per lineage")
    if {row.particle_id for row in assignments} != particle_ids:
        raise ValueError("phase-05 deposition particle identity mismatch")
    if {row.particle_id for row in archaeology} != particle_ids:
        raise ValueError("phase-05 archaeology particle identity mismatch")
    if any(row.particle_id not in particle_ids for row in external):
        raise ValueError("phase-05 external exchange points outside phase-02 lineages")

    evidence_ids = {row.evidence_id for row in evidence}
    ensemble_ids = {row.edge_id for row in ensemble}
    for row in ensemble:
        if any(eid not in evidence_ids for eid in row.evidence_ids):
            raise ValueError("phase-05 hydro ensemble references unknown evidence")
        if not 0.0 <= row.probability <= 1.0:
            raise ValueError("phase-05 hydro probability outside [0,1]")
    if any(row.edge_id not in ensemble_ids for row in realization):
        raise ValueError("phase-05 hydro realization points outside ensemble")
    if any(row.structural and not row.realized for row in realization):
        raise ValueError("phase-05 structural hydro edge cannot disappear in realization")

    pool_ids = {row.deposition_pool_id for row in pools}
    if any(row.deposition_pool_id not in pool_ids for row in assignments):
        raise ValueError("phase-05 deposition assignment points outside shared pools")
    if any(row.deposition_pool_id not in pool_ids for row in archaeology):
        raise ValueError("phase-05 archaeology row points outside deposition pools")
    for row in assignments:
        if not 0.0 < row.mode_probability <= 1.0:
            raise ValueError("phase-05 deposition mode probability invalid")
        if abs(sum(row.mode_weights.values()) - 1.0) > 1e-10:
            raise ValueError("phase-05 deposition mode weights are not normalized")
    for row in archaeology:
        if not (0.0 <= row.recorded_weight <= row.discovery_weight <= row.survival_weight <= row.represented_loss_weight + 1e-12):
            raise ValueError("phase-05 observation waterfall is not monotone")


def flatten_phase05(layer: Phase05Layer) -> dict[str, list[dict[str, Any]]]:
    return {
        "hydro_evidence": [
            {
                "evidence_id": r.evidence_id,
                "a": r.a,
                "b": r.b,
                "evidence_kind": r.evidence_kind,
                "provenance": r.provenance,
                "mode": r.mode,
                "confidence": r.confidence,
                "navigability": r.navigability,
                "empirical": r.empirical,
            }
            for r in layer.hydro_evidence
        ],
        "hydro_ensemble": [
            {
                "edge_id": r.edge_id,
                "a": r.a,
                "b": r.b,
                "mode": r.mode,
                "probability": r.probability,
                "navigability": r.navigability,
                "structural": r.structural,
                "evidence_ids": list(r.evidence_ids),
                "empirical_evidence_count": r.empirical_evidence_count,
                "probability_basis": r.probability_basis,
            }
            for r in layer.hydro_ensemble
        ],
        "hydro_realization": [
            {
                "realization_id": r.realization_id,
                "edge_id": r.edge_id,
                "a": r.a,
                "b": r.b,
                "mode": r.mode,
                "realized": r.realized,
                "draw": r.draw,
                "probability": r.probability,
                "navigability": r.navigability,
                "structural": r.structural,
            }
            for r in layer.hydro_realization
        ],
        "external_exchange": [r.__dict__.copy() for r in layer.external_exchange],
        "deposition_assignments": [
            {
                **{k: v for k, v in r.__dict__.items() if k != "mode_weights"},
                "mode_weights": dict(r.mode_weights),
            }
            for r in layer.deposition_assignments
        ],
        "deposition_pools": [r.__dict__.copy() for r in layer.deposition_pools],
        "archaeology": [r.__dict__.copy() for r in layer.archaeology],
    }
