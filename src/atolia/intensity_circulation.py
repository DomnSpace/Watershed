from __future__ import annotations

import hashlib
import math
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Sequence, Tuple

import numpy as np

import provenance_field as base
import provenance_field_mediterranean as med
import temporal_directional_model as temporal
import transport_fields as fields


INTENSITY_MODEL_VERSION = "intensity-circulation-v1"

# One propagation step is an abstract transfer/use opportunity, not a fixed calendar year.
DEFAULT_STEPS = 28
MIN_ACTIVE_INTENSITY = 1e-5


@dataclass(frozen=True)
class ProductionCell:
    bundle_id: str
    bundle_family: str
    object_class: str
    date_bc: int
    origin: str
    destination: str
    production_intensity: float
    circulation_seed_intensity: float
    source_mix: Mapping[str, float]
    recycle_mean: float


@dataclass
class NodeMoments:
    intensity: float = 0.0
    recycle_events: float = 0.0
    repair_events: float = 0.0
    source_entropy_mass: float = 0.0
    field_crossing_mass: float = 0.0
    physical_crossing_mass: float = 0.0

    def add(self, other: "NodeMoments", weight: float = 1.0) -> None:
        self.intensity += other.intensity * weight
        self.recycle_events += other.recycle_events * weight
        self.repair_events += other.repair_events * weight
        self.source_entropy_mass += other.source_entropy_mass * weight
        self.field_crossing_mass += other.field_crossing_mass * weight
        self.physical_crossing_mass += other.physical_crossing_mass * weight


@dataclass(frozen=True)
class LossStratum:
    production_cell: ProductionCell
    node_id: str
    step: int
    loss_intensity: float
    deposition_mode_weights: Mapping[str, float]
    expected_recycle_count: float
    expected_repair_count: float
    expected_source_entropy: float
    expected_field_crossings: float
    expected_physical_crossings: float
    route_distance_from_origin_km: float
    field_mix: Mapping[str, float]


@dataclass
class CellFlowReport:
    production_cell: ProductionCell
    produced: float = 0.0
    circulation_seed: float = 0.0
    transfer_flux: float = 0.0
    return_flux: float = 0.0
    recycle_flux: float = 0.0
    loss_flux: float = 0.0
    retire_flux: float = 0.0
    residual_active: float = 0.0
    max_active_nodes: int = 0
    loss_strata: List[LossStratum] = field(default_factory=list)

    def conservation_error(self) -> float:
        lhs = self.circulation_seed + self.recycle_flux
        rhs = self.return_flux + self.loss_flux + self.retire_flux + self.residual_active
        return float(lhs - rhs)


def _safe_entropy(mix: Mapping[str, float]) -> float:
    vals = np.asarray([float(v) for v in mix.values() if float(v) > 0], dtype=float)
    if len(vals) <= 1:
        return 0.0
    vals /= vals.sum()
    return float(-np.sum(vals * np.log(vals)) / math.log(len(vals)))


def _physical_type(mode: str) -> str:
    m = str(mode).lower()
    if "river" in m or "lagoon" in m:
        return "river"
    if "sea" in m:
        return "sea"
    if "coast" in m:
        return "coast"
    if any(x in m for x in ("pass", "mountain", "alpine", "jura", "portage")):
        return "pass"
    return "land"


def _edge_km(world: Any, edge: Any) -> float:
    a, b = world.nodes[edge.a], world.nodes[edge.b]
    return float(base.haversine_km(a.lon, a.lat, b.lon, b.lat))


def _adjacency(world: Any) -> Dict[str, List[Tuple[str, Any]]]:
    out: Dict[str, List[Tuple[str, Any]]] = {node: [] for node in world.nodes}
    for edge in world.edges:
        out[edge.a].append((edge.b, edge))
        if not edge.directed:
            out[edge.b].append((edge.a, edge))
    return out


def _goal_distance(world: Any, node_id: str, goal_id: str) -> float:
    a, b = world.nodes[node_id], world.nodes[goal_id]
    return float(base.haversine_km(a.lon, a.lat, b.lon, b.lat))


def _route_phase(date_bc: int) -> float:
    return float(np.clip((1800.0 - float(date_bc)) / 800.0, 0.0, 1.0))


