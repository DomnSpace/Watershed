from __future__ import annotations

from typing import Any, Mapping

import acquisition_campaign as campaign
import campaign_substrate_cache as cache


class CachedAcquisitionCampaignSampler(campaign.AcquisitionCampaignSampler):
    """Acquisition campaign using a precomputed shared hidden-world substrate."""

    def __init__(self, *args: Any, substrate_payload: Mapping[str, Any], **kwargs: Any):
        super().__init__(*args, intensity_steps=int(substrate_payload["intensity_steps"]), **kwargs)
        cache.validate_payload(substrate_payload)
        self.substrate_payload = dict(substrate_payload)
        self.substrate_fingerprint = cache.payload_fingerprint(substrate_payload)

    def prepare_candidates(self) -> None:
        if not getattr(self.world, "workshops", None) or not getattr(self.world, "sources", None):
            raise RuntimeError("Cached acquisition campaign still requires the shared world sources/workshops")
        self.flow_reports = []
        self.flow_summary = dict(self.substrate_payload.get("flow_summary", {}))
        self.loss_strata = cache.deserialize_loss_strata(self.substrate_payload)
        missing = sorted({s.node_id for s in self.loss_strata if s.node_id not in self.world.nodes})
        if missing:
            raise ValueError(f"campaign substrate/world geography mismatch; missing nodes: {missing[:8]}")
        self.sites = self._build_sites()
        self._prepared = True

    def career_report(self):
        report = super().career_report()
        report["campaign_substrate"] = {
            "schema": self.substrate_payload["schema"],
            "fingerprint": self.substrate_fingerprint,
            "world_seed": int(self.substrate_payload["world_seed"]),
            "workshop_count": int(self.substrate_payload["workshop_count"]),
            "intensity_steps": int(self.substrate_payload["intensity_steps"]),
            "loss_strata": len(self.substrate_payload["loss_strata"]),
            "precomputed": True,
        }
        return report
