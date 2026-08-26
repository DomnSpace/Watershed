# Atolia direct-NetCDF v2 preparation — Step 4.9/5

## Workshop tool ecology: guild progression emerges from what a workshop can actually do

Step 4.9 replaces vague verbs such as `can hammer`, `can cast`, `can polish`, or even `anneal_control = 0.72` with a physical workshop ecology.

The core proposition is:

```text
A craft skill is not an abstract unlock.
It is a reproducible operation performed by a person,
using a particular tool/work surface/furnace/jig,
on a particular material and geometry,
inside a bounded process window.
```

A workshop therefore develops partly by accumulating, modifying, wearing out, copying, inheriting and specializing tools. Guild competence emerges from **people × tools × materials × repeated operations × measurement/feedback**.

This also creates archaeological truth: workshops, graves, hoards and smith burials can contain individually evolved tools whose biographies are informative and occasionally funny.

A smith can genuinely end life owning:

```text
Goldringfinehammer v26
Hufschmiedhammer v1
```

because twenty-six generations of tiny finishing-hammer refinement mattered to their normal work, while one crude/heavy horse-related hammer entered the kit because that smith happened to service many horses.

The names above are player/debug labels, not claims about historical German terminology.

---

## 1. Remove binary craft verbs

Do not store:

```text
can_hammer = true
can_anneal = true
can_cast = true
```

Instead an operation is feasible only if its requirements overlap the workshop's current capability envelope.

For operation `o`:

```text
feasible(o,w,m,g) =
    tool_match
  × work_surface_match
  × thermal_match
  × material_match
  × geometry_match
  × operator_skill
  × fixture/control_match
```

where `w` is workshop, `m` material state and `g` workpiece geometry.

Quality is then conditional on how far inside the feasible process envelope the operation occurs.

---

## 2. Tool instances are first-class physical objects

Every persistent workshop tool can have:

```text
tool_id
family
subtype
version_lineage
maker_workshop
maker_person
birth_time
material
mass
length
working_face_geometry
working_face_area
edge_radius
surface_roughness
hardness_proxy
toughness_proxy
handle_length
handle_material
balance_position
mounting
wear_state
repair_count
regrind_count
rehandle_count
owner_history_ptr
operation_history_summary
parent_tool_ids
prototype_generation
```

Not every throwaway object requires a global row. Persist tools that materially constrain process capability, acquire a lineage, or can become archaeological objects.

---

## 3. Hammering becomes impact mechanics

A hammer operation has at minimum:

```text
hammer_mass
impact_velocity
impact_energy = 0.5*m*v^2
face_area
face_curvature
edge_radius
impact_angle
strike_position_error
strike_angle_error
repetition_rate
operator_fatigue
workpiece_temperature
workpiece_thickness
workpiece_support_compliance
```

Nominal average contact pressure is not sufficient for real contact mechanics, but the simulation can use calibrated effective stress/strain transfer functions rather than pretending all hammers are equivalent.

Two 1 kg hammers with different faces are not the same process instrument.

A narrow polished face can concentrate deformation and finish a small region. A broad flatter face can planish. A peen can drive directional deformation. A heavy sledge requires different support and often another worker. Tiny punches/chasing tools can transmit hammer energy into geometry far below the hammer face scale.

---

## 4. Hammer/tool families

The world generator should support at least these functional families, with historically plausible subsets varying by place/time:

```text
heavy forging hammer / sledge
medium forging hammer
small forging hammer
planishing hammer
raising hammer
sinking/bossing hammer
cross-peen-like directional hammer
straight-peen-like directional hammer
round-faced finishing hammer
small precision/fine hammer
riveting hammer
chasing hammer
punch-driving hammer
stake-driving/utility hammer
wood/rawhide/soft-faced mallet
stone hammer where applicable
```

The exact modern labels are taxonomy conveniences. Generated archaeological descriptions should distinguish evidence from reconstruction.

A single workshop does not need all of them. Tool specialization should emerge from repeated work.

---

## 5. The other half of hammering is the thing underneath

A hammer without a work surface tells us little.

Persist/support families such as:

```text
stone working slab
flat metal anvil
small bench anvil
stake anvil
beaked/horned stake
rounded raising stake
mushroom stake
edge stake
swage-like groove/block
wooden stump
sinking hollow/block
mandrel
rod
former
backing plate
riveting support
```

Important state:

```text
surface_area
curvature
local_radius
groove geometry
height
mass
foundation stiffness
surface hardness
surface roughness
wear grooves
```

