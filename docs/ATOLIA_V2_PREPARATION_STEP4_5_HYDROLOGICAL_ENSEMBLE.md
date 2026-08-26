# Atolia direct-NetCDF v2 preparation — Step 4.5/5

## Evidence-preserving palaeohydrological ensemble for dense Padanian–Mediterranean carrier landscapes

Status: implemented preparation pass 4.5 on `atolia-metal-lineage-v1`.

Step 4 established that transport, loss and archaeological findspots must operate on dynamic palaeogeography rather than modern rivers/coasts. Step 4.5 specifies how v2 may infer a much denser hydrological carrier world **without encoding Atoliamaxx as a premise**.

The rule is strict:

> **Observed evidence is immutable. Inference may add only physically admissible possibilities. A sampled hidden-world realization may use those possibilities, but inferred geometry never becomes archaeological fact merely because the simulation selected it.**

This is deliberately compatible with strong Atoliamaxx-like connectivity while remaining neutral about whether any particular inferred channel, flood, dam, lake connection or cooperative hydraulic work actually existed.

---

# 1. Three separate hydrological products

Never collapse these into one map.

```text
HYDRO_EVIDENCE
  mapped/datable palaeochannels, rivers, lakes, wetlands,
  shorelines, sediments, archaeological hydraulic features

HYDRO_ENSEMBLE
  physically admissible candidate channels, distributaries,
  marsh connectors, floodways, lake outlets, palaeoshore states,
  temporary blockages and human-modification possibilities

HYDRO_REALIZATION
  one time-dependent hidden-world history sampled from the ensemble
```

Every geometry/event carries:

```text
provenance_class = observed | inferred | realized
source_id
chronology_min
chronology_max
confidence
mechanism
parent_feature_ids
```

`realized` never upgrades `inferred` to `observed`.

---

# 2. Evidence ingestion

Step 5 should ingest neutral external evidence before generating any candidates:

```text
mapped palaeochannels
mapped Holocene fluvial ridges
DEM / palaeo-DEM constraints
bathymetry
known lakes/wetlands/peat bodies
sedimentary facies
relative sea-level constraints
submerged palaeocoastline evidence
known archaeological sites as observation constraints only
known hydraulic structures where securely identified
```

High-resolution regional evidence is preferred over pan-European generalization.

Priority region for v2 calibration:

```text
Adige / Atesis
Po / southern Venetian plain
Verona–Vicenza–Padua triangle
Garda–Affi corridor
Fimon–Berici–Bacchiglione system
Venetian / northern Adriatic lagoons
```

Broader Mediterranean/European layers remain the lower-resolution carrier substrate.

---

# 3. Five-times denser candidate hydrology

Target **candidate carrier geometry approximately 5× denser than the securely mapped usable channel geometry** in suitable lowland/wetland terrain.

This does NOT mean five additional major rivers per observed river.

Most added geometry should be:

```text
minor distributary
seasonal channel
marsh connector
groundwater-fed stream
abandoned-channel reactivation
flood bypass
short lake/wetland outlet
lagoonal creek
anabranch
local drainage channel
small human cut/diversion candidate
```

Large persistent inferred channels require much stronger geomorphic support.

Density multiplier is spatially conditional:

```text
candidate_density_multiplier ~= 1
    on steep/high-relief terrain

candidate_density_multiplier -> 5 or more
    on broad alluvial plains, wetlands, deltas,
    palaeochannel belts and lagoon margins
```

The multiplier is a candidate-space target, not a claim that all candidates coexist.

---

# 4. Candidate-channel probability

For cell/edge `x` and time `t`:

```text
logit P_candidate(x,t) =
    b0
  + b_slope      * low_gradient
  + b_flow       * contributing_area
  + b_ground     * groundwater_potential
  + b_palaeo     * palaeochannel_proximity
  + b_wet        * wetland_connectivity_gain
  + b_lake       * lake_outlet_gain
  + b_sed        * compatible_sediment
  + b_flood      * floodplain_membership
  + b_network    * network_connectivity_gain
  - b_ridge      * resistant_ridge_penalty
  - b_climb      * uphill_energy_penalty
  - b_barrier    * bedrock/barrier_penalty
```