def production_cells(world: Any) -> List[ProductionCell]:
    """Convert tonnes/bundle/class/time into aggregate production intensities.

    Class multipliers are renormalized inside each bundle/time so temporal/regional
    production priors redistribute object mass without creating or destroying tonnes.
    """
    cells: List[ProductionCell] = []
    for bundle in world.bundles:
        for date_bc in world.time_slices:
            tonnes = float(bundle.flux_tonnes.get(date_bc, 0.0))
            if tonnes <= 0:
                continue
            classes, base_weights = world._class_weights(date_bc, bundle)
            classes = [str(c) for c in classes]
            raw = np.asarray([
                float(w) * temporal.production_multiplier_for_bundle(str(c), bundle, date_bc)
                for c, w in zip(classes, base_weights)
            ], dtype=float)
            if raw.sum() <= 0:
                raw[:] = 1.0
            raw /= raw.sum()
            for object_class, weight in zip(classes, raw):
                mass = float(base.OBJECT_CLASSES[object_class]["mean_kg"])
                produced = tonnes * 1000.0 * 0.48 * float(weight) / max(.01, mass)
                # The seed is first-use objects. Reuse appears explicitly through the
                # recycle hazard instead of multiplying by 1/(1-r) up front.
                cells.append(ProductionCell(
                    bundle_id=str(bundle.id), bundle_family=str(bundle.family),
                    object_class=object_class, date_bc=int(date_bc),
                    origin=str(bundle.origin), destination=str(bundle.destination),
                    production_intensity=float(produced), circulation_seed_intensity=float(produced),
                    source_mix=dict(bundle.source_mix), recycle_mean=float(bundle.recycle_mean),
                ))
    return cells


def hazard_rates(world: Any, cell: ProductionCell, node_id: str, step: int) -> Dict[str, float]:
    """Competing rates for an aggregate use/transfer opportunity.

    Rates are deliberately low per step. Local/utilitarian traffic has high return +
    recycle rates; prestige/cross-system traffic trades some return probability for
    exceptional-loss exposure.
    """
    node = world.nodes[node_id]
    region = med.REGION_BY_NODE.get(node_id, "other")
    distance = _goal_distance(world, node_id, cell.destination)
    origin_distance = _goal_distance(world, node_id, cell.origin)
    progress = origin_distance / max(1.0, origin_distance + distance)
    prestige = float(cell.object_class in {"sword", "dagger", "ornament", "figurine", "vessel", "spearhead"})
    utilitarian = float(cell.object_class in {"awl", "sickle", "chisel", "fitting", "scrap", "axe"})
    tail = float(getattr(world, "bundle_incidence", {}).get(cell.bundle_id, 1.0) < .5)
    liminal = float(node.kind in {"river", "coast", "pass", "hub"})
    destination_near = math.exp(-distance / 120.0)
    local_near = math.exp(-origin_distance / 140.0)

    h_return = .020 + .050 * utilitarian + .045 * local_near + .050 * destination_near - .012 * tail
    h_recycle = .012 + .090 * cell.recycle_mean + .035 * utilitarian + .020 * destination_near
    h_loss = .0025 + .0040 * prestige + .0045 * tail + .0030 * liminal + .0020 * min(1.0, progress)
    h_retire = .004 + .010 * destination_near + .006 * utilitarian + .002 * min(1.0, step / 20.0)

    # Maritime/liminal contexts increase exceptional loss but do not dominate economy.
    if node.kind == "coast":
        h_loss *= 1.22
    elif node.kind == "pass":
        h_loss *= 1.18
    return {
        "return": max(1e-6, h_return),
        "recycle": max(1e-6, h_recycle),
        "loss": max(1e-6, h_loss),
        "retire": max(1e-6, h_retire),
    }


def competing_probabilities(rates: Mapping[str, float], dt: float = 1.0) -> Dict[str, float]:
    total = sum(max(0.0, float(v)) for v in rates.values())
    if total <= 0:
        return {"continue": 1.0, **{k: 0.0 for k in rates}}
    survival = math.exp(-total * dt)
    event = 1.0 - survival
    out = {"continue": survival}
    for key, value in rates.items():
        out[key] = event * max(0.0, float(value)) / total
    return out