A 300 g hammer on a fine stake can accomplish something a 3 kg hammer on a flat slab cannot.

---

## 6. Precision is not one number

Workshop precision decomposes into dimensions:

```text
position_precision_mm
angle_precision_deg
thickness_control_mm
mass_dosing_precision_g
repeatability
symmetry_error
surface_flatness
edge_radius_control
hole_position_error
join_alignment_error
temperature_estimation_error
cycle_timing_error
```

Each comes from a different combination of tools, fixtures, sensory skill and repetition.

A workshop can therefore be extraordinarily precise in ring finishing while mediocre at alloy dosing.

---

## 7. Measurement tools belong in the workshop ecology

Bronze Age measurement need not imply modern calibrated metrology. Include practical comparison/control devices:

```text
balance / scale
weights
measuring rod
cord
straightedge
set of reference lengths
compass/divider-like geometry tool where evidenced/plausible
scribing point
marking punch
templates
mould master/pattern
thickness comparison gauge/template
volume vessel
colour references embodied in master/apprentice practice
sound/tap comparison
reference objects
```

Some 'measurement' exists as embodied comparison rather than a surviving dedicated instrument.

Store both explicit instruments and learned sensory discriminations.

---

## 8. Thermal plant is also tooling

Replace `furnace quality` with components:

```text
hearth/furnace geometry
lining
crucible type
crucible capacity
crucible material
crucible age
lid/cover practice
tuyere count
tuyere geometry
bellows count
bellows capacity
airflow controllability
fuel type
fuel preparation
charge size
thermal inertia
hot-zone uniformity
oxidation exposure
slag access
casting distance from furnace
```

Temperature remains uncertain and physically inferred; workshops do not receive magical thermocouples.

---

## 9. Casting toolchain

Casting capability emerges from:

```text
mould material
mould architecture
one/two/multipart mould skill
core capability
wax modelling tools
pattern tools
gate geometry
riser/feeder practice
venting
mould preheat practice
pouring vessel/crucible handling
tongs
pouring coordination
charge capacity
metal cleanliness
```

An excellent wax modeller with poor melt control creates different defects from a superb furnace crew using a bad mould.

---

## 10. Cutting, scraping, drilling, punching and abrasion

Tool families:

```text
chisel
hot-cut/cold-cut tool
punch
drift
awl
scraper
burin/graver
file-like abrasive/cutting tool where appropriate
drill
bow-drill components
reamer
abrasive stone
sand/abrasive powders
polishing stone
burnisher
cloth/leather/wood polishing carrier
```

Each has material, edge geometry, hardness/wear and size.

A hole is therefore a process history, not merely `hole=true`.

---

## 11. Joining toolchain

Joining operations include:

```text
rivet formation
rivet setting
mechanical tabs
folds/seams
cramps/staples
socket fitting
interference/friction fitting
binding/composite assembly
solder/braze-like joining where historically appropriate
```

The physical truth records preparation, alignment, joining tool and resulting residual stress/defect state.

---

## 12. Tool manufacture is recursive

Tools make tools.

A workshop's current tool set determines what replacement/improved tools it can manufacture:

```text
T_(n+1) = make_or_modify(T_n, skill, available_material, observed_need)
```

This is the basis of `Goldringfinehammer v26`.

`v26` means the 26th meaningful lineage modification/prototype in that workshop tradition, not modern product engineering. Many generations can be tiny:

```text
face narrowed 4%
face polished more finely
handle shortened
balance shifted
edge radius changed
material replaced
face reworked after mushrooming
copied from master's preferred tool
combined properties of two predecessors
```

Most changes are neutral or worse. Repeated successful production selects useful variants.

---

## 13. Tool selection pressure

For each operation type, workshop experience accumulates outcome statistics:

```text
success
reject
repair required
cycle time
operator effort
material loss
crack occurrence
surface defect
shape deviation
customer/recipient acceptance
```

A tool variant gains reproduction probability when it repeatedly improves outcomes relevant to that workshop.

No omniscient optimizer is required.

---

## 14. Tool lineages can branch

```text
FineHammer-v11
   +-- v12a broader face -> sheet finishing lineage
   +-- v12b smaller face -> ring lineage
             +-- ... -> Goldringfinehammer-v26
```

Do not force one global version sequence. Version labels can be generated locally from lineage depth and nickname.

---

## 15. Tool nicknames are diegetic compression

The simulation has exact parameters; UI does not need to dump them.

A workshop/person can nickname a repeatedly associated tool from:

```text
material
shape
owner
place
job
object family
customer association
animal association
visible mark
lineage
```

Hence:

```text
Goldringfinehammer v26
Hufschmiedhammer v1
Mellaun sheet stake v7
Old Bent Peen v14
Red Crucible Tongs v3
```

Localization can later translate labels without changing hidden tool truth.

---

## 16. Horses are an excellent example of demand-driven accidental specialization

Do not assume a modern horseshoe industry where chronology does not support it. But horses generate legitimate metal/craft demand: harness fittings, bits, cheek pieces, rings, fasteners, vehicle/tack hardware, repairs and general camp/animal-associated work.

A smith serving horse-heavy clients can consequently accumulate:

```text
larger repair hammer
punch/drift sizes suited to tack fittings
ring mandrels
riveting tools
portable repair equipment
```

The humorous `Hufschmiedhammer v1` UI nickname can mean 'the big hammer he always used when the horse people arrived', without asserting modern nailed horseshoe practice.

---

## 17. Portable versus fixed workshop kits

Every tool has portability cost.

```text
portable_personal
pack_animal_portable
cart/boat_portable
fixed_workshop
```

This directly connects guild mobility to Step 4 transport.

A travelling smith carries a constrained kit and may borrow local anvils/hearths. A river workshop can move substantially heavier equipment by boat. A settled specialist can maintain massive fixed surfaces and larger furnaces.

Thus technological capability changes when the same craftsperson moves.

---

## 18. Person skill and workshop capability must stay separate

```text
person knows process + workshop lacks tool => constrained
excellent tool + novice operator => constrained
master + excellent tool + wrong alloy => constrained
master + complete kit + repeated familiar job => high reproducibility
```

Workshop capability is therefore approximately:

```text
C(operation) = intersection(
    operator envelope,
    tool envelope,
    support envelope,
    thermal/material envelope,
    fixture/measurement envelope
)
```

This is deliberately not an arithmetic average: one missing critical element can dominate failure. Weak-link-sensitive/harmonic diagnostics are appropriate here and **must not be clipped into 1**.

---

## 19. Guilds become distributions of workshop traditions

The 12 guilds should not be twelve static skill vectors.

Each guild is a population/network of workshop/person lineages with characteristic demand, tool ecology and transmission pathways.

For guild `g`:

```text
Guild_g(t) = {
    workshops,
    masters/apprentices,
    active tool lineages,
    object demand distribution,
    process traditions,
    geographic contacts,
    quality reputation,
    production volume
}
```

The guild identity is statistical and historical, not a magical class restriction.

---

## 20. Guild progression is endogenous

A guild grows in a location when:

```text
raw material available
+ customers/demand
+ enough successful masters
+ apprentice reproduction
+ tool reproduction
+ workshop viability
+ transport/contact
+ reputation
```

It contracts when:

```text
masters die without transmission
demand collapses
ore/fuel access changes
war destroys workshop
migration removes practitioners
critical tools are lost
quality declines
better competing workshop arrives
production becomes too infrequent to maintain precision
```

---

## 21. What a 'skill level' now means

A displayed skill level is a projection of the underlying ecology.

For example `fine ring finishing = 0.84` may summarize:

```text
operator strike precision
small hammer lineage quality
stake/mandrel suitability
abrasive sequence
anneal/work sequence
visual comparison skill
repetition count
recent reject rate
```

The scalar exists for gameplay/query speed; it is not the physical source of competence.

---

## 22. Guild specializations can now become concrete

Instead of generic `hammering guild`, guild/workshop differences appear as tool populations.

Illustrative specializations:

```text
weapon-heavy tradition:
  larger forging faces, edge/straightening tools, casting capacity,
  edge-work sequences, repair tools

sheet/vessel tradition:
  raising/sinking hammers, stakes, planishing surfaces,
  thickness comparison, anneal repetition

ornament/fine-work tradition:
  tiny hammers, punches, gravers, mandrels, fine abrasives,
  balances/weights, highly repeated micro-geometry

casting tradition:
  mould/pattern/wax tools, crucible ecology, tongs, furnace control,
  feeder/venting traditions

repair/recycling tradition:
  cutting/breaking tools, sorting, crucibles of multiple capacities,
  joining kit, patch/rivet tools, composition heuristics

horse/vehicle-associated workshop:
  rings, fittings, bits/tack/vehicle hardware, robust punches/drifts,
  portable repair kit
```

The canonical 12 guilds can overlap several of these; Step 5 should map their existing identities rather than replace their names.

---