Candidate geometry must obey drainage/topographic constraints unless the mechanism explicitly permits temporary ponding, avulsion or human excavation.

No channel may appear merely because it would improve Atoliamaxx connectivity.

---

# 5. Ensemble generation rather than one reconstructed map

For each 25-year physical snapshot, generate an ensemble of admissible hydrological states.

A candidate feature has state:

```text
dormant
seasonal
active_minor
active_major
wetland_connector
abandoned
reactivated
human_modified
blocked
breached
```

Transition probabilities depend on sedimentation, flooding, gradient, adjacent active channels, lake/wetland state and human intervention.

This allows one candidate to be active in 1450 BCE, abandoned in 1350 BCE and flood-reactivated in 1280 BCE without pretending we know its exact chronology.

---

# 6. Connectivity objective is hydrological, not archaeological

Candidate inference may optimize neutral physical quantities:

```text
drainage continuity
mass/flow continuity
wetland connectivity
lake spill routing
low-energy path consistency
floodplain drainage
shore/lagoon exchange
```

It must NOT optimize:

```text
agreement with Atoliamaxx
metal find density
known guild locations
preferred ancient trade routes
future player artefact selection
```

This firewall is essential.

---

# 7. Verona–Vicenza–Padua triangle

Treat this as a high-resolution ensemble zone because it combines:

```text
Adige palaeochannel belts
low-gradient alluvial plains
resurgence/groundwater systems
Berici/Fimon basin geometry
Bacchiglione-related drainage
wetland and floodplain surfaces
connections toward Padua and lagoonal systems
```

The model should permit many more small water connections than survive in a modern simplified drainage graph.

However, inferred links are tagged by mechanism and confidence. A Fimon-to-lowland connector and an inferred Adige anabranch are not equivalent evidence classes.

Suggested local candidate multiplier:

```text
ordinary alluvial plain: 3–5×
wetland/palaeochannel intersection: 5–8×
steep Berici/Garda margins: <= 2× except valley bottoms/outlets
```

These are computational candidate-space priors for Step-5 calibration, not historical frequencies.

---

# 8. Fimon and small lake/wetland systems

Lake/wetland basins are active network elements.

Each basin has:

```text
water_level
storage
inflow set
spring/groundwater input
outlet threshold
outlet geometry
sediment infill rate
wetland fringe
seasonality
```

Candidate connectors arise when neighbouring low points permit overflow, groundwater-fed drainage or flood exchange.

A lake is therefore not simply a point/node. Its changing shoreline and wetland fringe create transport, settlement, deposition and loss surfaces.

---

# 9. Garda/Affi blockage–ponding–breach hypothesis space

Do NOT encode a specific Bronze Age Affi/Garda dam or flood event as fact.

Instead implement a generic physically constrained event family:

```text
BLOCKAGE
  trigger = landslide | debris flow | fan growth | sediment pulse |
            ice/legacy morphology where chronologically admissible |
            human intervention candidate

PONDING
  storage grows behind barrier

OVERTOP/BREACH
  threshold exceeded or barrier fails

FLOOD_PULSE
  downstream discharge/sediment pulse

REORGANIZATION
  channels/wetlands/outlets may change
```

Event hazard:

```text
h_block = f(
    valley confinement,
    fan geometry,
    slope instability,
    sediment supply,
    flood regime,
    seismic susceptibility,
    existing outlet geometry
)
```

A realization may contain such an event only when the terrain/process state permits it.

Output remains:

```text
mechanism = inferred_blockage_event
provenance_class = realized
source_evidence = geomorphic constraints
```

unless an external dated observation independently establishes the event.

---

# 10. Flood pulses can reorganize networks

