# Atolia direct-NetCDF v2 preparation — Step 1/5

## World accounting, chronology, movement and sufficient state

Status: preparation pass 1 on `atolia-metal-lineage-v1`.

This step intentionally does **not** tune the twelve guilds and does **not** finalize isotopic physics. Those are Step 2 and Step 3. Step 1 fixes the extensive ledgers and state semantics they must inhabit.

---

## 0. Five-pass preparation sequence

1. **World accounting and state semantics** — this document.
2. **Twelve guilds through 1000 years** — locations, lifetimes, skill vectors, branching/merger, apprenticeship, career movement, object specialisms and historically plausible evolution.
3. **Isotope/trace deep model** — source covariance, Pb isotopes, trace-element inheritance, mixing, fractionation/non-fractionation assumptions, analytical uncertainty and what remelting destroys or preserves.
4. **Transport, broker and recycling ecology** — river/road/sea movement, 2–5 km active-travel days, dwell times, warrior/merchant/household/workshop careers, broker stocks, remelt hazards, object-class transitions and deposition.
5. **Direct NetCDF v2 build/freeze plan** — exact schema, online propagation writer, chunk/compression benchmark, invariants, one full master build, runtime condensation and 300-career validation.

---

## 1. Canonical v2 population targets

The v2 model has three distinct extensive quantities. They must never be conflated.

### 1.1 Primary metal input ledger

Provisional user targets over the full 1000-year world horizon:

- primary Cu: **1,000,000 t** total across the broader river/world system;
- of that, Atesis-associated source production target: **200,000 t Cu**;
- primary Sn: **30,000 t**;
- Au and Ag: explicit primary budgets required, but **not numerically fixed in Step 1**;
- As, Pb, Fe, Zn and trace elements: source/alloy ledgers, with primary budgets or conditional concentrations to be fixed by metallurgy/isotope passes.

These are primary-input ledgers. Recycling is internal throughput and may not be added as new primary metal.

For each chemical species `m`:

```
primary_input_m
= terminal_loss_m
+ terminal_retirement_m
+ final_active_inventory_m
+ numerical_residual_m
```

Transfers, repairs, broker residence and remelts are internal throughput.

### 1.2 Object-episode ledger

Target:

- **50,000,000 physical object episodes whose metal lineage crosses the Atesis at least once during the 1000-year horizon.**

An object episode is one physically distinct artefact life between manufacture/remelt boundaries. Remelting ends one object episode and may create another object class.

This is deliberately **not** the same thing as unique metal mass.

The big field must carry an extensive `represented_object_episodes` quantity. It does not need one NetCDF row per physical object.

### 1.3 Metal-lineage ledger

A metal lineage persists through:

```
ore -> smelted metal -> ingot/object -> use -> broker/scrap -> remelt
    -> different object -> repair -> transfer -> remelt -> ... -> final deposition
```

The same atoms can contribute to several object episodes. Therefore:

```
object_episode_mass_throughput >= primary_metal_mass
```

without violating conservation.

---

## 2. Recycling semantics

Provisional high-recycling schedule:

- after the **first/pristine object life**, probability of metal recovery/remelt: `r0 = 0.60`;
- after an already recycled object life, recovery/remelt probability: `r1 = 0.85` by default, later made class/context/time dependent.

Under the simple geometric limit, expected object lives per surviving metal parcel are:

```
E[L] = 1 + r0/(1-r1) = 5
```

before mass losses, mixing and terminal sinks are included.

This is a calibration prior, not a law. Step 4 will make recovery depend on object class, prestige, context, guild/broker access, date and deposition hazard.

### 2.1 Required mass-count closure

The requested 50M object episodes cannot be forced to represent all 200 kt of Atesis-source Cu without checking the implied class masses.

Define:

```
M_cross_primary = primary metal mass belonging to lineages that ever cross Atesis
T_episode_mass  = cumulative metal mass embodied across their object episodes
N_episode       = 50,000,000
mean_episode_mass = T_episode_mass / N_episode
```

`mean_episode_mass` must match the modeled class mixture rather than being silently imposed.

Therefore v2 introduces a calibrated quantity:

```
f_cross_objectized
```

= fraction of primary metal input whose descendant lineages enter the explicit 50M Atesis-crossing object-episode population.

The remainder is still conserved in bulk metal, ingots, untracked local objects, industrial/workshop stock, other river systems or terminal sinks. Step 5 may solve `f_cross_objectized` from the final class-mass distribution.

No rescaling may create or destroy metal simply to hit 50M.

