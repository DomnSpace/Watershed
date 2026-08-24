from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List

import artifact_physical_truth as physical_truth
import instrument_measurement_model as instruments
import poari_archaeology_v2 as poari


PHYSICAL_SAMPLER_VERSION = "poari-physical-artifact-sampler-v1"


class PhysicalArchaeologyPOARICareerSampler(poari.ArchaeologyPOARICareerSampler):
    """POARI sampler with lazy, deterministic physical truth per selected find.

    Geographic/transport priors influence how an object reaches archaeology, but
    they never replace the object's material, workshop, use-history or corrosion state.
    """

    def _ensure_physical(self, c: Any) -> Dict[str, Any]:
        row = c.row
        if "artifact_truth" not in row:
            physical_truth.enrich_legacy_catalogue_row(self.world, row, self.seeds.archaeology_seed)
        return row["artifact_truth"]

    def _project_player_object(self, slot: Any, c: Any) -> Dict[str, Any]:
        truth = self._ensure_physical(c)
        public = super()._project_player_object(slot, c)
        # Public catalogue condition is directly observable; production/workshop/use
        # history and true chemistry remain hidden until instruments constrain them.
        corr = truth["corrosion"]
        find = truth["find_context"]
        ident = truth["identity"]
        public["find_context"] = {
            "site_id": find["find_site_id"],
            "site": deepcopy(find["site"]),
            "discovery_year_ce": find["discovery_year_ce"],
            "recovery_method": find["recovery_method"],
        }
        public["condition"] = {
            "present_mass_kg": ident["mass_kg_present"],
            "surface_coverage_fraction": corr["surface_coverage_fraction"],
            "integrity_fraction": corr["integrity_fraction"],
            "visible_cracking_fraction": corr["crack_fraction"],
            "condition_note": (
                "coherent mineralized surface" if corr["integrity_fraction"] > .72
                else "moderate corrosion and local material loss" if corr["integrity_fraction"] > .46
                else "substantial mineralization / structural loss"
            ),
        }
        public["physical_sampler_version"] = PHYSICAL_SAMPLER_VERSION
        return public

    def _measurement_payload(self, slot: Any, c: Any) -> Dict[str, Any]:
        artifact = self._ensure_physical(c)
        available = self._available_tests(slot, c)
        measured: Dict[str, Any] = {}
        legacy = c.row.get("tests", {})
        for tool in available:
            if tool in instruments.TOOL_FUNCS:
                measured[tool] = instruments.measure_tool(artifact, tool, self.seeds.measurement_seed)
            elif tool == "manufacturing_sequence":
                # Sequence is a reconstruction channel. The player receives observable
                # operation evidence, not the hidden guild label/workshop ID.
                measured[tool] = {
                    "tool": tool,
                    "available": True,
                    "operations_observed": list(artifact["manufacture"]["operations"]),
                    "uncertainty_note": "Operation ordering is reconstructed from manufacturing traces; guild/workshop identity is not emitted.",
                }
            elif tool in legacy:
                measured[tool] = {
                    "tool": tool,
                    "available": True,
                    "legacy_observation": deepcopy(legacy[tool]),
                    "uncertainty_note": "Legacy observation retained until a physical forward model is added for this channel.",
                }
        return {
            "career_index": slot.index,
            "object_id": c.object_id,
            "measurement_model_version": instruments.MEASUREMENT_MODEL_VERSION,
            "tests": measured,
        }

    def debug_truth(self) -> List[Dict[str, Any]]:
        out = super().debug_truth()
        for item, slot in zip(out, self.slots):
            c = self.selected_by_slot[slot.index]
            artifact = self._ensure_physical(c)
            item["artifact_truth"] = deepcopy(artifact)
            item["physical_sampler_version"] = PHYSICAL_SAMPLER_VERSION
        return out