def transition_distribution(world: Any, cell: ProductionCell, node_id: str, adjacency: Mapping[str, Sequence[Tuple[str, Any]]]) -> List[Tuple[str, Any, float]]:
    neighbors = adjacency.get(node_id, ())
    if not neighbors:
        return []
    phase = _route_phase(cell.date_bc)
    mix = fields.object_field_mix(cell.object_class, cell.bundle_family, phase)
    current_goal = _goal_distance(world, node_id, cell.destination)
    logits: List[float] = []
    rows: List[Tuple[str, Any]] = []
    for nxt, edge in neighbors:
        attraction = fields.effective_edge_weight(world, edge, mix, cell.date_bc)
        direction = temporal.directional_log_bias(cell.object_class, mix, edge, node_id, nxt, cell.date_bc)
        temp = temporal.route_temperature(cell.object_class, str(edge.mode), cell.date_bc)
        km = _edge_km(world, edge)
        remaining = _goal_distance(world, nxt, cell.destination)
        progress = (current_goal - remaining) / max(80.0, current_goal)
        physical_cost = float(edge.cost) / max(12.0, km)
        # A soft destination potential; Mediterranean high temperature allows much
        # more lateral movement without making the chain an aimless random walk.
        logit = (
            math.log(max(1e-9, attraction))
            + direction
            + 2.25 * progress
            - .020 * km
            - .18 * physical_cost
        ) / max(.08, temp)
        logits.append(logit)
        rows.append((nxt, edge))
    arr = np.asarray(logits, dtype=float)
    arr -= np.max(arr)
    probs = np.exp(np.clip(arr, -40, 40)); probs /= probs.sum()
    return [(nxt, edge, float(p)) for (nxt, edge), p in zip(rows, probs)]


def _deposition_mode_weights(world: Any, cell: ProductionCell, node_id: str) -> Dict[str, float]:
    bundle = next(b for b in world.bundles if str(b.id) == cell.bundle_id)
    # Reuse the archaeology grammar only for mode proportions; no object is materialized.
    return dict(world._deposition_probabilities(cell.object_class, bundle))


