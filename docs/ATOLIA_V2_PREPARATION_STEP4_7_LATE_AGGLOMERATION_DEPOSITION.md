# Atolia direct-NetCDF v2 preparation — Step 4.7/5

## Late-tail agglomeration: hoards, wet/coastal basins, urnfield landscapes, and repeated deposition attractors

Step 4.7 adds a late-biography process that Step 4 did not fully capture: objects and metal batches that have already travelled, changed owners, been repaired/recycled, or entered scrap/ritual/wealth stores may **agglomerate again** shortly before terminal deposition.

This is not a rule that hoards belong at urnfields, hidden lakes, coasts, Sparta, or Atsipadhes. It is a neutral mechanism allowing repeated human use of particular landscape classes to create spatially correlated terminal deposits.

## 1. Biography extension

```text
production -> circulation -> ownership -> repair/recycling -> circulation
                                              |
                                              v
                                    late aggregation pool
                                              |
                    +-------------------------+-------------------------+
                    |                         |                         |
                 recovery                 dispersal              terminal deposit
                                                                      |
                                             hoard / wet / funerary / ritual / loss
```

An aggregation pool may contain complete artefacts, broken objects, ingot-like metal, tools, ornaments, weapons, scrap, remelt feed, and objects with unrelated earlier biographies.

## 2. Agglomeration is not instantaneous hoarding

Represent an explicit temporary state:

```text
aggregation_id
start_time
location_distribution
owner/group context
member pointers
metal_mass
object_count
composition heterogeneity
recovery_probability
split_probability
addition_rate
removal_rate
terminal_hazard
```

Pools can grow, split, be recovered, partly remelted, robbed, moved, or abandoned.

## 3. Late-tail attractor field

For location x and time t:

```text
A_late(x,t) =
    w_wet   * wetland_margin
  + w_lake  * lake_or_sink_margin
  + w_coast * coastal_hidden_basin
  + w_river * river_crossing_or_old_channel
  + w_fun   * funerary_landscape
  + w_urn   * urnfield_activity
  + w_rit   * repeated_ritual_activity
  + w_set   * settlement_edge
  + w_route * route_convergence
  + w_hide  * concealment_quality
  + w_mem   * place_memory
  + w_cris  * conflict_or_crisis
```

The terms are independent latent mechanisms. A site may score highly for several reasons without the model deciding that one archaeological interpretation is correct.

## 4. Coastal hidden lakes / enclosed basins

Add a landscape class for small or partially concealed water/wetland basins near coasts or navigable corridors:

```text
coastal_hidden_basin
```

It includes physically admissible:

- karst/depression lakes,
- spring-fed basins,
- lagoon remnants,
- marsh pockets,
- seasonally flooded depressions,
- enclosed valley-bottom wetlands,
- former channels cut off from active drainage.

These can become deposition attractors because they combine water, boundary character, concealment, repeated route use, and preservation. The mechanism is generic; named places are diagnostics/case-study priors only when independently supported.

## 5. Sparta/Laconia handling

Do not encode `Sparta = hidden lake hoard node`.

Instead, the Eurotas/Laconian world may contain inferred palaeowetlands, old channels, springs, enclosed basins, coast-facing routes and repeated settlement/funerary landscapes where the palaeohydrological ensemble permits them.

A read-only later diagnostic can ask whether generated terminal clusters resemble patterns around Laconia/Sparta. Named-site desirability cannot alter the attractor field.

## 6. Atsipadhes / peak-sanctuary handling

Atsipadhes Korakias is evidence for repeated Bronze Age ritual activity at a Cretan peak sanctuary, not evidence for a Late Bronze Age metal hoard or hidden lake. Therefore the implementation distinguishes:

```text
observed_ritual_place
observed_metal_deposition
inferred_deposition_attractor
```

Peak sanctuaries and other repeatedly visited places may contribute `place_memory` and `repeated_ritual_activity` where chronologically admissible, but the generator may not fabricate a hoard at Atsipadhes to satisfy the model.

