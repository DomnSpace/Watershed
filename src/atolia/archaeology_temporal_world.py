from __future__ import annotations

from typing import Any, Dict

import numpy as np

import archaeology_field_world as field_world
import temporal_directional_model as temporal


TEMPORAL_FIELD_WORLD_VERSION = "archaeology-temporal-field-world-v1"


class TemporalFieldArchaeologicalWorld(field_world.FieldArchaeologicalObservationWorld):
    """Round-1 world: preserve bundle tonnes but redistribute class production temporally.

    This is deliberately a thin layer. Production remains bundle-origin based until
    Round 3 introduces full carrier-manifold production intensity cells.
    """

    def _class_weights(self, t: int, bundle: Any):
        classes, weights = super()._class_weights(t, bundle)
        arr = np.asarray(weights, dtype=float)
        multipliers = np.asarray([
            temporal.production_multiplier_for_bundle(str(object_class), bundle, int(t))
            for object_class in classes
        ], dtype=float)
        adjusted = np.clip(arr * multipliers, 1e-12, None)
        adjusted /= adjusted.sum()
        return classes, adjusted

    def generate_archaeological_catalogue(self, max_materialized: int = 30000) -> Dict[str, Any]:
        report = super().generate_archaeological_catalogue(max_materialized=max_materialized)
        report["temporal_directional_version"] = temporal.TEMPORAL_DIRECTIONAL_VERSION
        report["temporal_field_world_version"] = TEMPORAL_FIELD_WORLD_VERSION
        return report