def propagate_cell(world: Any, cell: ProductionCell, max_steps: int = DEFAULT_STEPS) -> CellFlowReport:
    adjacency = _adjacency(world)
    source_entropy = _safe_entropy(cell.source_mix)
    active: Dict[str, NodeMoments] = {
        cell.origin: NodeMoments(intensity=cell.circulation_seed_intensity,
                                 source_entropy_mass=cell.circulation_seed_intensity * source_entropy)
    }
    report = CellFlowReport(production_cell=cell, produced=cell.production_intensity,
                            circulation_seed=cell.circulation_seed_intensity)
    # Approximate travelled distance per active packet, used only for loss-stratum diagnostics.
    travelled: Dict[str, float] = {cell.origin: 0.0}

    for step in range(max_steps):
        if not active:
            break
        report.max_active_nodes = max(report.max_active_nodes, len(active))
        nxt_active: Dict[str, NodeMoments] = defaultdict(NodeMoments)
        nxt_travelled_mass: Dict[str, float] = defaultdict(float)
        nxt_intensity_mass: Dict[str, float] = defaultdict(float)

        for node_id, moments in active.items():
            n = float(moments.intensity)
            if n < MIN_ACTIVE_INTENSITY:
                report.retire_flux += n
                continue
            rates = hazard_rates(world, cell, node_id, step)
            probs = competing_probabilities(rates)
            ret = n * probs["return"]
            rec = n * probs["recycle"]
            loss = n * probs["loss"]
            retire = n * probs["retire"]
            cont = n * probs["continue"]
            report.return_flux += ret
            report.recycle_flux += rec
            report.loss_flux += loss
            report.retire_flux += retire

            # Recycling is local re-entry with accumulated recycling/repair moments.
            if rec > MIN_ACTIVE_INTENSITY:
                avg_recycle = moments.recycle_events / max(n, 1e-12)
                avg_repair = moments.repair_events / max(n, 1e-12)
                avg_entropy = moments.source_entropy_mass / max(n, 1e-12)
                avg_fc = moments.field_crossing_mass / max(n, 1e-12)
                avg_pc = moments.physical_crossing_mass / max(n, 1e-12)
                re = NodeMoments(
                    intensity=rec,
                    recycle_events=rec * (avg_recycle + 1.0),
                    repair_events=rec * (avg_repair + .18 + .22 * float(cell.object_class in {"sword", "dagger", "axe", "vessel"})),
                    source_entropy_mass=rec * min(1.0, avg_entropy + .025 + .035 * cell.recycle_mean),
                    field_crossing_mass=rec * avg_fc,
                    physical_crossing_mass=rec * avg_pc,
                )
                nxt_active[node_id].add(re)
                nxt_travelled_mass[node_id] += travelled.get(node_id, 0.0) * rec
                nxt_intensity_mass[node_id] += rec

            if loss > MIN_ACTIVE_INTENSITY:
                avg_recycle = moments.recycle_events / max(n, 1e-12)
                avg_repair = moments.repair_events / max(n, 1e-12)
                avg_entropy = moments.source_entropy_mass / max(n, 1e-12)
                avg_fc = moments.field_crossing_mass / max(n, 1e-12)
                avg_pc = moments.physical_crossing_mass / max(n, 1e-12)
                report.loss_strata.append(LossStratum(
                    production_cell=cell, node_id=node_id, step=step, loss_intensity=loss,
                    deposition_mode_weights=_deposition_mode_weights(world, cell, node_id),
                    expected_recycle_count=avg_recycle, expected_repair_count=avg_repair,
                    expected_source_entropy=avg_entropy, expected_field_crossings=avg_fc,
                    expected_physical_crossings=avg_pc,
                    route_distance_from_origin_km=travelled.get(node_id, 0.0),
                    field_mix=fields.object_field_mix(cell.object_class, cell.bundle_family, _route_phase(cell.date_bc)),
                ))

            if cont <= MIN_ACTIVE_INTENSITY:
                continue
            transitions = transition_distribution(world, cell, node_id, adjacency)
            if not transitions:
                report.retire_flux += cont
                continue
            report.transfer_flux += cont
            cur_ptype = None
            for target, edge, p in transitions:
                flow = cont * p
                if flow <= MIN_ACTIVE_INTENSITY:
                    continue
                avg_recycle = moments.recycle_events / max(n, 1e-12)
                avg_repair = moments.repair_events / max(n, 1e-12)
                avg_entropy = moments.source_entropy_mass / max(n, 1e-12)
                avg_fc = moments.field_crossing_mass / max(n, 1e-12)
                avg_pc = moments.physical_crossing_mass / max(n, 1e-12)
                ptype = _physical_type(str(edge.mode))
                physical_inc = float(ptype != "land") * .08
                sig = fields.field_signature(world, edge, fields.object_field_mix(cell.object_class, cell.bundle_family, _route_phase(cell.date_bc)), cell.date_bc)
                field_inc = float(1.0 - np.max(sig)) * .08
                moved = NodeMoments(
                    intensity=flow,
                    recycle_events=flow * avg_recycle,
                    repair_events=flow * avg_repair,
                    source_entropy_mass=flow * avg_entropy,
                    field_crossing_mass=flow * (avg_fc + field_inc),
                    physical_crossing_mass=flow * (avg_pc + physical_inc),
                )
                nxt_active[target].add(moved)
                d = travelled.get(node_id, 0.0) + _edge_km(world, edge)
                nxt_travelled_mass[target] += d * flow
                nxt_intensity_mass[target] += flow

        active = {k: v for k, v in nxt_active.items() if v.intensity >= MIN_ACTIVE_INTENSITY}
        travelled = {
            k: nxt_travelled_mass[k] / max(1e-12, nxt_intensity_mass[k])
            for k in active
        }

    report.residual_active = sum(v.intensity for v in active.values())
    return report


def propagate_world(world: Any, max_steps: int = DEFAULT_STEPS) -> Tuple[List[CellFlowReport], Dict[str, Any]]:
    cells = production_cells(world)
    reports: List[CellFlowReport] = []
    totals = defaultdict(float)
    strata = 0
    for cell in cells:
        r = propagate_cell(world, cell, max_steps=max_steps)
        reports.append(r)
        totals["produced"] += r.produced
        totals["circulation_seed"] += r.circulation_seed
        totals["transfer_flux"] += r.transfer_flux
        totals["return_flux"] += r.return_flux
        totals["recycle_flux"] += r.recycle_flux
        totals["loss_flux"] += r.loss_flux
        totals["retire_flux"] += r.retire_flux
        totals["residual_active"] += r.residual_active
        strata += len(r.loss_strata)
    conservation = totals["circulation_seed"] + totals["recycle_flux"] - (
        totals["return_flux"] + totals["loss_flux"] + totals["retire_flux"] + totals["residual_active"]
    )
    summary = {
        "model_version": INTENSITY_MODEL_VERSION,
        "production_cells": len(cells),
        "loss_strata": strata,
        **{k: float(v) for k, v in totals.items()},
        "conservation_error": float(conservation),
        "relative_conservation_error": float(conservation / max(1.0, totals["circulation_seed"] + totals["recycle_flux"])),
    }
    return reports, summary