---

## 3. Chronology

World duration is fixed at **1000 calendar years**.

Exact endpoints remain parameters in Step 1:

```
start_bc - end_bc = 1000 years
```

because Step 2 must inspect where the twelve guild histories actually make sense before freezing dates.

Unlike v1, time is not only an abstract propagation step. v2 carries calendar-compatible durations:

- `calendar_date_days` or equivalent integer day offset;
- `transit_days`;
- `dwell_days`;
- `current_object_age_days`;
- `metal_lineage_age_days`.

NetCDF may store day offsets as integers while exposing BC-year summaries.

---

## 4. Movement: 2–5 km/day means active travel speed

Canonical land/ordinary active-travel prior:

```
v_active ~ bounded distribution on 2..5 km/day
```

This applies only while a person/animal/boat cargo episode is actively progressing through the relevant transport mode. It is **not** multiplied by every day of an artefact lifetime.

For an edge/leg of physical length `d`:

```
travel_days = d / v_active
```

plus mode/context delay.

Most elapsed time is dwell:

```
object lifetime = transit days + household/use dwell + workshop dwell
                + broker/storage dwell + repair dwell + other stationary time
```

Step 4 will define separate movement priors for river craft, sea transport, mountain/portage, pack travel and warrior/merchant movement. Step 1 only requires that physical distance and elapsed time remain separable.

---

## 5. Three distances, not one

Every lineage state carries:

1. `ore_distance_km`
   - source field to first smelting/manufacturing entry;
   - fixed after initial entry for each source contribution, aggregated mass-weightedly when sources mix.

2. `cumulative_metal_distance_km`
   - all movement experienced by the metal after metallurgical entry;
   - never resets at remelt.

3. `current_object_distance_km`
   - movement since the most recent true remelt/recasting that created the current artefact episode;
   - resets on remelt, not on repair.

Developer truth also reports:

```
total_metal_journey_km = ore_distance_km + cumulative_metal_distance_km
```

with invariant:

```
total_metal_journey_km >= cumulative_metal_distance_km >= current_object_distance_km >= 0
```

A final grave sword may therefore have:

```
current_object_distance_km = 90
cumulative_metal_distance_km = 780
ore_distance_km = 140
```

without any contradiction.

---

## 6. Big-field sufficient state

The direct-NetCDF field must be richer than v1 but still aggregate packets rather than instantiate 50M Python objects.

Each active packet/state carries extensive mass/count plus intensive or moment coordinates.

### 6.1 Extensive ledgers

- `metal_mass_kg[species]` or a compact basis sufficient to reconstruct species mass;
- `represented_object_episodes`;
- active packet intensity / represented metal lineage count;
- primary-vs-recycled mass contribution;
- terminal sink fluxes.

### 6.2 Lineage moments

Retain v1:

- recycle/remelt expectation;
- repair expectation;
- source entropy;
- physical crossings;
- transport-field crossings.

Add v2:

- `ore_distance_km`;
- `cumulative_metal_distance_km`;
- `current_object_distance_km`;
- `expected_remelt_count` distinct from repairs;
- `expected_workshop_transition_count`;
- `broker_cycle_expectation`;
- `technical_memory_fraction`;
- `current_object_age_days`;
- `metal_lineage_age_days`;
- `transit_days` and/or transit fraction;
- source-mixture age/mixing depth summary;
- guild-exposure summary hooks for Step 2;
- chemistry/isotope covariance hooks for Step 3.

For profile condensation, store weighted means **and covariance blocks where correlations matter**. v1 independent marginal sampling is insufficient for variables such as remelt count, source entropy, cumulative distance and technical-memory survival.

---

## 7. Event algebra

### 7.1 Transfer

On movement distance `d` taking `dt` days:

```
cumulative_metal_distance += d
current_object_distance += d
transit_days += dt
metal_lineage_age += dt
current_object_age += dt
```

No new metal or object episode is created.

### 7.2 Dwell/use

```
dwell_days += dt
metal_lineage_age += dt
current_object_age += dt
```

Repair hazards, ownership transfer, guild contact and loss hazards may act during dwell.

### 7.3 Repair

```
repair_count += 1
technical_memory *= repair_memory_survival
```

Current-object identity and distance survive. A repair may add a small mass contribution with a different source/guild history; that becomes a mixture branch in explicit selected-object lineage materialization.

### 7.4 Broker/scrap residence

The object episode may end without immediate remelt:

```
object -> scrap/broker stock -> dwell/move -> remelt
```

