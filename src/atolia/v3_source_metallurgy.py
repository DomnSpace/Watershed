from __future__ import annotations

"""Atolia v3 phase-03 source geochemistry and metallurgy.

Phase 03 is downstream of the phase-02 metal genealogy. It does not alter
circulation, loss strata, batch identities, parent links or object episodes.

Conservation rule:
- store elemental masses, not wt%;
- store Pb isotope masses, not isotope ratios;
- derive concentrations and ratios only as views;
- a remelt child receives the contribution-scaled inventories of its phase-02
  parents exactly.

The repository does not yet contain the empirical covariance/source database
specified in the Step-3 preparation note. Therefore the source model below is
explicitly marked as a provisional legacy calibration: the v1 source trace/Pb
ratio means are frozen as means and Pb carrier concentrations are frozen,
auditable priors. No independent "noise" is added and no covariance is invented.
"""

from dataclasses import dataclass
import hashlib
import math
from typing import Any, Mapping, Sequence

import provenance_field as base
import v3_metal_biography as biography


SOURCE_METALLURGY_VERSION = "atolia-v3-source-metallurgy-v1"
SOURCE_CALIBRATION_STATUS = "provisional-legacy-v1-means-no-empirical-covariance"
PROCESS_RECIPE_STATUS = "provisional-object-class-alloy-prior-v1"

ELEMENTS = (
    "Cu", "Sn", "As", "Pb", "Ag", "Fe", "Zn", "Sb", "Ni", "Co", "Bi",
)
PB_ISOTOPES = ("Pb204", "Pb206", "Pb207", "Pb208")
PB_MASS_NUMBERS = {"Pb204": 204.0, "Pb206": 206.0, "Pb207": 207.0, "Pb208": 208.0}

TRACE_TO_ELEMENT = {
    "Sb_ppm": "Sb",
    "Ag_ppm": "Ag",
    "Ni_ppm": "Ni",
    "Co_ppm": "Co",
    "Bi_ppm": "Bi",
}

# Frozen values from the v2 fallback prior, generated once with calibration seed
# 20260830 and committed here so a world build never silently resamples geology.
# They are *not* presented as measurements.
FROZEN_PB_PPM_PRIOR = {
    "trentino_east": 2435.918,
    "upper_atesis": 933.918,
    "veneto_pre_alps": 3942.915,
    "eastern_alps_external": 688.694,
    "tyrrhenian_apennine": 2126.849,
    "ligurian_tuscany": 2842.998,
    "balkan_import": 1347.832,
}


@dataclass(frozen=True)
class SourceChemistry:
    source_id: str
    label: str
    pb_ppm: float
    trace_ppm: Mapping[str, float]
    pb_ratios: Mapping[str, float]
    calibration_status: str = SOURCE_CALIBRATION_STATUS


@dataclass(frozen=True)
class BatchChemistry:
    batch_id: str
    particle_id: str
    metal_mass_kg: float
    element_mass_kg: Mapping[str, float]
    pb_isotope_mass_kg: Mapping[str, float]
    source_pb_mass_kg: Mapping[str, float]
    recipe_status: str = PROCESS_RECIPE_STATUS

    @property
    def pb_mass_kg(self) -> float:
        return float(sum(self.pb_isotope_mass_kg.values()))


@dataclass(frozen=True)
class MetallurgyLineage:
    particle_id: str
    batches: tuple[BatchChemistry, ...]
    final_batch_id: str


def _stable_u01(*parts: object) -> float:
    raw = "|".join(str(p) for p in parts).encode("utf-8")
    x = int.from_bytes(hashlib.sha256(raw).digest()[:8], "big")
    return (x + 0.5) / 2**64


def source_chemistry_table(world: Any) -> dict[str, SourceChemistry]:
    out: dict[str, SourceChemistry] = {}
    for source_id, src in sorted(world.sources.items()):
        trace_ppm = {
            TRACE_TO_ELEMENT[k]: max(0.0, float(v))
            for k, v in src.trace_mean.items()
            if k in TRACE_TO_ELEMENT
        }
        ratios = {
            "Pb206_204": float(src.isotope_mean["Pb206_204"]),
            "Pb207_204": float(src.isotope_mean["Pb207_204"]),
            "Pb208_204": float(src.isotope_mean["Pb208_204"]),
        }
        pb_ppm = float(FROZEN_PB_PPM_PRIOR.get(source_id, 550.0))
        out[source_id] = SourceChemistry(
            source_id=str(source_id),
            label=str(src.label),
            pb_ppm=pb_ppm,
            trace_ppm=trace_ppm,
            pb_ratios=ratios,
        )
    return out