## 7. Urnfield co-location without circularity

Urnfield landscapes can become one late-tail attractor because funerary activity creates repeated visits, memory, boundaries, paths, pyre/metal handling and persistent social knowledge of place.

But enforce:

```text
P(hoard | urnfield) > P(hoard | generic cell)
```

only through explicit causal variables, never through a hard `urnfield => hoard` mapping.

Possible causal contributors:

```text
repeated visitation
funerary procession routes
metal accompanying cremation/deposition
pyre-derived fragments
boundary marking
ancestral place memory
settlement proximity
shared wetland/river-edge preference
later intentional deposition
```

The model must also generate:

- urnfields without hoards,
- hoards without urnfields,
- wet deposits without funerary activity,
- accidental losses in the same landscape,
- later deposits reusing older funerary places.

## 8. Shared-location recurrence

A location can become a recurrent attractor through memory:

```text
M_place(t+1) = decay * M_place(t)
             + observed_local_activity
             + successful_recovery_memory
             + funerary_memory
             + ritual_memory
```

Different groups need not know the original reason a place was used. Later reuse can therefore create palimpsests separated by decades or centuries.

## 9. Agglomeration kernel

For circulating object i entering a late-tail context:

```text
P(join pool j) = sigmoid(
    b0
  + b_distance * proximity(i,j)
  + b_owner    * ownership_relation
  + b_metal    * recyclable_value
  + b_type     * contextual_compatibility
  + b_crisis   * crisis_state
  + b_ritual   * ritual_context
  + b_fun      * funerary_context
  + b_memory   * place_memory_j
)
```

Membership does not imply simultaneous manufacture or common provenance.

This is especially important for recycled long-distance metal: one hoard may contain lineages accumulated over hundreds of kilometres and multiple prior lives.

## 10. Hoard internal structure

Preserve internal covariance rather than treating a hoard as N independent draws:

```text
shared terminal location
shared terminal time distribution
shared final owner/group context
member-specific production provenance
member-specific travel history
member-specific repair/recycle history
member-specific guild history
member-specific chemistry/isotopes
```

Thus a hoard can be terminally coherent but metallurgically heterogeneous.

## 11. Urnfield-linked metal pathways

Funerary landscapes need several separate metal channels:

```text
body-associated object
cremation-altered object
pyre debris
fragment intentionally selected after cremation
object deposited beside urn
metal deposited later into established cemetery
unrelated accidental loss
later hoard reusing cemetery landscape
```

Do not merge these into one `funerary` flag.

Thermal exposure should modify microstructure/surface/oxidation measurements where physically appropriate.

## 12. Wet deposition and preservation

For lake/wetland/coastal-basin deposition, terminal deposition state queries Step 4.5 hydro realization:

```text
water_depth
seasonality
sediment_rate
redox_state proxy
organic sediment probability
channel migration hazard
shore-distance
burial rate
later erosion/exposure
```

This affects corrosion and discovery, not only loss probability.

## 13. Crisis aggregation

Conflict, flight, theft, institutional collapse and owner death can temporarily increase aggregation:

```text
h_aggregate_crisis = f(
    conflict,
    displacement,
    theft,
    market disruption,
    workshop closure,
    owner mortality,
    recovery expectation
)
```

Most crisis caches should still be recoverable. Archaeological hoards are the failed-recovery tail plus deliberate terminal deposits.

## 14. Broker/workshop late pools

Step 4.7 also permits non-ritual agglomeration at:

```text
broker stock
smith scrap pile
foundry remelt batch
merchant cargo
military equipment store
household wealth cache
```

These pools can later be scattered or deposited through fire, destruction, wreck, theft, abandonment, burial, flood or deliberate concealment.

This prevents the model from making every large metal cluster ritual.

## 15. Coastal/boat coupling

Boat travel increases the chance that already aggregated metal moves as a correlated batch.

Cargo/pool movement therefore uses a shared transport event:

```text
aggregation j --boat leg--> new location
```