A large natural event should not merely increase a scalar flood hazard.

It can:

```text
activate dormant floodways
cut a new distributary
abandon an old reach
breach a natural levee
connect two wetlands temporarily
shift a river mouth
bury an existing channel
create a new lake/wetland surface
move sediment and deposited artefacts
```

Use event-level correlated updates rather than independent edge toggles.

---

# 11. Human hydraulic modification without assuming canals

Human intervention is represented as a graded process:

```text
natural
opportunistically_modified
repeatedly_maintained
cooperatively_maintained
engineered
```

Possible interventions:

```text
bank reinforcement
ford maintenance
short drainage cut
channel clearing
small diversion
wetland drainage
irrigation intake
landing/beaching improvement
levee repair
outlet control
```

Do not label a feature `canal` until its process state/evidence meets a later explicit criterion.

---

# 12. Emergent hydraulic cooperation

Large cooperation is an output, not an Atoliamaxx premise.

For communities sharing a water landscape:

```text
P_cooperate = sigmoid(
    b0
  + b_shared_floodplain * shared_floodplain_exposure
  + b_benefit           * navigation_irrigation_drainage_gain
  + b_population        * participating_population
  + b_repeat            * prior_successful_maintenance
  + b_dependency        * downstream_upstream_dependency
  - b_cost              * labour_cost
  - b_conflict          * intergroup_conflict
  - b_failure           * recent_failed_projects
)
```

A cooperative project must have a concrete local objective and labour cost.

Repeated neighbouring small works can concatenate into a larger maintained hydraulic corridor without the simulation initially positing a centralized canal authority.

Record:

```text
project_id
participants
labour_person_days
maintenance_interval
hydraulic_gain
navigation_gain
agricultural_gain
flood_risk_change
failure_history
```

---

# 13. Cooperation can fail and disappear

Hydraulic works are mortal.

Without maintenance:

```text
siltation
bank failure
vegetation
avulsion
flood damage
political abandonment
population decline
```

reduce function.

This is important for archaeological neutrality: an extensive hydraulic episode can leave only fragmentary geomorphic traces later.

But the model must not use this possibility as an excuse to assert invisible works. It remains hidden-world inference with uncertainty.

---

# 14. Human/natural ambiguity is retained

For ambiguous features maintain competing mechanism weights:

```text
P(natural_channel)
P(natural_reactivated)
P(human_cleared)
P(human_cut)
P(mixed_origin)
```

Do not collapse to the maximum class during master generation.

The covariance/mixture survives into developer truth and can later become an archaeological inference problem in the game.

---

# 15. Palaeocoast ensemble

Apply the same evidence/inference/realization separation to coastlines.

Inputs:

```text
relative sea level
bathymetry/palaeo-DEM
subsidence/uplift priors
sediment supply
mapped lagoon/coastal deposits
known submerged-landscape features
```

Generate:

```text
shore probability surface
lagoon probability
wetland probability
river-mouth distribution
beachability/shelter
nearshore navigability
```

Do not reduce uncertain Bronze Age coastlines to one polyline.

Transport can sample from the realization while release diagnostics retain the uncertainty field.

---

# 16. Mediterranean/European scaling

The dense inference machinery is resolution-adaptive.

```text
Atesis/Po/northern Adriatic core:
    high-resolution DEM + regional evidence + dense ensemble

rest of northern Italy/Alpine approaches:
    medium resolution

Mediterranean/European carrier world:
    coarser palaeocoast/major-river/wetland ensemble
```

This prevents the 5× rule from exploding the entire European graph unnecessarily.

Long-distance Step-4 boat/merchant movement can use the coarse graph and refine only on entry to high-resolution regions.

---

# 17. Coupling to Step-4 movement

For each transport packet, water access is no longer a fixed node property.

At `(x,t)` query the selected hydrological realization:

```text
P_water_access
active_channel_class
wetland_depth/class
shore_distance
navigability
seasonality
embarkability
network_connectivity
```