def pb_inventory_from_ratios(
    pb_mass_kg: float, ratios: Mapping[str, float]
) -> dict[str, float]:
    """Convert atomic Pb ratios to isotope masses that sum to pb_mass_kg."""
    total_mass = max(0.0, float(pb_mass_kg))
    if total_mass == 0.0:
        return {name: 0.0 for name in PB_ISOTOPES}
    atom_rel = {
        "Pb204": 1.0,
        "Pb206": max(0.0, float(ratios["Pb206_204"])),
        "Pb207": max(0.0, float(ratios["Pb207_204"])),
        "Pb208": max(0.0, float(ratios["Pb208_204"])),
    }
    weighted = {
        iso: atom_rel[iso] * PB_MASS_NUMBERS[iso] for iso in PB_ISOTOPES
    }
    denom = sum(weighted.values())
    if denom <= 0.0:
        raise ValueError("Pb isotope ratios produce zero isotope inventory")
    return {iso: total_mass * weighted[iso] / denom for iso in PB_ISOTOPES}


def pb_ratios_from_inventory(inventory: Mapping[str, float]) -> dict[str, float]:
    n204 = max(0.0, float(inventory.get("Pb204", 0.0))) / PB_MASS_NUMBERS["Pb204"]
    if n204 <= 0.0:
        return {
            "Pb206_204": math.nan,
            "Pb207_204": math.nan,
            "Pb208_204": math.nan,
        }
    return {
        "Pb206_204": (max(0.0, float(inventory.get("Pb206", 0.0))) / 206.0) / n204,
        "Pb207_204": (max(0.0, float(inventory.get("Pb207", 0.0))) / 207.0) / n204,
        "Pb208_204": (max(0.0, float(inventory.get("Pb208", 0.0))) / 208.0) / n204,
    }


_TIN_AFFINITY = {
    "sword": 1.30, "dagger": 1.20, "spearhead": 1.15, "axe": 1.05,
    "chisel": .95, "sickle": .92, "knife": .92, "vessel": 1.05,
    "ornament": .90, "figurine": .90, "fitting": .85, "ring": .72,
    "pin": .70, "bead": .55, "awl": .70, "ingot": .80, "scrap": .82,
}


def _alloy_fractions(
    object_class: str,
    date_bc: int,
    recycle_generation: int,
    role: str,
    particle_id: str,
) -> dict[str, float]:
    """Transparent process prior; not a source-provenance model."""
    late = min(1.0, max(0.0, (1800.0 - float(date_bc)) / 800.0))
    affinity = _TIN_AFFINITY.get(str(object_class), .85)
    # Small deterministic spread avoids every same-class packet being identical
    # without pretending it is an empirical source covariance.
    jitter = 0.92 + 0.16 * _stable_u01(
        SOURCE_METALLURGY_VERSION, particle_id, recycle_generation, role, "alloy"
    )
    sn = min(.145, max(.006, (.055 + .025 * late) * affinity * jitter))
    arsenic = min(.022, max(.0010, (.0070 - .0030 * late + .0015 * recycle_generation) / jitter))
    fe = min(.006, .0008 * (2.0 - jitter))
    zn = min(.004, .00035 * (1.5 - .5 * late) * jitter)
    return {"Sn": sn, "As": arsenic, "Fe": fe, "Zn": zn}


def _source_weighted_packets(
    batch: biography.MetalBatchState,
    sources: Mapping[str, SourceChemistry],
) -> tuple[dict[str, float], dict[str, float], dict[str, float]]:
    """Return source-derived trace masses, Pb isotope masses and source Pb masses."""
    traces = {element: 0.0 for element in TRACE_TO_ELEMENT.values()}
    pb_inv = {iso: 0.0 for iso in PB_ISOTOPES}
    source_pb: dict[str, float] = {}
    for source_id, source_metal_mass in batch.ancestry_mass_kg.items():
        source = sources.get(source_id)
        if source is None:
            continue
        carrier_mass = max(0.0, float(source_metal_mass))
        pb_mass = carrier_mass * max(0.0, source.pb_ppm) * 1e-6
        source_pb[source_id] = source_pb.get(source_id, 0.0) + pb_mass
        inv = pb_inventory_from_ratios(pb_mass, source.pb_ratios)
        for iso, value in inv.items():
            pb_inv[iso] += value
        for element, ppm in source.trace_ppm.items():
            traces[element] = traces.get(element, 0.0) + carrier_mass * max(0.0, ppm) * 1e-6
    return traces, pb_inv, source_pb


