from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import poari_career_router as base


class StrictPOARICareerSampler(base.POARICareerSampler):
    """POARI router whose involution cannot reduce global world-shape coherence."""

    def _involution_rewrite(self) -> None:
        for _ in range(self.involution_passes):
            changed = False
            used_ids = {candidate.object_id for candidate in self.selected_by_slot.values()}
            order = list(self.slots)
            self.rng.shuffle(order)
            for slot in order:
                if slot.recurrence_role not in {"independent", "background"}:
                    continue
                old = self.selected_by_slot[slot.index]
                old_global = self._global_coherence_score()
                old_dims = self._coherence_dimensions(slot, old)
                old_local = base.p_mean(
                    list(old_dims.values()),
                    [self._dimension_weights(slot).get(k, 1.0) for k in old_dims],
                    p=base.p_for_level(slot.level),
                )
                alternatives = [
                    c for c in self.candidates
                    if c.object_id not in used_ids
                    and (c.object_class in slot.allowed_classes or slot.level > 8)
                    and (c.material_family in slot.allowed_materials or slot.level > 12)
                ]
                if not alternatives:
                    continue
                if len(alternatives) > self.involution_trials:
                    idx = self.rng.choice(len(alternatives), size=self.involution_trials, replace=False)
                    alternatives = [alternatives[int(i)] for i in idx]

                best = old
                best_global = old_global
                best_local = old_local
                for candidate in alternatives:
                    self.selected_by_slot[slot.index] = candidate
                    self._rebuild_selected_state()
                    dims = self._coherence_dimensions(slot, candidate)
                    if self._hard_gate(slot, candidate, dims) <= 0:
                        self.selected_by_slot[slot.index] = old
                        self._rebuild_selected_state()
                        continue
                    candidate_global = self._global_coherence_score()
                    candidate_local = base.p_mean(
                        list(dims.values()),
                        [self._dimension_weights(slot).get(k, 1.0) for k in dims],
                        p=base.p_for_level(slot.level),
                    )
                    global_ok = candidate_global >= old_global - 1e-10
                    improves_global = candidate_global > best_global + .0008
                    tie_improves_local = abs(candidate_global - best_global) <= .0008 and candidate_local > best_local + .003
                    if global_ok and (improves_global or tie_improves_local):
                        best = candidate
                        best_global = candidate_global
                        best_local = candidate_local
                    self.selected_by_slot[slot.index] = old
                    self._rebuild_selected_state()

                if best.object_id != old.object_id:
                    used_ids.discard(old.object_id)
                    used_ids.add(best.object_id)
                    self.selected_by_slot[slot.index] = best
                    self._rebuild_selected_state()
                    changed = True
            if not changed:
                break