rather than independently teleporting its members.

Wreck/loss can terminally deposit the whole pool or split it according to event severity and hydrodynamics.

## 16. Tail enrichment, not global domination

Late agglomeration should enrich the extreme archaeological tail without swallowing ordinary losses.

Calibration target conceptually:

```text
majority of represented metal episodes -> recycled/recovered/ordinary loss pathways
small fraction -> aggregation pools
smaller fraction -> unrecovered multi-object terminal deposits
```

Exact rates are Step-5 calibration parameters and must not be fitted solely to known hoard counts because discovery bias is severe.

## 17. NetCDF additions

Suggested sparse groups:

```text
/late_tail/aggregation
/late_tail/membership
/late_tail/place_memory
/late_tail/funerary
/late_tail/terminal_events
```

CSR membership:

```text
aggregation_ptr
aggregation_member_index
```

Per pool:

```text
aggregation_time_start/end
terminal_time
terminal_location
context_mix
mass_total
member_count
recovery_probability
terminal_mechanism
```

## 18. No duplicated object truth

Objects remain in the lineage tables from Steps 1–4.7. Aggregation tables contain pointers only.

No hoard-specific copy of alloy, isotope, guild or manufacture state is allowed.

This preserves the direct-NetCDF pointer philosophy and prevents huge duplicated payloads.

## 19. Validation diagnostics

Print:

```text
aggregation_pool_count
recovered_pool_fraction
partially_recovered_fraction
terminal_multiobject_fraction
median/95p pool size
mass-weighted pool size
within-pool provenance entropy
within-pool guild entropy
within-pool recycle-count distribution
wetland terminal fraction
coastal-hidden-basin fraction
urnfield-associated fraction
urnfield-without-hoard fraction
hoard-without-urnfield fraction
reused-place fraction
mean age spread within terminal pools
```

## 20. Anti-conspiracy / neutrality tests

Run ablations:

```text
A: no place memory
B: place memory but no funerary coupling
C: funerary coupling but no hydro attractors
D: full neutral model
```

Then compare spatial clustering and composition.

Named hypotheses such as Sparta/Laconia, Atsipadhes, Atolia, or specific Urnfield centres are evaluated only after the world is frozen.

## 21. Release invariants

1. Hoards are emergent aggregation/deposition outcomes, not object classes assigned at manufacture.
2. Aggregation may be recovered, split, moved or remelted.
3. Terminally coherent pools retain heterogeneous earlier biographies.
4. Wet/coastal/lake attractors depend on the Step-4.5 hydrological realization.
5. Urnfield association is causal/probabilistic, never a hard co-location rule.
6. Urnfields without hoards and hoards without urnfields must remain common possibilities.
7. Atsipadhes is treated according to its actual evidence class; no fabricated Late Bronze Age hoard is inserted there.
8. Sparta/Laconia is a diagnostic region, not a forced hidden-lake node.
9. Place memory can create repeated deposition palimpsests but decays through time.
10. Crisis concealment is usually recoverable; archaeological caches occupy the failed-recovery tail.
11. Workshop, broker, cargo and household pools remain viable non-ritual explanations.
12. Aggregation uses pointers to existing lineage truth; metallurgy is never duplicated or erased.
13. Named Atoliamaxx hypotheses have no write access to generation.

## 22. Result

Step 4.7 turns terminal deposition from an independent per-object coin flip into a correlated social/landscape process while preserving the full metallurgy underneath it:

```text
ore/mines -> guild/workshop -> object -> carrier lives -> recycling
                                               |
                                               v
                                  late social agglomeration
                                               |
                       hydro + funerary + route + memory landscape
                                               |
                            recovery / remelt / split / deposition
                                               |
                                  archaeological observation
```

The useful consequence is precisely the desired one: **long-travel, multiply recycled metal can re-condense into late hoards at repeatedly meaningful wet, coastal, funerary or route-boundary places, including landscapes that also host urnfields, without encoding those archaeological associations as foregone conclusions.**