The Step-4 water-mode transition then operates on that state.

An inferred minor marsh connector may permit a small local craft but not a bulk merchant vessel. Navigability is therefore continuous/categorical, not boolean.

---

# 18. Coupling to loss frontlines

Hydrological uncertainty directly influences loss geography.

For realization `r`:

```text
F_loss_r(x,t)
```

is generated using active channels, flood fronts, wetland boundaries, shorelines and change rates.

Across the ensemble retain:

```text
E[F_loss]
Var[F_loss]
P(high_loss_front)
```

Thus a modern findspot can be compared to a broad ancient loss-front probability without claiming a single vanished river definitely occupied that coordinate.

---

# 19. Archaeological discovery firewall

The hidden hydrological ensemble is generated before player-career crystallization.

Forbidden feedback:

```text
player finds -> change inferred palaeochannels
career selection -> change hydro realization
known desired Atoliamaxx pattern -> increase candidate probability
```

Later gameplay may infer/reconstruct the hidden realization from evidence, but it does not retroactively create it.

---

# 20. NetCDF schema additions

Suggested groups:

```text
/hydro/evidence
/hydro/candidates
/hydro/snapshots
/hydro/events
/hydro/human_projects
/hydro/coast
/hydro/runtime
```

### `/hydro/evidence`

Sparse immutable feature table:

```text
feature_id
geometry_ref
feature_type
chronology_min/max
confidence
source_id
```

### `/hydro/candidates`

```text
candidate_id
parent_evidence_ids
mechanism
base_probability
terrain_cost
connectivity_gain
candidate_scale
```

### `/hydro/snapshots`

Avoid copying complete geometry every 25 years.

Store state vectors over stable candidate IDs:

```text
time_index
candidate_state
flow_capacity
navigability
wetness
shore_probability
```

with sparse changed-state encoding where useful.

### `/hydro/events`

```text
event_id
time
cell/feature ids
event_type
magnitude
affected_candidate_ptr/index
```

### `/hydro/human_projects`

Store project/event histories separately from physical channel state.

---

# 21. NetCDF efficiency

The fivefold candidate network must not create another 40-GB JSON problem.

Use:

```text
stable integer feature IDs
CSR adjacency
quantized probabilities where adequate
packed enums for state/mechanism
shared geometry vertices
snapshot deltas rather than duplicate geometries
chunking by region/time
zlib/zstd-compatible NetCDF compression where supported
```

Developer master retains full evidence/provenance links.

Installer runtime needs only the sampled canonical realization plus sufficient uncertainty summaries for gameplay/research.

---

# 22. Ensemble sampling and canonical world

The giant overnight build does not need to propagate 100 complete hydrological worlds through 50M represented object episodes.

Recommended workflow:

```text
1. construct evidence layer once
2. construct candidate ensemble once
3. run 32–128 cheap hydro-only realizations
4. reject physically invalid realizations
5. characterize connectivity/loss-front distributions
6. sample/freeze one canonical v2 realization using canonical seed
7. propagate the expensive metal/object world on that realization
8. retain ensemble uncertainty metadata for interpretation
```

This keeps the expensive run tractable while avoiding arbitrary hand selection.

---

# 23. Physical rejection tests

Reject a hydro realization if it violates hard constraints such as:

```text
persistent uphill flow without permitted ponding/pumping
water mass continuity failure
unphysical disconnected major river
large lake without viable storage/outlet accounting
major channel crossing bedrock ridge without mechanism
coastline inconsistent with hard RSL/elevation constraints
human project with impossible labour budget
instantaneous large channel relocation without flood/avulsion event
```

Soft archaeological disagreement is NOT a rejection criterion.

---

# 24. Neutrality diagnostics

Every release candidate prints:

```text
observed_channel_length_km
candidate_channel_length_km
realized_channel_length_km
candidate/observed density ratio by region
fraction realized by mechanism
fraction with direct evidence parent
wetland connector count
reactivation count
avulsion count
blockage/breach count
human modification count
cooperative project count
median project labour
shoreline uncertainty area
```