def _new_packet_chemistry(
    lineage: biography.MetalLineage,
    batch: biography.MetalBatchState,
    sources: Mapping[str, SourceChemistry],
) -> BatchChemistry:
    """Chemistry for a root/addition batch that has no phase-02 parents."""
    traces, pb_inv, source_pb = _source_weighted_packets(batch, sources)
    fractions = _alloy_fractions(
        lineage.object_class,
        batch.date_bc,
        batch.recycle_generation,
        batch.role,
        lineage.particle_id,
    )
    elements = {name: 0.0 for name in ELEMENTS}
    for element, value in traces.items():
        if element in elements:
            elements[element] += float(value)
    elements["Pb"] = sum(pb_inv.values())
    for element, fraction in fractions.items():
        elements[element] += float(batch.metal_mass_kg) * fraction

    non_cu = sum(v for k, v in elements.items() if k != "Cu")
    if non_cu >= batch.metal_mass_kg:
        raise ValueError(
            f"non-Cu chemistry exceeds batch mass for {batch.batch_id}: "
            f"{non_cu} >= {batch.metal_mass_kg}"
        )
    elements["Cu"] = float(batch.metal_mass_kg) - non_cu
    return BatchChemistry(
        batch_id=batch.batch_id,
        particle_id=batch.particle_id,
        metal_mass_kg=float(batch.metal_mass_kg),
        element_mass_kg=elements,
        pb_isotope_mass_kg=pb_inv,
        source_pb_mass_kg=source_pb,
    )


def _scaled_add(target: dict[str, float], values: Mapping[str, float], scale: float) -> None:
    for key, value in values.items():
        target[key] = target.get(key, 0.0) + float(value) * float(scale)


def _child_chemistry(
    batch: biography.MetalBatchState,
    parents: Mapping[str, BatchChemistry],
) -> BatchChemistry:
    elements = {name: 0.0 for name in ELEMENTS}
    pb_inv = {iso: 0.0 for iso in PB_ISOTOPES}
    source_pb: dict[str, float] = {}
    for parent_id, contribution_kg in batch.parent_contributions_kg.items():
        parent = parents[parent_id]
        scale = float(contribution_kg) / float(parent.metal_mass_kg)
        _scaled_add(elements, parent.element_mass_kg, scale)
        _scaled_add(pb_inv, parent.pb_isotope_mass_kg, scale)
        _scaled_add(source_pb, parent.source_pb_mass_kg, scale)
    return BatchChemistry(
        batch_id=batch.batch_id,
        particle_id=batch.particle_id,
        metal_mass_kg=float(batch.metal_mass_kg),
        element_mass_kg=elements,
        pb_isotope_mass_kg=pb_inv,
        source_pb_mass_kg=source_pb,
    )


def validate_batch_chemistry(
    batch: BatchChemistry,
    *,
    tolerance: float = 1e-10,
) -> None:
    if batch.metal_mass_kg <= 0.0 or not math.isfinite(batch.metal_mass_kg):
        raise ValueError("chemistry batch mass must be positive and finite")
    if set(batch.element_mass_kg) != set(ELEMENTS):
        raise ValueError("chemistry element basis mismatch")
    if set(batch.pb_isotope_mass_kg) != set(PB_ISOTOPES):
        raise ValueError("Pb isotope basis mismatch")
    if any((not math.isfinite(float(v))) or float(v) < 0.0 for v in batch.element_mass_kg.values()):
        raise ValueError("invalid element mass")
    if any((not math.isfinite(float(v))) or float(v) < 0.0 for v in batch.pb_isotope_mass_kg.values()):
        raise ValueError("invalid Pb isotope mass")
    element_sum = sum(float(v) for v in batch.element_mass_kg.values())
    if abs(element_sum - batch.metal_mass_kg) > max(tolerance, batch.metal_mass_kg * 1e-10):
        raise ValueError(
            f"element mass does not close for {batch.batch_id}: {element_sum} vs {batch.metal_mass_kg}"
        )
    pb_mass = float(batch.element_mass_kg["Pb"])
    isotope_sum = sum(float(v) for v in batch.pb_isotope_mass_kg.values())
    if abs(pb_mass - isotope_sum) > max(tolerance, max(pb_mass, 1e-12) * 1e-10):
        raise ValueError(f"Pb isotope mass does not close for {batch.batch_id}")
    source_pb_sum = sum(float(v) for v in batch.source_pb_mass_kg.values())
    if abs(pb_mass - source_pb_sum) > max(tolerance, max(pb_mass, 1e-12) * 1e-10):
        raise ValueError(f"source Pb mass does not close for {batch.batch_id}")