Metal continues accumulating distance and age during broker movement/storage.

### 7.5 Remelt/recast

```
remelt_count += 1
represented_object_episodes += newly_created_episode_count
current_object_distance = 0
current_object_age = 0
technical_memory *= remelt_memory_survival
workshop_transition_count += relevant_transition
```

Chemistry/source ancestry is mixed/evolved, not reset.

### 7.6 Terminal deposition/loss

Absorbs mass/object episode into archaeological, unrecovered, destroyed or other terminal sinks according to the observation model. Recycling remains internal throughput.

---

## 8. Metals and chemistry basis

Step 1 reserves a multi-species mass vector at minimum for:

```
Cu, Sn, As, Pb, Ag, Au, Fe, Zn
```

plus sparse trace chemistry and isotope state supplied by Step 3.

Do not encode Sn, Ag or Au merely as decorative trace labels if they are intended as real economy-scale metal streams.

The 30 kt Sn ledger is primary input. Tin retained through recycling remains internal metal mass; process losses and additions must be explicit.

Gold and silver primary totals remain unresolved parameters in Step 1 rather than invented values.

---

## 9. Representation of 50 million objects

The simulation target is **50M represented physical object episodes**, not 50M in-memory Python objects and not necessarily 50M NetCDF rows.

A state row can carry:

```
represented_object_episodes = 12_438.7
represented_metal_mass_kg = ...
```

and split/merge conservatively during propagation.

The master may still become larger than v1 because it carries richer exact state coordinates and a broader 1000-year connected world, but storage growth comes from scientific state, not repeated object dictionaries.

Selected player objects remain individually instantiated only after acquisition.

---

## 10. Spatial/world scope

The v2 world is not an Atesis-only economy.

Primary Cu target:

```
~200 kt Atesis-associated sources
~800 kt distributed across other connected river/coastal/source systems
```

The Atesis is a tracked crossing surface inside a larger circulation world.

Every state/lineage should therefore support crossing counters for named hydrological/physical surfaces, of which Atesis is one distinguished diagnostic:

```
ever_crossed_atesis
atesis_crossing_count
first_atesis_crossing_date
last_atesis_crossing_date
```

The 50M target is calibrated against `ever_crossed_atesis == true`.

Do not force all Atesis-sourced copper to count as Atesis-crossing object episodes; source origin and crossing history are separate variables.

---

## 11. Direct-NetCDF computation pattern

No giant JSON intermediate.

```
world/guild/source model
  -> stream production cohort
  -> propagate aggregate metal/object packets through time and graph
  -> append exact loss/terminal states directly to chunked NetCDF master
  -> update online profile statistics + covariance blocks + sparse exposures
  -> discard cohort Python state
  -> next cohort
  -> finalize indexes/CSR and conservation ledger
  -> derive runtime v2 from master
```

The master is allowed to be substantially larger and richer than v1. The runtime should remain compact enough to ship/query because exact state rows are removed after profile condensation.

---

## 12. Step-1 invariants

The eventual v2 builder may not be considered ready for the full run until small synthetic tests satisfy:

1. Cu/Sn/Au/Ag/etc. mass closure by species.
2. Recycling/remelting never creates primary metal.
3. Object-episode count increases only when a new object is physically manufactured after remelt/recast.
4. `cumulative_metal_distance >= current_object_distance` always.
5. Remelt resets current-object distance and age; repair does not.
6. Active-travel velocity lies in the configured physical range when that mode uses the 2–5 km/day prior.
7. Dwell time dominates most normal object lifetimes; distance is not inferred from lifetime alone.
8. `ever_crossed_atesis` is a true path/crossing property, not source-region identity.
9. 50M Atesis-crossing object episodes is reached by calibration of physical throughput/counts, not by violating mass closure.
10. Profile condensation preserves the important joint distributions, not only independent marginal variances.
11. POARI remains outside hidden artefact selection.
12. Same world seed reproduces the same latent world.

---

## 13. What Step 2 must receive from Step 1

Step 2 may now assume:

- a 1000-year calendar world;
- explicit workshop/guild transition counts;
- object and metal ages/distances are separate;
- remelt creates a new manufacturing episode;
- repairs preserve object identity;
- guild exposure may be accumulated through several careers/workshops;
- the big field has sparse hooks for guild history without hard-coding a single final guild;
- class/object counts and metal mass are separate conserved ledgers.

Step 2 must define the twelve guild skill systems and their spatiotemporal evolution without changing these accounting rules.