And specifically for the Atoliamaxx-sensitive core:

```text
Verona–Vicenza–Padua connectivity metrics
Fimon connectivity metrics
Garda/Affi outlet-state metrics
Adige/Po cross-basin connector metrics
northern-Adriatic lagoon connectivity
```

These are reported descriptively. No target value is optimized to make the conspiracy stronger.

---

# 25. Ablation test

Run the canonical medium world twice:

```text
A: observed hydro evidence only
B: observed + neutral inferred hydro ensemble
```

Compare, without fitting to archaeology:

```text
water-mode frequency
cumulative metal distance
500–1000+ km recycled-metal tail
broker connectivity
war displacement
loss-front geometry
hoard geography
coastal/river deposition
modern discovery probability
```

If B merely creates uniform extra mobility, the ensemble is wrong.

It should instead create spatially structured alternative corridors, especially in low-gradient wetland/alluvial landscapes.

---

# 26. Atoliamaxx compatibility test

Only after the neutral world has been frozen may a separate diagnostic ask:

```text
How compatible is this realization/ensemble with Atoliamaxx hypotheses?
```

That diagnostic may inspect:

```text
hydrological connectivity
possible cooperative hydraulic chains
metal transport
settlement access
loss/find distributions
```

but it has **zero write access** to world generation.

This is the cleanest way to let the model surprise us rather than encode the answer.

---

# 27. Step-4.5 release invariants

1. Observed and inferred hydrology are never conflated.
2. Atoliamaxx is never an inference feature or objective.
3. Candidate density may be ~5× observed geometry in appropriate terrain, but realized density is emergent.
4. Most added features are minor/ephemeral connectors, not invented major rivers.
5. Palaeochannels can activate, abandon and reactivate through explicit mechanisms.
6. Lakes/wetlands are dynamic surfaces with storage/outlet behavior.
7. Garda/Affi blockage/breach exists only as a generic physically constrained event family unless independently evidenced.
8. Human modification is graded; `canal` is not a default label.
9. Large hydraulic cooperation emerges from repeated local incentives and maintenance.
10. Cooperation can fail and its works can silt/erode/abandon.
11. Human/natural ambiguity is retained probabilistically.
12. Palaeocoasts are probability surfaces/ensembles where evidence is uncertain.
13. Transport uses realization-specific navigability, not generic water proximity.
14. Loss-front uncertainty is retained across hydro realizations.
15. Player careers cannot influence hydrological truth.
16. The fivefold candidate network is stored sparsely in NetCDF.
17. Physical rejection tests operate independently of archaeological desirability.
18. Atoliamaxx compatibility is evaluated only downstream as a read-only diagnostic.

---

# 28. What Step 5 now receives

The final v2 implementation pass receives:

```text
Step 1: metal/object mass and lineage accounting
Step 2: autonomous guild skill ecology
Step 3: isotope/trace/process physics
Step 4: carrier mobility, recycling, loss and findspot ecology
Step 4.5: evidence-preserving dense palaeohydrological ensemble
```

Step 5 can therefore build the final direct-NetCDF world in the correct order:

```text
external palaeolandscape evidence
        ↓
neutral dense hydro candidate ensemble
        ↓
physically valid hydro realizations
        ↓
freeze canonical hydrological realization
        ↓
autonomous guild/workshop world
        ↓
metal production + chemistry/isotope inventories
        ↓
carrier random walks / boats / brokers / war / recycling
        ↓
loss frontlines and deposition
        ↓
post-depositional landscape transformation
        ↓
modern discovery field
        ↓
ECMWF-style runtime condensation
        ↓
private 300-object career crystallization
```

The important epistemic property is preserved all the way through:

> **The world is allowed to become Atoliamaxx-like. It is never required to be Atoliamaxx-like.**