## 23. Tool quality changes metallurgical truth

Tool state feeds directly into object state.

Examples:

```text
worn rough hammer face -> surface marking / local strain irregularity
poor anvil support -> bending / thickness heterogeneity
excellent planishing pair -> low thickness variance / characteristic finish
bad tongs -> interrupted pour / contamination risk / spill risk
cracked crucible -> contamination / catastrophic loss
worn punch -> hole geometry change
fine abrasive sequence -> lower roughness / erased earlier marks
repeated cold work -> deformation texture / hardness increase
anneal between passes -> recrystallization changes
```

Dr Corrosion can later infer parts of the workshop toolchain from the artefact.

---

## 24. Tool marks become evidence

Generate latent tool-mark families from actual tool geometry and wear state:

```text
hammer-face impressions
peen directionality
punch profile
chisel width/angle
file/abrasion direction
polishing sequence
mould seam/parting evidence
stake-supported deformation signatures
rivet setting marks
```

Observation is noisy and preservation-dependent.

This creates a path from a microscopic mark to a hidden workshop lineage without hard-coding the answer.

---

## 25. Workshop fingerprinting

A workshop can develop a statistical signature from:

```text
tool geometry distributions
mould conventions
alloy dosing habits
anneal/work sequence
surface treatment
repair style
measurement biases
recurrent defects
```

Never make fingerprints perfectly unique. Shared teachers, copied tools and trade must create overlap.

---

## 26. Tools travel too

Tool mobility events include:

```text
master migration
apprentice departure
inheritance
gift
trade
capture/theft
workshop destruction salvage
boat loss
grave deposition
hoard deposition
scrap recycling
```

A tool can therefore move a process tradition without moving an entire guild.

This is a much better technology-transfer mechanism than simply increasing a regional tech scalar.

---

## 27. Smith graves/urns become unusually informative archaeological contexts

If a craftsperson is buried/deposited with a subset of tools, the assemblage is sampled from the actual owned kit, modified by funerary selection.

Thus a smith-associated burial might contain:

```text
fine hammer lineage v26
old heavy utility hammer v1
three punches
worn ring mandrel
broken tongs
balance weight
```

The missing furnace and anvil do not imply the smith lacked them; they were fixed/shared workshop assets.

The game can distinguish:

```text
owned
used
workshop-shared
buried
recovered archaeologically
```

---

## 28. Tool lifetime and maintenance

Tools age under use:

```text
face mushrooming
edge rounding
plastic deformation
abrasive wear
fracture
handle loosening
handle replacement
oxidation
thermal damage
crucible cracking
anvil/stake surface grooving
```

Maintenance actions alter geometry and may create a new meaningful version.

A beloved v26 fine hammer may physically contain much older material than its current working-face geometry.

---

## 29. Tool material recycling

Tools themselves enter the metal circulation model.

```text
tool -> repair -> reforge -> descendant tool
     -> break -> scrap -> unrelated artefact
     -> grave/hoard/loss -> archaeological find
```

Therefore the 50-million-object v2 world should not classify metal permanently as `artefact` versus `tool`; these are life-history roles.

---

## 30. Apprentices inherit biased subsets

Apprentice learning samples:

```text
master operations observed
operations actually practiced
master tool access
personal tool inheritance
copied tool geometry
local demand
mistakes survived
```

An apprentice can inherit the master's Goldringfinehammer geometry without understanding why it works, preserve it faithfully for three generations, and then lose the associated technique.

Conversely, a clever apprentice can improve a tool before mastering the process.

---

## 31. Tool innovation does not require modern invention narratives

Most innovation is local adjustment:

```text
this face is too broad
this handle tires me
this mould traps gas here
this stake radius makes the bowl crease
this punch breaks the ring
this crucible is too large for small gold melts
```

The model proposes small perturbations under experienced need and retains variants according to actual production outcomes.

Rare cross-domain transfer can combine previously separate solutions.

---

## 32. Gold/silver versus bulk bronze creates strong tool divergence

Precious-metal workshops handle small masses where loss is expensive. Selection pressure favors:

```text
small controlled tools
mass accounting
fine collection/recovery
precise geometry
surface finish
repeatable small crucibles
small-scale joining
```

Bulk bronze/weapon workshops favor different force/capacity envelopes.

This naturally makes `Goldringfinehammer v26` plausible while the same workshop's seldom-used large hammer remains primitive.

---

## 33. Force envelope, not 'hammer level'

For each impact tool estimate an operation envelope:

