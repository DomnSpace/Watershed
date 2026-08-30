# Atolia v3 phase 05 — hydro, exchange, deposition, observation

Phase 05 is downstream of the exact v1 propagation spine and phases 02–04. It does not rerun circulation, replace metal-batch identities, change chemistry, or select player-visible archaeological objects.

## Separation contract

Hydrology is stored in three distinct stages:

1. `/hydro/evidence` — statements supplied by the structural world or an optional converted evidence product.
2. `/hydro/ensemble` — candidate water connections with explicit realization probabilities and evidence references.
3. `/hydro/realization` — one deterministic world realization keyed by `world_seed`.

The existing structural water graph is model structure, not external palaeohydrological evidence. If no external GIS/palaeohydrology product is supplied, the file is explicitly marked:

`structural-world-graph-plus-provisional-connectors-no-external-palaeohydrology`

Short-range inferred connector candidates preserve the useful v2 ensemble mechanism but are labelled as provisional model priors. They are never silently promoted to observations.

## Sparse external exchange

`/exchange/tails` stores rare explicit external-network contacts. They are linked to phase-02 `particle_id` values and may use existing bundle/source textual tags as a trigger. Untagged long-distance contacts remain `external_unspecified_network`.

The layer is explicitly status-marked:

`sparse-model-tail-no-external-traffic-calibration`

External exchange is contextual history only in phase 05. It does not add or remove metal, alter source ancestry, or modify phase-03 chemistry.

## Shared late-stage deposition pools

Every phase-02 weighted lineage maps back to its exact phase-01 `(production_cell_index, cell_loss_index)` `LossStratum`. The terminal deposition mode is drawn deterministically from that stratum's existing `deposition_mode_weights`; phase 05 does not introduce a second deposition grammar.

Assignments are grouped into shared pools by:

`(loss_node_id, production time slice, deposition mode)`

The pool is a terminal context shared by multiple weighted lineages when those keys coincide. Pooling occurs after the loss process and does not feed back into circulation.

## Survival → discovery → recording

`/archaeology/observation` applies the existing broad conditional priors after loss, now directly to the real phase-02 weighted lineages:

`loss weight → survival weight → discovery weight → recorded weight`

Each stage stores both its conditional probability and resulting expected weight. The waterfall must be monotone for every lineage.

These are broad priors, not an empirical archaeological observation calibration. The approximately 30k catalogue condensation remains phase 06/07 work; phase 05 does not sample or select the player catalogue.

## NetCDF groups

- `/hydro/evidence`
- `/hydro/ensemble`
- `/hydro/realization`
- `/exchange/tails`
- `/deposition/assignments`
- `/deposition/pools`
- `/archaeology/observation`

The phase-05 root metadata links the exact phase-01 spine, phase-02 biography, phase-03 metallurgy and phase-04 workshop hashes. The phase-05 fingerprint uses `canonical-float-12sig-v1` while stored NetCDF values remain full `f8`.

## Scientific gaps kept explicit

The repository still does not contain the converted empirical palaeohydrology/GIS product recovered during the forensic audit. Phase 05 therefore supports supplied evidence but does not fabricate it. Likewise, the external-network tail has no external traffic calibration and is stored as a model prior rather than archaeological fact.

POARI remains outside hidden-world selection: **POARI routes archaeological inquiry, not hidden artefact selection.**
