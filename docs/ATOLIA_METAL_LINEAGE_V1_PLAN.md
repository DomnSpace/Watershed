# Atolia Metal Lineage v1 — upgrade plan

Branch: `atolia-metal-lineage-v1`
Base: `atolia-release-candidate-surgery`

## Goal

Replace the implicit assumption that the final artefact is the fundamental transported unit with an explicit **metal biography**. A selected archaeological object becomes the final episode in a chain of ore extraction, batching, manufacture, use, brokerage, remelting, recycling, repair, and redeposition.

The scientific invariant remains:

> POARI routes archaeological inquiry, not artefact selection.

Career actions may choose sites/questions from observable evidence. They must not rank hidden objects by their latent guild, source, crossing, recycle, or repair truth.

## 1. Core state

Introduce a hidden metal-lineage model independent of the final object class.

```text
MetalBatchState
  batch_id
  mass_kg
  date_bc
  node_id
  source_mix
  alloy_wt_pct
  trace_ppm
  lead_isotopes
  cumulative_metal_km
  ore_transport_km
  recycle_generation
  parent_batch_ids[]
  retained_mass_fraction

MetalEpisode
  episode_id
  batch_id
  kind = ore|ingot|object|scrap|broker_stock|remelt|repair|loss
  object_class?
  workshop_id?
  guild_affinities?
  primary_guild_id?
  node_start / node_end
  route_nodes[]
  distance_km
  date_start_bc / date_end_bc
  process_operations[]

MetalLineage
  lineage_id
  root_sources[]
  batches[]
  episodes[]
  final_batch_id
  final_object_id
  distance_ore_km
  distance_cumulative_metal_km
  distance_current_object_km
```

The final artefact keeps the existing `artifact_truth` structure, but gains `metal_lineage` and lineage-derived summaries.

## 2. Three different distances

Never overload one `route_km` again.

- `ore_transport_km`: source extraction / first smelting / first workshop supply movement.
- `cumulative_metal_km`: sum of every physical movement of the surviving metal fraction through all episodes.
- `current_object_km`: movement after the last full remelt / manufacture that created the recovered object.

Thus an intact grave sword may legitimately have:

```text
current_object_km = 85
cumulative_metal_km = 740
ore_transport_km = 310
```

No release invariant should demand that final-object distance itself reach 500–1000 km.

## 3. Recycling becomes a transformation, not a counter

Current recycle moments remain useful as latent expectations, but materialization converts them into a sequence of transformations.

At each recycle/remelt episode:

1. choose a broker/workshop node reachable from the previous episode;
2. choose whether the old object is repaired, reworked without full melt, or remelted;
3. on remelt, permit object-class change;
4. permit addition of new metal from one or more contemporaneous source/broker pools;
5. evolve alloy/trace/isotope state by mass-weighted mixing plus explicitly modeled process loss/noise;
6. assign the new workshop and guild affinities;
7. increment cumulative metal distance while resetting `current_object_km` only after a full remelt/new-object manufacture.

Mass mixing boundary:

`a_next = (sum_i m_i * a_i_after_process + additions) / m_batch`

Do not hard-code archaeometallurgical elemental-loss constants unless supported later by evidence. v1 may use conservative bounded process-noise parameters with explicit schema/version labels.

## 4. Guild lineage

A final object no longer has only one meaningful guild signal.

Store a chronological `guild_lineage` derived from manufacturing/repair episodes:

```text
[
  {episode, workshop, guild_affinities, primary_guild, operation_set, survival_mode},
  ...
]
```

Evidence persistence depends on transformation type:

- full remelt: destroys previous microstructure and most shape/tool evidence;
- deformation/reworking: may preserve casting or earlier geometry beneath later work;
- repair/join: may preserve a locally distinct alloy, guild technique, or microstructure;
- chemistry/isotopes: retain mixed ancestry but become less source-specific with repeated mixing;
- final microstructure/hardness: weighted strongly toward the last heat/deformation sequence.

The twelve guilds therefore become technical lineages that can recur, overlap, or conflict within one metal biography.

## 5. Source and alloy evolution

Separate four concepts:

1. geological source ancestry;
2. batch source fractions at each remelt;
3. bulk alloy of each episode;
4. instrument-visible altered/surface chemistry.

For each remelt, retain ancestry through parent-batch pointers rather than replacing it with only the latest normalized source map. Derive final source fractions recursively by surviving mass contribution.

Repeated brokerage/recycling should naturally increase mixture entropy and reduce confidence in a single-source explanation, while preserving physical trace/isotope consequences.

## 6. Latent circulation substrate

Do **not** regenerate the 2.16 GB developer substrate immediately.

v1 implementation order:

### A. Lineage materializer on top of existing ECMWF runtime
Use existing profile moments:
- expected recycle count
- expected repair count
- source entropy
- physical/field crossings
- route distance

Materialize a plausible hidden lineage only for the 300 selected objects. This keeps runtime cost tiny and proves the model first.