```text
E_impact range
momentum range
contact area range
local strain effectiveness
workpiece thickness range
workpiece temperature range
precision envelope
fatigue cost
```

Operator strength affects velocity/control, but bigger force is not monotonically better.

Fine work often progresses by **better force placement and geometry**, not more force.

---

## 34. Two-person and team operations

Some operations require coordination:

```text
master directs + striker uses sledge
bellows operators + furnace master
multi-person crucible/pour handling
large sheet/object support
```

Store team coordination experience. A great individual smith cannot reproduce every large workshop operation alone.

---

## 35. Workshop layout matters modestly

Represent coarse functional layout, not a CAD model for every workshop:

```text
hearth_to_anvil_distance
hearth_to_mould_distance
water access
light quality
ventilation proxy
covered/open work area
storage security
floor recovery potential
```

This affects hot-transfer time, precious-metal recovery, contamination, fire risk and throughput.

---

## 36. Demand drives the tool ecology

The object demand stream determines what gets practiced.

```text
warrior clients -> weapons/repair
horse/vehicle traffic -> fittings/rings/repair
elite centre -> fine ornaments/prestige objects
river port -> repair, fittings, mixed scrap, diverse imported objects
agricultural settlement -> utilitarian tools/fittings
ritual centre -> repeated specialized forms
```

Therefore geography affects technology through actual jobs rather than regional bonuses.

---

## 37. Guild reputation must be object-derived

Reputation updates from delivered outcomes:

```text
survival in use
visible finish
failure/repair rate
prestige clients
repeat orders
rare difficult successes
```

A guild can temporarily coast on reputation, but poor output eventually reduces demand and therefore the practice needed to preserve its tool traditions.

---

## 38. High quality becomes self-reinforcing but fragile

```text
high quality
 -> more demanding orders
 -> more repetition
 -> better tool specialization
 -> more apprentice attraction
 -> potentially higher quality
```

But:

```text
master death + tool loss + demand interruption
 -> process envelope collapses
 -> quality falls rapidly
```

This implements the requested rule that guilds slowly die unless they continue producing high quality, without an arbitrary decay timer.

---

## 39. Tool ecology explains technological mosaics

A location need not have one `technology level`.

It may simultaneously possess:

```text
world-class sheet raising
ordinary weapon casting
poor precious-metal weighing
excellent rivet repair
obsolete furnace design
```

That heterogeneity is desirable and archaeologically interesting.

---

## 40. Proposed NetCDF v2 groups

```text
/workshops
/persons
/tools/catalogue
/tools/instances
/tools/lineage
/tools/ownership_events
/tools/maintenance_events
/tools/use_summary
/work_surfaces
/furnaces
/crucibles
/moulds
/measurement_tools
/process/operations
/process/outcomes
/guilds/membership
/guilds/reputation
/guilds/demand
```

Use ragged pointer arrays for variable-length memberships and event histories.

---

## 41. Do not store every hammer blow

Fifty million object biographies make blow-level storage absurd.

Use operation episodes:

```text
operation_episode_id
object_id
person_id
workshop_id
operation_type
tool_set_ptr
start_material_state
process_parameter_summary
strike_count / cycle_count
mean + variance of effective energy/precision
outcome_state
```

Generate individual blow distributions transiently if needed; retain sufficient statistics and exceptional events.

---

## 42. Tool-use summaries

For each persistent tool maintain compact counters/distributions:

```text
uses_by_operation
estimated_impacts
mass_processed
workpiece_material histogram
temperature-regime histogram
failure_count
repair_count
owner_count
```

This permits both wear evolution and archaeological interpretation without terabytes of logs.

---

## 43. Pointer structure

Example:

```text
object.operation_ptr -> operation episodes
operation.tool_ptr -> tool IDs
tool.parent_ptr -> predecessor tools
tool.owner_ptr -> ownership events
workshop.tool_ptr -> active kit
person.skill_event_ptr -> learning events
guild.workshop_ptr -> workshop memberships
```

This is exactly the sort of sparse relationship NetCDF v2 should preserve while materializing only selected career truth at runtime.

---

## 44. Tool parameter dictionary versus instances

Millions of nearly identical hammers should not duplicate strings/metadata.

Store:

```text
tool archetype dictionary
+ compact instance deltas
+ lineage parent pointers
+ wear state
```

A tool becomes a full standalone record only where history/variation warrants it.

---

## 45. Generated labels are not physics

`Goldringfinehammer v26` is generated from the hidden state. The hidden state remains numerical.

For example:

