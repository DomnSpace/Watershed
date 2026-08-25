from __future__ import annotations

"""Release-candidate invariants applied without disturbing the calibration branch.

This module is intentionally narrow. It installs fixes that must be true before a
shared campaign substrate is frozen and shipped to players:

* production counts conserve bundle copper mass and do not apply the temporal
  multiplier twice;
* the legacy POARI generalized mean keeps the mathematical HM < GM < AM < QM
  ordering, including p=-1 weak-link sensitivity;
* random-hoard artefacts enter the physical truth model as hoard deposits before
  burial/corrosion are generated, rather than being relabelled only afterwards.

The acquisition campaign itself remains the source of career logic.  These are
release-boundary correctness repairs, not a replacement model.
"""

import math
from typing import Any, Mapping, Sequence

import numpy as np

import acquisition_campaign as acquisition
import intensity_circulation as intensity
import poari_career_router as legacy_poari
import provenance_field as provenance


RELEASE_INVARIANTS_VERSION = "atolia-release-invariants-v1"
_INSTALLED = False


def generalized_mean(
    values: Sequence[float],
    weights: Sequence[float] | None = None,
    p: float = 1.0,
    eps: float = 1e-12,
) -> float:
    """Weighted generalized mean on positive coordinates.

    No clipping is applied to the powered sum before the inverse power.  That is
    essential for p < 0: clipping a harmonic sum to 1 first collapses weak-link
    sensitivity and can incorrectly return exactly 1.
    """
    x = np.clip(np.asarray(values, dtype=float), eps, None)
    if len(x) == 0:
        return 0.0
    if weights is None:
        w = np.ones(len(x), dtype=float)
    else:
        w = np.asarray(weights, dtype=float)
        if len(w) != len(x):
            raise ValueError("weights and values must have equal length")
    w = np.clip(w, 0.0, None)
    if float(w.sum()) <= 0.0:
        w = np.ones(len(x), dtype=float)
    w /= w.sum()
    if abs(float(p)) < 1e-12:
        return float(math.exp(float(np.sum(w * np.log(x)))))
    powered = float(np.sum(w * np.power(x, float(p))))
    if powered <= 0.0:
        return 0.0
    return float(powered ** (1.0 / float(p)))


def mass_conserving_production_cells(world: Any) -> list[intensity.ProductionCell]:
    """Convert bundle tonnes to object-event counts while conserving metal mass.

    ``world._class_weights`` is already the authoritative count-share vector for
    the active world.  In the temporal world it has already incorporated and
    renormalized the temporal production multipliers, so applying those multipliers
    here a second time is both unnecessary and incorrect.

    For each bundle/time slice:

        m_bar = sum_c f_c m_c
        N_total = 1000 * Q_tonnes * 0.48 / m_bar
        N_c = f_c * N_total

    Therefore sum_c N_c m_c == 1000 * Q_tonnes * 0.48 up to floating error.
    """
    cells: list[intensity.ProductionCell] = []
    for bundle in world.bundles:
        for date_bc in world.time_slices:
            tonnes = float(bundle.flux_tonnes.get(date_bc, 0.0))
            if tonnes <= 0.0:
                continue
            classes, weights = world._class_weights(date_bc, bundle)
            classes = [str(c) for c in classes]
            f = np.asarray(weights, dtype=float)
            f = np.clip(f, 0.0, None)
            if float(f.sum()) <= 0.0:
                f[:] = 1.0
            f /= f.sum()
            masses = np.asarray(
                [float(provenance.OBJECT_CLASSES[c]["mean_kg"]) for c in classes],
                dtype=float,
            )
            mean_mass = float(np.sum(f * masses))
            if mean_mass <= 0.0:
                raise ValueError("class-weighted mean object mass must be positive")
            total_objects = tonnes * 1000.0 * 0.48 / mean_mass
            for object_class, share in zip(classes, f):
                produced = total_objects * float(share)
                cells.append(
                    intensity.ProductionCell(
                        bundle_id=str(bundle.id),
                        bundle_family=str(bundle.family),
                        object_class=object_class,
                        date_bc=int(date_bc),
                        origin=str(bundle.origin),
                        destination=str(bundle.destination),
                        production_intensity=float(produced),
                        circulation_seed_intensity=float(produced),
                        source_mix=dict(bundle.source_mix),
                        recycle_mean=float(bundle.recycle_mean),
                    )
                )
    return cells


def production_mass_error(world: Any) -> float:
    """Absolute kg error of the release production transform."""
    cells = mass_conserving_production_cells(world)
    represented = sum(
        c.production_intensity * float(provenance.OBJECT_CLASSES[c.object_class]["mean_kg"])
        for c in cells
    )
    expected = 0.0
    for bundle in world.bundles:
        for date_bc in world.time_slices:
            expected += max(0.0, float(bundle.flux_tonnes.get(date_bc, 0.0))) * 1000.0 * 0.48
    return float(represented - expected)


_ORIGINAL_CANDIDATE_FROM_STRATUM = acquisition.AcquisitionCampaignSampler._candidate_from_stratum


def _hoard_coherent_candidate_from_stratum(
    self: acquisition.AcquisitionCampaignSampler,
    s: intensity.LossStratum,
    career_no: int,
    slot: Any,
    action: acquisition.ResearchAction,
    hoard: Mapping[str, Any] | None = None,
):
    """Ensure hoard burial mode reaches physical truth before corrosion is built."""
    if hoard is None:
        return _ORIGINAL_CANDIDATE_FROM_STRATUM(self, s, career_no, slot, action, hoard)

    # The existing method obtains deposition mode through this hook before calling
    # artifact_physical_truth.build_artifact_truth().  Temporarily forcing the hook
    # means burial environment/corrosion are generated as a hoard deposit from the
    # beginning; _force_hoard_context may still impose the common event/site after.
    original_sampler = self._sample_deposition_mode
    self._sample_deposition_mode = lambda _s, _rng: "finished_object_hoard"
    try:
        return _ORIGINAL_CANDIDATE_FROM_STRATUM(self, s, career_no, slot, action, hoard)
    finally:
        self._sample_deposition_mode = original_sampler


def install() -> str:
    """Install the release fixes once in the current Python process."""
    global _INSTALLED
    if _INSTALLED:
        return RELEASE_INVARIANTS_VERSION
    legacy_poari.p_mean = generalized_mean
    intensity.production_cells = mass_conserving_production_cells
    acquisition.AcquisitionCampaignSampler._candidate_from_stratum = _hoard_coherent_candidate_from_stratum
    _INSTALLED = True
    return RELEASE_INVARIANTS_VERSION
