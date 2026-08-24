from __future__ import annotations

from typing import Any, Dict

import archaeology_observation_v2 as observation
import dense_geography_v1 as dense
import provenance_field_mediterranean as med


class DenseArchaeologicalObservationWorld(observation.ArchaeologicalObservationWorld):
    """Observation-v2 world whose curated transport graph is expanded to 1000 nodes."""

    target_geography_nodes = dense.DEFAULT_TARGET_NODES

    def __init__(self, *args: Any, target_geography_nodes: int | None = None, **kwargs: Any):
        super().__init__(*args, **kwargs)
        if target_geography_nodes is not None:
            self.target_geography_nodes = int(target_geography_nodes)
        self.geography_report: Dict[str, Any] = {}

    def _build_graph(self) -> None:
        # MediterraneanProvenanceWorld first installs the canonical Atolia +
        # Europe/Mediterranean skeleton. Densification happens before jet-bundle
        # shortest paths and workshop allocation, so the added localities become
        # first-class route/deposition/workshop positions rather than map-only dots.
        super()._build_graph()
        canonical = set(self.nodes)
        self.geography_report = dense.densify_world_graph(self, self.target_geography_nodes)
        self.geography_report["connectivity"] = dense.connectivity_report(self, canonical)
        self.geography_report["canonical_nodes"] = len(canonical)
        self.geography_report["region_counts"] = self._dense_region_counts()

    def _dense_region_counts(self) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for node_id in self.nodes:
            region = med.REGION_BY_NODE.get(node_id, "other")
            counts[region] = counts.get(region, 0) + 1
        return dict(sorted(counts.items()))