```text
family = hammer
functional_cluster = fine_precious_ring
mass = 0.214 kg
face_A = 93 mm²
face_B = 147 mm²
face_radius_A = ...
handle_length = ...
lineage_depth = 26
```

Changing localization or nickname does not alter the world.

---

## 46. Archaeological preservation

Tools have context-dependent preservation/recovery probabilities. Small precious-work tools may be lost differently from large fixed anvils; iron-bearing later tools have different corrosion trajectories from bronze/stone tools.

Do not infer absence of craft from absence of a complete toolkit.

---

## 47. Career integration

The 300 private finds can now include:

```text
finished artefact
scrap fragment
ingot
workshop debris
crucible fragment
mould fragment
tool
tool fragment
smith-associated grave/urn assemblage
```

A Level-1 player may initially identify only `small bronze hammer`; late research could infer it belonged to a fine-work lineage whose characteristic marks occur on several otherwise unrelated objects.

That is a much stronger late-game reveal than a guild ID printed into the object.

---

## 48. Guild inference becomes scientific

The hidden truth knows workshop/guild history. The player sees evidence:

```text
alloy
microstructure
tool marks
mould evidence
joining style
repair style
isotopes
geography
chronology
```

The game asks the player to infer collaboration/tradition/contact rather than simply unlock a guild label.

---

## 49. Validation targets

Before v2 mass generation test:

```text
same person + different tool kit -> meaningfully different output
same kit + different person -> meaningfully different output
same hammer + different work surface -> meaningfully different output
fine tool lineage improves its target task more than unrelated tasks
tool specialization follows demand
unused specialist tools decay/wear/vanish rather than magically upgrading
apprentice transmission is imperfect
mobile workshops lose fixed capabilities
river/boat mobility permits heavier kit than foot mobility
rare tools can travel independently of guilds
smith burial samples owned/shared kit imperfectly
operation summaries reproduce expected object physical state
```

---

## 50. Anti-RPG invariants

1. No binary `can hammer`.
2. No universal hammer quality scalar.
3. More force is not automatically better.
4. Tool geometry and work surface both matter.
5. Precision is multidimensional.
6. Person skill and workshop equipment are separate.
7. Tool evolution is local and task-selected.
8. Tool version numbers describe lineage, not chronological technological epochs.
9. A guild does not own exclusive physical processes.
10. Guild progression emerges from workshop populations, demand, production, transmission and tool ecology.
11. Technology can regress when people/tools/demand disappear.
12. Tools themselves have metal/material biographies and can be recycled.
13. Archaeological tool absence does not imply process absence.
14. Player-facing tool names never replace numerical hidden truth.
15. Do not store every blow; preserve operation sufficient statistics and exceptional events.
16. Weak-link capability aggregation must preserve harmonic sensitivity and must never clip the powered sum before the generalized-mean root.

---

## 51. What this does to the 12-guild skill tree

The final guild skill tree should now be generated in three layers:

```text
LAYER A — physical capabilities
    force/precision/thermal/geometry/material process envelopes

LAYER B — workshop traditions
    characteristic tool lineages + operation sequences + quality control

LAYER C — game/research concepts
    the 12 named guild branches Dr Corrosion can learn to recognize
```

Layer C must never directly mutate Layer A. Research only improves the player's ability to observe and infer the already-instantiated hidden world.

This preserves the core career premise: the player's archaeology was physically instantiated before the career began.

---

## 52. Step 5 handoff

The final v2 world build should therefore no longer ask merely:

```text
Which guild made this object?
What was its skill level?
```

It asks:

```text
Which people/workshop episodes touched this metal?
Which exact tool lineages and work surfaces constrained each operation?
What material state entered each operation?
What process envelope was attempted?
What physical state resulted?
Which traditions were transmitted, copied, modified or lost?
What evidence survived into the archaeological object?
```

That gives us the intended scale transition:

```text
12 guilds
   ↓
workshop populations
   ↓
craftspeople + apprentices
   ↓
actual tool kits and evolving tool lineages
   ↓
operation episodes
   ↓
physical metallurgy
   ↓
50 million circulating object biographies
   ↓
loss/deposition/preservation
   ↓
300 private career finds
   ↓
Dr Corrosion slowly reconstructs the hidden workshop world
```

The joke hammer is therefore not decoration. `Goldringfinehammer v26` beside `Hufschmiedhammer v1` is exactly the compressed archaeological consequence of an endogenous technology model: **this smith did this job constantly, got extraordinarily good at it, and for some reason also had to deal with a lot of horse people.**