### B. Broker/workshop transition kernel
Add a deterministic, seeded transition kernel over existing world nodes/workshops using geography, date, transport fields, workshop activity, object class/status, and broker-like hubs. It must not depend on career regime.

### C. Later substrate v2
Only after v1 audit succeeds, decide whether the developer master should preserve extra sufficient statistics such as cumulative-metal-distance moments, recycle-generation covariance, broker transitions, or batch-mixture moments.

## 7. Career-regime correction

Keep the eight-stage epistemic schedule, but remove hidden biography weighting from within-site artefact selection.

Site/action choice may use observable/aggregated acquisition dimensions. Once a site is chosen:

`P(profile | chosen site) ∝ archaeological_intensity × observation/recovery terms`

not

`× hidden crossing/guild/recycle usefulness`.

Replace Boolean `tail` as the main concept with an exceptionality vector:

```text
rarity
object_distance
cumulative_metal_distance   # hidden truth, not POARI input
physical_crossings
field_crossings
region_difference
context_loss
```

Only observable or acquisition-safe projections enter POARI.

Late career meaning becomes:

- discriminating dig: test competing explanations using acquired measurements;
- network reconstruction: distinguish movement of people/guild practice, finished objects, and metal;
- falsification probe: seek weak-link sites where the current reconstruction should fail.

## 8. Measurements

Extend instrument forward models so lineage can become inferable without direct truth leakage.

Candidate observables:
- XRF / bulk chemistry mismatch between repair and body;
- Pb isotope mixtures incompatible with a single source;
- trace-element mixture broadening;
- metallographic evidence of prior casting/reworking;
- CT/radiography joins, patches, concealed inserts;
- hardness/recrystallization gradients;
- guild-operation signatures surviving in different zones.

Public object projection must never expose `metal_lineage`, source ancestry, guild lineage, or exact recycle genealogy directly.

## 9. Validation invariants

Add focused tests/audits before any expensive rebuild:

- 300/300 selected objects have a valid lineage.
- `current_object_km <= cumulative_metal_km`.
- all episode distances nonnegative and finite.
- source fractions positive and normalized after each materialized mixture.
- batch mass conserved within explicit process-loss tolerance.
- parent-batch graph acyclic.
- final `artifact_truth.material` matches final lineage batch.
- final workshop/manufacture matches final lineage manufacturing episode.
- repair episodes correspond to timeline repair evidence.
- same player key -> identical lineage.
- different key -> divergent career/lineages on same hidden world.
- POARI site/action ranking never reads `metal_lineage` or final hidden guild/source truth.

Distribution audit should report by career regime:

```text
current_object_km quantiles
cumulative_metal_km quantiles
ore_transport_km quantiles
recycle generations
number of workshops
number of distinct primary guilds
guild-lineage entropy
source ancestry entropy
repair count
full-remelt count
object-class transitions
```

500–1000 km should be evaluated primarily against cumulative metal biography, not required as a final-object route quota.

## 10. Implementation sequence

1. Add `metal_lineage.py` with pure dataclasses/helpers and deterministic seeded genealogy generation.
2. Extend `artifact_physical_truth.build_artifact_truth()` to accept/build lineage and derive final material/manufacture state from it.
3. Add broker/workshop/object-class transition kernel independent of career regime.
4. Wire existing ECMWF recycle/repair/profile moments into lineage materialization.
5. Add guild-lineage persistence rules for remelt/rework/repair.
6. Extend instrument models for mixed ancestry and multi-episode manufacturing evidence.
7. Remove hidden crossing boost from within-site `discriminating_dig` / `network_reconstruction` profile selection.
8. Replace `tail` diagnostics with explicit exceptionality components while retaining backward-compatible debug field if necessary.
9. Add `audit_metal_lineages.py` and update `audit_career_regimes.py`.
10. Run on existing `out/player_game.json` / runtime path first; regenerate only the 300-object package, not the developer master.
11. If lineage distributions and career behavior are scientifically healthy, design ECMWF runtime v2 sufficient statistics; otherwise keep v1 runtime and lineage as conditional materialization.

## 11. Branch/archive policy

Active development:

- `atolia-metal-lineage-v1`

Historical refs to preserve, not delete until v1 is validated:

- `atolia-copper-200kt-v0`
- `atolia-transport-field-editor-temp`
- `atolia-release-candidate-surgery`

Intended archive namespace after validation:

- `old/atolia/copper-200kt-v0`
- `old/atolia/transport-field-editor-temp`
- `old/atolia/release-candidate-surgery`

Git branch namespaces are naming conventions, not actual folders. Archive by creating equivalent `old/atolia/...` refs at the exact historical heads and only then deleting the old top-level names if desired.

## Release criterion

`atolia-metal-lineage-v1` is ready to replace the surgery branch only when the existing 300-object package can be regenerated deterministically from the compact runtime with rich, internally consistent metal/guild biographies, no direct hidden-truth artefact ranking, and no requirement to rebuild the giant developer master.
