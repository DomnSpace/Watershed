from __future__ import annotations

"""Deterministic medium-cohort selection and preservation diagnostics for Atolia v3.

Phase 06 adds no new hidden-world mechanism.  It chooses a bounded, explicit
stratified subset of the already-defined v1 ProductionCell population, carries
Horvitz-style reconstruction weights, and validates that the subset preserves
important exact production distributions and downstream biography/deposition
structure against a separate deterministic probe cohort.

The selector never changes ProductionCell values.  Every selected row retains the
original global production-cell index so Phase-02 particle identities are the
same identities that the later full build will produce.
"""

from dataclasses import dataclass
import hashlib
import math
from typing import Any, Iterable, Mapping, Sequence

import provenance_field as base


PHASE06_MODEL_VERSION = "atolia-v3-medium-stratified-v1"
SELECTION_POLICY = "deterministic-stratified-uniform-within-stratum-v1"
PROBE_POLICY = "independent-deterministic-uniform-cell-probe-v1"
DEFAULT_MEDIUM_CELLS = 2048
DEFAULT_PROBE_CELLS = 384
DEFAULT_CHUNK_CELLS = 256

PRESTIGE_CLASSES = {"sword", "dagger", "ornament", "figurine", "vessel", "spearhead"}
UTILITARIAN_CLASSES = {"awl", "sickle", "chisel", "fitting", "scrap", "axe", "ingot", "knife"}


@dataclass(frozen=True)
class CellFrameRow:
    global_cell_index: int
    bundle_family: str
    object_class: str
    class_group: str
    date_bc: int
    date_band: str
    origin: str
    destination: str
    od_distance_km: float
    distance_band: str
    source_entropy: float
    entropy_band: str
    recycle_mean: float
    recycle_band: str
    production_intensity: float
    stratum_id: str
    tail_score: int


@dataclass(frozen=True)
class StratumAllocation:
    stratum_id: str
    population_cells: int
    selected_cells: int
    population_production_intensity: float


@dataclass(frozen=True)
class SelectedCell:
    local_cell_index: int
    global_cell_index: int
    stratum_id: str
    inclusion_probability: float
    reconstruction_weight: float
    tail_score: int


@dataclass(frozen=True)
class SelectionPlan:
    population_cells: int
    target_cells: int
    selected: tuple[SelectedCell, ...]
    strata: tuple[StratumAllocation, ...]


def _seed64(*parts: object) -> int:
    raw = "|".join(str(part) for part in parts).encode("utf-8")
    return int.from_bytes(hashlib.sha256(raw).digest()[:8], "big")


def _hash_rank(*parts: object) -> tuple[int, str]:
    raw = "|".join(str(part) for part in parts).encode("utf-8")
    digest = hashlib.sha256(raw).hexdigest()
    return int(digest[:16], 16), digest


def _source_entropy(mix: Mapping[str, float]) -> float:
    vals = [max(0.0, float(v)) for v in mix.values() if float(v) > 0.0]
    if len(vals) <= 1:
        return 0.0
    total = sum(vals)
    p = [v / total for v in vals]
    return float(-sum(x * math.log(x) for x in p) / math.log(len(p)))


def _class_group(object_class: str) -> str:
    if object_class in PRESTIGE_CLASSES:
        return "prestige"
    if object_class in UTILITARIAN_CLASSES:
        return "utilitarian"
    return "other"