def materialize_metallurgy_lineage(
    world: Any,
    lineage: biography.MetalLineage,
) -> MetallurgyLineage:
    sources = source_chemistry_table(world)
    by_id: dict[str, BatchChemistry] = {}
    rows: list[BatchChemistry] = []
    for batch in lineage.batches:
        if batch.parent_contributions_kg:
            chemistry = _child_chemistry(batch, by_id)
        else:
            chemistry = _new_packet_chemistry(lineage, batch, sources)
        validate_batch_chemistry(chemistry)
        by_id[batch.batch_id] = chemistry
        rows.append(chemistry)
    if lineage.final_batch_id not in by_id:
        raise ValueError("final phase-02 batch missing from chemistry lineage")
    return MetallurgyLineage(
        particle_id=lineage.particle_id,
        batches=tuple(rows),
        final_batch_id=lineage.final_batch_id,
    )


def materialize_metallurgy(
    world: Any,
    lineages: Sequence[biography.MetalLineage],
) -> list[MetallurgyLineage]:
    return [materialize_metallurgy_lineage(world, lineage) for lineage in lineages]


def flatten_metallurgy(
    lineages: Sequence[biography.MetalLineage],
    chemistry: Sequence[MetallurgyLineage],
) -> dict[str, list[dict[str, Any]]]:
    if len(lineages) != len(chemistry):
        raise ValueError("phase-02 and phase-03 lineage counts differ")
    batches: list[dict[str, Any]] = []
    elements: list[dict[str, Any]] = []
    pb_isotopes: list[dict[str, Any]] = []
    source_pb: list[dict[str, Any]] = []
    batch_index_by_id: dict[str, int] = {}

    for lineage, chem_lineage in zip(lineages, chemistry):
        if lineage.particle_id != chem_lineage.particle_id:
            raise ValueError("particle identity mismatch between phase 02 and phase 03")
        phase2_ids = [b.batch_id for b in lineage.batches]
        phase3_ids = [b.batch_id for b in chem_lineage.batches]
        if phase2_ids != phase3_ids:
            raise ValueError("batch identity/order mismatch between phase 02 and phase 03")
        for batch in chem_lineage.batches:
            idx = len(batches)
            batch_index_by_id[batch.batch_id] = idx
            ratios = pb_ratios_from_inventory(batch.pb_isotope_mass_kg)
            dominant = None
            if batch.source_pb_mass_kg:
                dominant = max(batch.source_pb_mass_kg, key=batch.source_pb_mass_kg.get)
            batches.append({
                "chemistry_batch_index": idx,
                "batch_id": batch.batch_id,
                "particle_id": batch.particle_id,
                "metal_mass_kg": float(batch.metal_mass_kg),
                "element_mass_sum_kg": float(sum(batch.element_mass_kg.values())),
                "pb_mass_kg": float(batch.element_mass_kg["Pb"]),
                "Pb206_204": float(ratios["Pb206_204"]),
                "Pb207_204": float(ratios["Pb207_204"]),
                "Pb208_204": float(ratios["Pb208_204"]),
                "pb_dominant_source_id": dominant,
                "recipe_status": batch.recipe_status,
            })
            for element in ELEMENTS:
                mass = float(batch.element_mass_kg[element])
                elements.append({
                    "element_row_index": len(elements),
                    "chemistry_batch_index": idx,
                    "element": element,
                    "mass_kg": mass,
                    "mass_fraction": mass / float(batch.metal_mass_kg),
                })
            for iso in PB_ISOTOPES:
                pb_isotopes.append({
                    "pb_isotope_row_index": len(pb_isotopes),
                    "chemistry_batch_index": idx,
                    "isotope": iso,
                    "mass_kg": float(batch.pb_isotope_mass_kg[iso]),
                })
            pb_total = max(0.0, float(batch.element_mass_kg["Pb"]))
            for source_id, mass in sorted(batch.source_pb_mass_kg.items()):
                source_pb.append({
                    "source_pb_row_index": len(source_pb),
                    "chemistry_batch_index": idx,
                    "source_id": source_id,
                    "pb_mass_kg": float(mass),
                    "fraction_of_pb": (float(mass) / pb_total) if pb_total > 0.0 else 0.0,
                })
    return {
        "chemistry_batches": batches,
        "elements": elements,
        "pb_isotopes": pb_isotopes,
        "source_pb": source_pb,
    }


def source_table_rows(world: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for source in source_chemistry_table(world).values():
        row = {
            "source_id": source.source_id,
            "label": source.label,
            "pb_ppm": float(source.pb_ppm),
            "Pb206_204": float(source.pb_ratios["Pb206_204"]),
            "Pb207_204": float(source.pb_ratios["Pb207_204"]),
            "Pb208_204": float(source.pb_ratios["Pb208_204"]),
            "calibration_status": source.calibration_status,
        }
        for element in TRACE_TO_ELEMENT.values():
            row[f"{element}_ppm"] = float(source.trace_ppm.get(element, 0.0))
        rows.append(row)
    return rows