def _date_band(date_bc: int) -> str:
    # Stable 200-year bins, descending labels for the 1800--1000 BCE world.
    hi = ((int(date_bc) + 199) // 200) * 200
    lo = hi - 199
    return f"{hi}-{lo}BC"


def distance_band(km: float) -> str:
    x = max(0.0, float(km))
    if x < 100.0:
        return "0-100"
    if x < 300.0:
        return "100-300"
    if x < 700.0:
        return "300-700"
    if x < 1400.0:
        return "700-1400"
    return "1400+"


def entropy_band(value: float) -> str:
    x = max(0.0, min(1.0, float(value)))
    if x < .20:
        return "low"
    if x < .55:
        return "medium"
    return "high"


def recycle_band(value: float) -> str:
    x = max(0.0, float(value))
    if x < .10:
        return "low"
    if x < .30:
        return "medium"
    return "high"


def count_band(value: float) -> str:
    x = max(0.0, float(value))
    if x < .5:
        return "0"
    if x < 1.5:
        return "1"
    if x < 2.5:
        return "2"
    return "3+"


def crossing_band(value: float) -> str:
    x = max(0.0, float(value))
    if x < .25:
        return "0"
    if x < 1.25:
        return "1"
    if x < 2.25:
        return "2"
    return "3+"


def build_cell_frame(world: Any, cells: Sequence[Any]) -> tuple[CellFrameRow, ...]:
    rows: list[CellFrameRow] = []
    for index, cell in enumerate(cells):
        a = world.nodes[str(cell.origin)]
        b = world.nodes[str(cell.destination)]
        km = float(base.haversine_km(a.lon, a.lat, b.lon, b.lat))
        entropy = _source_entropy(cell.source_mix)
        cgroup = _class_group(str(cell.object_class))
        dband = distance_band(km)
        eband = entropy_band(entropy)
        rband = recycle_band(float(cell.recycle_mean))
        tband = _date_band(int(cell.date_bc))
        stratum_text = "|".join((tband, cgroup, dband, eband, rband))
        stratum_id = "ms_" + hashlib.sha256(stratum_text.encode("utf-8")).hexdigest()[:16]
        tail_score = (
            int(dband in {"700-1400", "1400+"})
            + int(eband == "high")
            + int(rband == "high")
            + int(cgroup == "prestige")
        )
        rows.append(CellFrameRow(
            global_cell_index=index,
            bundle_family=str(cell.bundle_family),
            object_class=str(cell.object_class),
            class_group=cgroup,
            date_bc=int(cell.date_bc),
            date_band=tband,
            origin=str(cell.origin),
            destination=str(cell.destination),
            od_distance_km=km,
            distance_band=dband,
            source_entropy=entropy,
            entropy_band=eband,
            recycle_mean=float(cell.recycle_mean),
            recycle_band=rband,
            production_intensity=float(cell.production_intensity),
            stratum_id=stratum_id,
            tail_score=tail_score,
        ))
    return tuple(rows)


def _allocate_quotas(
    frame: Sequence[CellFrameRow],
    target_cells: int,
) -> dict[str, int]:
    if target_cells <= 0:
        raise ValueError("target_cells must be positive")
    target = min(int(target_cells), len(frame))
    by_stratum: dict[str, list[CellFrameRow]] = {}
    for row in frame:
        by_stratum.setdefault(row.stratum_id, []).append(row)
    if not by_stratum:
        return {}

    strata = sorted(by_stratum)
    quotas = {key: 0 for key in strata}
    if target >= len(strata):
        for key in strata:
            quotas[key] = 1
        remaining = target - len(strata)
    else:
        # If the requested target is pathologically smaller than the number of
        # occupied strata, retain the rare/tail-heavy strata first.
        ranked = sorted(
            strata,
            key=lambda key: (
                -max(row.tail_score for row in by_stratum[key]),
                len(by_stratum[key]),
                key,
            ),
        )
        for key in ranked[:target]:
            quotas[key] = 1
        return quotas

    if remaining <= 0:
        return quotas

    # sqrt(population production mass) prevents the largest ordinary strata from
    # consuming the whole budget while still allocating most rows where the world
    # actually carries intensity.
    capacity = {key: len(by_stratum[key]) - quotas[key] for key in strata}
    while remaining > 0 and any(value > 0 for value in capacity.values()):
        active = [key for key in strata if capacity[key] > 0]
        weights = {
            key: math.sqrt(max(1e-30, sum(r.production_intensity for r in by_stratum[key])))
            * (1.0 + .18 * max(r.tail_score for r in by_stratum[key]))
            for key in active
        }
        total = sum(weights.values()) or float(len(active))
        raw = {key: remaining * weights[key] / total for key in active}
        added = 0
        for key in active:
            take = min(capacity[key], int(math.floor(raw[key])))
            if take > 0:
                quotas[key] += take
                capacity[key] -= take
                remaining -= take
                added += take
        if remaining <= 0:
            break
        # Deterministic largest remainder, one row at a time.
        ranked = sorted(
            (key for key in active if capacity[key] > 0),
            key=lambda key: (-(raw[key] - math.floor(raw[key])), key),
        )
        if not ranked:
            break
        for key in ranked:
            if remaining <= 0:
                break
            quotas[key] += 1
            capacity[key] -= 1
            remaining -= 1
            added += 1
        if added == 0:
            break
    return quotas


def select_medium_cohort(
    frame: Sequence[CellFrameRow],
    *,
    target_cells: int = DEFAULT_MEDIUM_CELLS,
    seed: int = 1300,
) -> SelectionPlan:
    if not frame:
        return SelectionPlan(0, 0, (), ())
    quotas = _allocate_quotas(frame, target_cells)
    by_stratum: dict[str, list[CellFrameRow]] = {}
    for row in frame:
        by_stratum.setdefault(row.stratum_id, []).append(row)

    selected_rows: list[tuple[CellFrameRow, float]] = []
    strata_rows: list[StratumAllocation] = []
    for stratum_id in sorted(by_stratum):
        population = by_stratum[stratum_id]
        quota = min(len(population), int(quotas.get(stratum_id, 0)))
        ranked = sorted(
            population,
            key=lambda row: _hash_rank(
                PHASE06_MODEL_VERSION,
                seed,
                "medium",
                stratum_id,
                row.global_cell_index,
            ),
        )
        inclusion = float(quota / len(population)) if quota else 0.0
        for row in ranked[:quota]:
            selected_rows.append((row, inclusion))
        strata_rows.append(StratumAllocation(
            stratum_id=stratum_id,
            population_cells=len(population),
            selected_cells=quota,
            population_production_intensity=float(sum(r.production_intensity for r in population)),
        ))

    # Global-index order makes the selected phase-01 slice stable and easy to map.
    selected_rows.sort(key=lambda item: item[0].global_cell_index)
    selected = tuple(
        SelectedCell(
            local_cell_index=local,
            global_cell_index=row.global_cell_index,
            stratum_id=row.stratum_id,
            inclusion_probability=inclusion,
            reconstruction_weight=(1.0 / inclusion if inclusion > 0.0 else math.inf),
            tail_score=row.tail_score,
        )
        for local, (row, inclusion) in enumerate(selected_rows)
    )
    return SelectionPlan(
        population_cells=len(frame),
        target_cells=len(selected),
        selected=selected,
        strata=tuple(strata_rows),
    )


def select_probe_indices(
    population_cells: int,
    *,
    probe_cells: int = DEFAULT_PROBE_CELLS,
    seed: int = 1300,
) -> tuple[int, ...]:
    if population_cells <= 0 or probe_cells <= 0:
        return ()
    n = min(int(probe_cells), int(population_cells))
    ranked = sorted(
        range(int(population_cells)),
        key=lambda index: _hash_rank(PHASE06_MODEL_VERSION, seed, "probe", index),
    )
    return tuple(sorted(ranked[:n]))


def _normalize(counts: Mapping[str, float]) -> dict[str, float]:
    total = sum(max(0.0, float(v)) for v in counts.values())
    if total <= 0.0:
        return {}
    return {str(k): max(0.0, float(v)) / total for k, v in sorted(counts.items())}


def _tv(p: Mapping[str, float], q: Mapping[str, float]) -> float:
    keys = set(p) | set(q)
    return .5 * sum(abs(float(p.get(k, 0.0)) - float(q.get(k, 0.0))) for k in keys)


def _js(p: Mapping[str, float], q: Mapping[str, float]) -> float:
    keys = set(p) | set(q)
    if not keys:
        return 0.0
    pp = {k: float(p.get(k, 0.0)) for k in keys}
    qq = {k: float(q.get(k, 0.0)) for k in keys}
    mm = {k: .5 * (pp[k] + qq[k]) for k in keys}

    def kl(a: Mapping[str, float], b: Mapping[str, float]) -> float:
        return sum(x * math.log(x / b[k]) for k, x in a.items() if x > 0.0 and b[k] > 0.0)

    return .5 * kl(pp, mm) + .5 * kl(qq, mm)


def _production_features(row: CellFrameRow) -> dict[str, str]:
    return {
        "object_class": row.object_class,
        "date_band": row.date_band,
        "distance_band": row.distance_band,
        "source_entropy": row.entropy_band,
        "recycle_band": row.recycle_band,
        "class_x_distance": f"{row.class_group}|{row.distance_band}",
        "date_x_class": f"{row.date_band}|{row.class_group}",
        "entropy_x_distance": f"{row.entropy_band}|{row.distance_band}",
    }


def production_preservation(
    frame: Sequence[CellFrameRow],
    plan: SelectionPlan,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    by_index = {row.global_cell_index: row for row in frame}
    exact: dict[str, dict[str, float]] = {}
    estimate: dict[str, dict[str, float]] = {}
    for row in frame:
        for axis, value in _production_features(row).items():
            exact.setdefault(axis, {})[value] = exact.setdefault(axis, {}).get(value, 0.0) + row.production_intensity
    for selected in plan.selected:
        row = by_index[selected.global_cell_index]
        w = row.production_intensity * selected.reconstruction_weight
        for axis, value in _production_features(row).items():
            estimate.setdefault(axis, {})[value] = estimate.setdefault(axis, {}).get(value, 0.0) + w

    metrics: list[dict[str, Any]] = []
    for axis in sorted(exact):
        p = _normalize(exact[axis])
        q = _normalize(estimate.get(axis, {}))
        metrics.append({"stage": "production_exact", "axis": axis, "metric": "total_variation", "value": _tv(p, q), "threshold": .08})
        metrics.append({"stage": "production_exact", "axis": axis, "metric": "jensen_shannon", "value": _js(p, q), "threshold": .035})
    for row in metrics:
        row["passed"] = bool(float(row["value"]) <= float(row["threshold"]))
    return metrics, {
        "axes": len(exact),
        "max_total_variation": max((r["value"] for r in metrics if r["metric"] == "total_variation"), default=0.0),
        "max_jensen_shannon": max((r["value"] for r in metrics if r["metric"] == "jensen_shannon"), default=0.0),
        "all_passed": all(bool(r["passed"]) for r in metrics),
    }


def downstream_feature_rows(
    lineages: Sequence[Any],
    phase05_layer: Any,
    inclusion_probability_by_cell: Mapping[int, float],
) -> list[dict[str, Any]]:
    assignments = {row.particle_id: row for row in phase05_layer.deposition_assignments}
    external_particles = {row.particle_id for row in phase05_layer.external_exchange}
    rows: list[dict[str, Any]] = []
    for lineage in lineages:
        p = float(inclusion_probability_by_cell[int(lineage.production_cell_index)])
        if p <= 0.0:
            raise ValueError("downstream preservation requires positive cell inclusion probability")
        dep = assignments[str(lineage.particle_id)]
        features = {
            "object_class": str(lineage.object_class),
            "distance_band": distance_band(float(lineage.cumulative_metal_distance_km)),
            "remelt_band": count_band(float(lineage.remelt_count)),
            "repair_band": count_band(float(lineage.repair_count)),
            "source_entropy": entropy_band(float(lineage.source_entropy)),
            "deposition_mode": str(dep.mode),
            "physical_crossings": crossing_band(float(dep.expected_physical_crossings)),
            "field_crossings": crossing_band(float(dep.expected_field_crossings)),
            "external_exchange": "yes" if str(lineage.particle_id) in external_particles else "no",
        }
        features["distance_x_remelt"] = f"{features['distance_band']}|{features['remelt_band']}"
        features["distance_x_deposition"] = f"{features['distance_band']}|{features['deposition_mode']}"
        features["entropy_x_remelt"] = f"{features['source_entropy']}|{features['remelt_band']}"
        rows.append({
            "weight": float(lineage.represented_weight) / p,
            "features": features,
        })
    return rows


def _distribution_from_feature_rows(rows: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, float]]:
    counts: dict[str, dict[str, float]] = {}
    for row in rows:
        weight = max(0.0, float(row["weight"]))
        for axis, value in row["features"].items():
            counts.setdefault(str(axis), {})[str(value)] = counts.setdefault(str(axis), {}).get(str(value), 0.0) + weight
    return {axis: _normalize(values) for axis, values in counts.items()}


def downstream_preservation(
    medium_rows: Sequence[Mapping[str, Any]],
    probe_rows: Sequence[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    medium = _distribution_from_feature_rows(medium_rows)
    probe = _distribution_from_feature_rows(probe_rows)
    metrics: list[dict[str, Any]] = []
    for axis in sorted(set(medium) & set(probe)):
        metrics.append({"stage": "downstream_probe", "axis": axis, "metric": "total_variation", "value": _tv(probe[axis], medium[axis]), "threshold": .22})
        metrics.append({"stage": "downstream_probe", "axis": axis, "metric": "jensen_shannon", "value": _js(probe[axis], medium[axis]), "threshold": .10})
    for row in metrics:
        row["passed"] = bool(float(row["value"]) <= float(row["threshold"]))
    return metrics, {
        "axes": len(set(medium) & set(probe)),
        "max_total_variation": max((r["value"] for r in metrics if r["metric"] == "total_variation"), default=0.0),
        "max_jensen_shannon": max((r["value"] for r in metrics if r["metric"] == "jensen_shannon"), default=0.0),
        "all_passed": all(bool(r["passed"]) for r in metrics),
    }


def chunked(values: Sequence[Any], size: int = DEFAULT_CHUNK_CELLS) -> Iterable[Sequence[Any]]:
    if size <= 0:
        raise ValueError("chunk size must be positive")
    for start in range(0, len(values), int(size)):
        yield values[start:start + int(size)]
