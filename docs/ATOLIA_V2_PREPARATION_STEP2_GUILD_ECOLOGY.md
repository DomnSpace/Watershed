# Atolia direct-NetCDF v2 preparation — Step 2/5

## Twelve evolving metallurgical communities of practice

Status: preparation pass 2 on `atolia-metal-lineage-v1`.

This pass upgrades the twelve existing developer guild coordinates into an autonomous technology ecology over the 1000-year v2 world. They remain **latent communities of practice**, not literal named corporations, ethnic groups, political factions, hereditary castes, or fixed historical institutions.

The model objective is:

```text
resources + local demand + inherited technique + practice + quality feedback
    -> viable workshop tradition
    -> objects with characteristic performance and manufacturing traces
    -> object-specific lifetime mobility ecology
    -> apprentices/repairers/brokers carry some skills elsewhere
    -> local variants diverge, merge, specialize or disappear
```

A guild exists only while people repeatedly perform its difficult operations well enough to reproduce them.

---

## 1. Historical/technical basis and caution

The current twelve coordinates are useful because they describe operations actually relevant to copper-alloy craft: mould preparation/casting, socket/core geometry, raised sheet, annealing, cold-working edges, mechanical joining, repair/reworking, surface treatment, wire/rod work, lost-wax modelling, scrap batching/recycling, and finishing/polishing.

They should not imply industrial standardisation. Archaeometallurgical work on European Bronze Age weapons shows substantial variation in alloy, microstructure and hardness even within regions and periods; production depended on smith skill and material behaviour rather than one universal recipe. Repeated hammering/cold work, annealing and sharpening are empirically attested for weapons, including the Verona-area Olmo di Nogara material. Lost-wax, cast-plus-reworked and highly localized technical repertoires also occur in different Bronze Age settings.

Accordingly, v2 treats each guild as a **skill attractor in a continuous workshop skill space**.

The twelve IDs remain stable because downstream diagnostics already use them, but the names are developer mnemonics.

---

## 2. Workshop and practitioner state

Each workshop lineage `w` at node `x`, date `t`, has:

```text
W_w(x,t) = (
    people,
    masters,
    apprentices,
    skill_vector,
    tool_capital,
    thermal_capability,
    fuel_access,
    clay_stone_access,
    metal_stock,
    customer_demand,
    reputation,
    recent_quality,
    production_volume,
    idle_time,
    lineage_parent,
    external_contacts
)
```

The skill vector is continuous over a technical basis such as:

```text
casting
moulding
core/socket control
gating/feeding
thermal cycling
cold deformation
hot/warm deformation
sheet raising/planishing
edge work
joining/riveting
repair/reworking
surface treatment
decoration
rod/wire forming
lost-wax modelling
batching/recycling
refining/metal sorting
finishing/polishing
```

No workshop needs to belong exclusively to one guild. Its guild affinity vector is derived from this skill state.

For guild `g`:

```text
A_g(w,t) = similarity(skill_w(t), prototype_g(t,x))
           × viability_g(w,t)
           × lineage_memory_g(w,t)
```

with overlap allowed.

---

## 3. Skill growth, practice and forgetting

A difficult technique should not remain alive because it once existed nearby.

For skill coordinate `k`:

```text
K_k(t+dt) = K_k(t)
          + learning_k(practice, mentors, successful output)
          + transfer_k(incoming craftspeople/contact)
          - forgetting_k(idle_time, complexity, practitioner loss)
          - disruption_k(workshop failure, migration, supply collapse)
```

A practical continuous form:

```text
dK_k/dt = α_k * P_k * (1-K_k)
        + β_k * C_k
        - δ_k * I_k * K_k
        - μ_k * mortality_gap * K_k
```

where:

- `P_k` = recent production episodes actually requiring skill `k`;
- `C_k` = contact/apprenticeship transfer pressure;
- `I_k` = idle fraction for that operation;
- `δ_k` grows with tacit complexity;
- `mortality_gap` rises when masters die without trained successors.

### 3.1 Tacit-complexity hierarchy

Low forgetting / easy reacquisition:

- basic melting;
- simple open mould casting;
- rough grinding;
- simple bend/hammer repair.

Medium:

- split mould alignment;
- controlled core/socket casting;
- repeated anneal/work cycles;
- consistent edge hardening by work;
- riveted assembly;
- controlled scrap batching.

High:

- thin raised-sheet vessels without tearing;
- difficult large/thin castings;
- complex wax models and casting trees;
- fine surface/inlay traditions;
- reliable alloy/temperature judgement from sensory cues;
- high-quality sword blade finishing and differential working.

If production demand disappears for decades, the high-complexity end decays fastest.

---

## 4. Quality feedback and autonomous survival

A guild lineage does not survive because of a fixed persistence constant.

For each produced object episode `o`, compute physical quality:

```text
Q_o = Q_geometry
    × Q_cast_integrity
    × Q_alloy_fit
    × Q_thermal_history
    × Q_working_fit
    × Q_joining_if_needed
    × Q_finish_if_functional
```

Object-class weights differ. A vessel cares strongly about thin-wall integrity and joining; a sword cares strongly about casting defects, alloy/work balance, edge treatment and final geometry.

Workshop reputation follows delayed performance:

```text
R_w(t+1) = (1-λ_R) R_w(t)
         + λ_R * observed_successes
         - penalty * catastrophic_failures
```

Demand then responds to quality, availability and social preference:

```text
D_w ∝ local_need × accessibility × f(reputation) × class_specialism
```

A workshop/guild can therefore:

- grow because its objects last and are requested;
- expand through apprentices;
- shrink if it cannot source fuel/clay/tin/scrap;
- lose high skills during low production;
- survive as a simpler descendant;
- split when apprentices establish elsewhere;
- merge technically after sustained contact;
- go locally extinct.

There is no guaranteed 1000-year persistence for any guild.

---

## 5. Apprentice and master careers

Practitioners are not full 50M-object agents. They are a much smaller hidden workforce layer.

Each practitioner career has approximately:

```text
birth/cohort
entry age
apprenticeship duration
mastery vector
home workshop lineage
career locations
contact workshops
object classes practiced
annual production/practice counts
retirement/death
```

Guild spread happens mainly through people and repeated practice, not by teleporting a `guild_id` field.

### 5.1 Skill transmission

Apprentice learning probability for skill `k` depends on:

```text
master_skill_k
× number_of_observed/practiced_operations
× workshop production frequency
× task access
× apprentice aptitude/noise
```

A rarely executed elite operation may fail to transmit even if the master knows it.

### 5.2 Migration and branching

A trained craftsperson can establish a daughter workshop if:

```text
local demand × material access × social opportunity > establishment threshold
```

Daughter skills are noisy subsets/variants of the parent:

```text
K_daughter = K_parent * transmission_mask + innovation_noise
```

This naturally creates regional variants without declaring new hard-coded guilds.

---

## 6. Object class determines mobility ecology

Step 1 language about generic `travel_days` is superseded here.

Objects accumulate movement as part of the life of the thing/person/animal/network they belong to.

Examples:

- sword/spear/dagger: carried by warriors, escorts, retainers, migrants; frontier patrol/ranging random walk;
- horse gear/fittings: follows animal herd/service/war movement;
- sickle/chisel/axe: mainly local agricultural/woodworking radius, occasional owner relocation or exchange;
- vessel: household/elite/merchant residence with lower daily random displacement but occasional long transfer;
- ornament/ring/pin/bead: follows person through marriage, mobility, exchange and inheritance;
- ingot/scrap: broker/merchant/workshop transport network, often river/shore biased;
- figurine/prestige object: court/sanctuary/gift/exchange mobility;
- repaired object: mobility conditional on owner ecology before and after repair.

Thus guild ecology influences movement indirectly through **what it makes and for whom**.

For object `o`, movement is a random walk on the transport graph with class/carrier-dependent activity:

```text
Δx_o(t) ~ movement_kernel(class, owner_role, season, frontier_pressure,
                          river_access, horse_access, social_transfer)
```

The 2–5 km/day prior belongs only to relevant terrestrial daily displacement kernels, not to a scheduled trip itinerary.

---

# 7. The twelve v2 guild coordinates

## G-01 — Split-Mould

### Technical core

Reusable or carefully prepared two-part/closed mould casting, alignment, gating and feeding, shrinkage allowance, extraction and post-cast cleanup.

### Real workshop needs

- mould stone or appropriate clay/temper;
- mould preparation area and drying time;
- crucibles/hearth/fuel;
- controlled metal quantity and fluidity;
- ability to judge fill and avoid major porosity/misrun;
- finishing tools after casting.

### Strong objects

Axes, spearheads, daggers, swords, fittings and other repeatable cast geometries.

### Skill bottlenecks

Mould alignment, core stability where used, gate placement, temperature judgement and repeated dimensional consistency.

### Ecology

Thrives where repeated demand justifies mould investment: weapon/tool production hubs, redistribution nodes and workshops with dependable metal supply.

Can spread moderately well because mould concepts are teachable, but high-quality large/thin casting remains tacit.

### Evolution

Early local variants may be broad/simple. Successful lineages specialize toward particular object families. High-volume nodes can increase dimensional regularity; disrupted lineages fall back toward simpler casting.

### Connections

Strong co-development with G-02 and G-05; feeds rough castings to G-04/G-12; receives scrap batches from G-11.

---

## G-02 — Socket-Rib

### Technical core

Structural casting geometry: sockets, ribs, hollow/core-controlled forms, haft interfaces and mechanically efficient reinforcement.

### Needs

- stable cores and core positioning;
- understanding of wall thickness and metal flow;
- mould/core materials that survive casting;
- repeatable haft dimensions;
- feedback from actual tool/weapon breakage.

### Strong objects

Socketed axes/spearheads, fittings, selected chisels and reinforced forms.

### Skill bottleneck

This is partly geometry knowledge rather than merely hotter furnaces. Poor execution gives core shift, weak walls, incomplete sockets or bad hafting.

### Ecology

Grows in places with repeated utilitarian demand and direct user feedback. It can become widespread because the performance advantage is visible, but regional socket/rib conventions diverge.

### Evolution

Lineages improve structural efficiency through use failures. Contact between G-01 and G-02 can create excellent production centers; separation allows locally distinctive geometry.

---

## G-03 — Raised-Sheet

### Technical core

Casting a manageable blank followed by repeated raising/sinking/planishing and annealing into thin sheet forms.

### Needs

- appropriate hammer/stake/anvil surfaces, including wood/stone/metal tools;
- repeated heat cycles;
- fuel and controlled annealing;
- high practitioner dexterity;
- metal sufficiently ductile for repeated deformation;
- time: this is labour intensive.

### Strong objects

Vessels, sheet ornaments, fittings, selected body armour/large sheet traditions where chronology permits.

### Skill bottleneck

Avoiding tearing, wrinkling and excessive thinning while preserving geometry. High tacit complexity.

### Ecology

Requires sustained demand from households/elites/ritual or exchange systems able to pay labour cost. Likely concentrates in larger craft nodes and wealthy demand zones rather than every village.

### Evolution

Highly prone to local extinction if demand collapses. Successful centers export apprentices and finished objects over large ranges. Can leave strong regional signatures in hammering/anneal sequences.

### Connections

G-04 is nearly obligatory at high quality; G-06 important for assembled sheet; G-08/G-12 for visible prestige finish.

---

## G-04 — Anneal-Line

### Technical core

Controlled cycles of deformation and annealing; practical recognition of work hardening, cracking risk, recrystallization and recoverable ductility.

### Needs

- controllable hearth;
- fuel;
- repeated manipulation/inspection;
- sensory temperature judgement;
- awareness of alloy-dependent response.

### Strong objects

Cross-cutting rather than class-specific: weapons, tools, wire/rod, raised sheet, ornaments.

### Evidence logic

Repeated annealing and hammering are well supported in analysed Bronze Age weapons, including Olmo di Nogara. G-04 therefore becomes a foundational technical tradition rather than a decorative guild label.

### Ecology

Can diffuse widely because many crafts benefit from it, but mastery varies. It may survive as partial know-how even where specialist lineages collapse.

### Evolution

Expected to become increasingly embedded in several traditions, producing convergence rather than one exclusive guild. Its local skill strength depends heavily on practice volume.

### Connections

Strong with G-03, G-05 and G-09; relevant to G-07 repairs.

---

## G-05 — Cold-Edge

### Technical core

Post-cast blade/tool working: hammering/cold reduction, selective annealing where needed, edge shaping, sharpening and work-hardening appropriate to alloy.

### Needs

- anvils/stakes/hammers;
- abrasives/grinding stones;
- repeated access to functional weapons/tools for feedback;
- metallurgical judgement of how far a particular alloy can be worked.

### Strong objects

Swords, daggers, knives, axes, sickles, chisels, spearheads.

### Reality constraint

Do not model a single standard sword recipe. Actual Bronze Age swords show broad variation in tin content, working intensity, hardness and microstructure. The guild represents embodied adaptation to alloy and function.

### Ecology

Thrives wherever demanding cutting/impact tools are used heavily. Frontier/warrior demand can sustain high specialization; agricultural/tool economies sustain simpler branches.

### Evolution

Performance selection is strong: bad edges fail visibly. High-quality lineages may gain reputation quickly and move with warrior/customer networks.

### Connections

G-01 rough casting + G-04 thermal control + G-05 edge completion is one major weapon-production pathway; G-12 may finish the visible surface.

---

## G-06 — Rivet-Knot

### Technical core

Mechanical joining and assembly: rivets, clinching, seams, fitted components, patch attachment and other joining appropriate to period/material evidence.

### Needs

- accurately fitted components;
- drilling/punching/perforation capability where needed;
- rivet stock;
- support/anvil surfaces;
- alignment and sequence planning.

### Strong objects

Vessels, fittings, composite weapon elements, sheet assemblies and repairs.

### Caution

Do not automatically assume advanced solder/brazing for every place/time. Joining mode is an explicit subskill selected from evidence-compatible possibilities.

### Ecology

Often co-located with sheet and repair craft. Can persist in practical repair networks even when elite production declines.

### Evolution

Local joining conventions are highly diagnostic because they combine geometry, available stock and learned assembly sequence.

---

## G-07 — Repair-Loop

### Technical core

Diagnosis, patching, re-edging, reshaping, rehafting interfaces, joining repairs, selective annealing and deciding when an object is still worth repairing versus remelting.

### Needs

- access to circulating used objects;
- low-volume flexible toolset;
- broad rather than narrow skill repertoire;
- knowledge of failure modes;
- scrap/addition stock.

### Strong objects

Nearly all durable tools/weapons/vessels, especially high-value or difficult-to-replace items.

### Ecology

Follows users more readily than high-capital production guilds. Repairers can thrive at frontier nodes, markets, passes, ports and dispersed settlements.

### Evolution

May be one of the strongest vectors of cross-guild technical contact because repairers see objects made elsewhere. However, repair skill does not imply ability to reproduce every object from scratch.

### V2 significance

Repairs preserve current-object identity and some earlier manufacture. They can add a new guild episode without resetting `current_object_distance`.

---

## G-08 — Surface-Skin

### Technical core

Surface preparation, decoration, polishing systems, possible tinning/gilding/inlay or contrasting surface treatments **only when local date/material evidence supports the particular operation**.

### Needs

- abrasives;
- fine tools/punches;
- clean controlled workspace;
- decorative material supply;
- patrons willing to pay visible labour.

### Strong objects

Ornaments, vessels, figurines, fittings and selected weapons.

### Ecology

Demand-sensitive and status-sensitive. Often clusters where elite/ritual exchange supports time-intensive visible work.

### Evolution

High stylistic mobility but technique may travel independently of motif. Some branches disappear rapidly when patronage collapses; simpler polishing survives through G-12-like practice.

---

## G-09 — Wire-Ring

### Technical core

Making slender rod/wire-like stock by hammering, rolling/forging, twisting, bending and annealing; forming rings, pins, beads and fine components.

### Important correction

`Wire-Ring` does **not** imply a modern drawplate by default. Drawn wire is a separately gated subtechnology if/where supported. The baseline Bronze Age operation is elongated rod/wire stock produced through deformation and finishing.

### Needs

- fine hammers/anvils;
- annealing access;
- gauges/judgement for thickness consistency;
- repeated fine deformation;
- small but reasonably clean metal charges.

### Strong objects

Rings, pins, ornaments, bead components and fittings.

### Ecology

Low material mass but high labour/skill. Can travel with personal-adornment demand and may survive in small workshops better than large casting traditions.

### Evolution

Likely to cross-fertilize strongly with G-04 and G-12. Regional variants may differ more in forming sequence and finish than chemistry.

---

## G-10 — Wax-Branch

### Technical core

Lost-wax/cire-perdue modelling for forms where reusable split moulds are inconvenient: figurines, complex ornaments, selected vessels/fittings and elaborate one-off geometry.

### Needs

- wax/fat/resin-like modelling materials appropriate to local practice;
- refractory investment/clay knowledge;
- drying/firing control;
- gating/venting intuition;
- destructive mould process and therefore no simple reusable mould economy.

### Strong objects

Complex figurines, ornaments, fittings and other geometrically elaborate castings.

### Ecology

High complexity and often prestige-driven. Requires sustained specialist practice; vulnerable to local extinction when commissions disappear.

### Evolution

Can appear as regional high-skill branches rather than one pan-European tradition. Finished objects can travel much farther than the practitioners who know the full process.

### Connections

G-01 shares casting knowledge; G-08/G-12 commonly handle visible finishing.

---

## G-11 — Scrap-Sum

### Technical core

Sorting, batching, remelting and combining scrap/ingots/returns; practical control of usable composition despite uncertain metal histories.

### Needs

- access to scrap streams, markets or workshop returns;
- weighing/portion judgement, whether formal or embodied;
- crucibles/hearth/fuel;
- recognition of metal behaviour/colour/fracture/flow;
- storage/broker organization.

### Strong objects

Not a single class. It feeds ingots, repair stock and new casting batches across the economy.

### V2 significance

This guild is central to metal lineage. It changes **metal identity without requiring long object travel**. A local broker stock can mix metal that previously travelled through several systems.

### Ecology

Thrives at redistribution hubs, ports, river nodes, large settlements and persistent workshops. Can also exist as small founder/scrap economies.

### Evolution

High recycling rates create strong selection for people who can make heterogeneous scrap usable. Quality feedback penalizes badly mixed brittle/poorly cast batches. Successful batching traditions may become highly valuable but leave weaker morphological signatures than casting/finishing guilds.

### Connections

Especially G-07 repair and G-01 casting; eventually every manufacturing branch can depend on G-11 stock.

---

## G-12 — Fine-Polish

### Technical core

Grinding, abrasion, sharpening, smoothing, scraping/burnishing and final surface/edge finishing.

### Needs

- abrasive stones/sands/pastes;
- fine hand tools;
- substantial labour time;
- visual/tactile quality judgement.

### Strong objects

Weapons, tools, ornaments, vessels, figurines and prestige surfaces.

### Ecology

Broadest customer base but intensity varies enormously. Basic finishing is ubiquitous; exceptional fine finishing is a specialist skill supported by prestige demand.

### Evolution

The guild should therefore be bimodal: a widespread low-level background competence and narrower high-quality specialist lineages. High specialists can disappear while basic finishing persists.

### Connections

Works downstream of nearly every manufacturing tradition, especially G-05, G-08 and G-10.

---

## 8. Guild geography is endogenous

Step 2 does **not** assign one permanent homeland to each guild.

Instead every node/time has a viability field:

```text
V_g(x,t) = f(
    metal_supply,
    tin/scrap access,
    fuel,
    mould/clay/stone resources,
    water/river/port access,
    customer class demand,
    population/workforce,
    existing skill seed,
    neighboring guild complementarity,
    disruption
)
```

A guild may have several independent centers.

Examples of expected tendencies, not hard-coded truths:

- G-01/G-02: high-volume casting/tool/weapon hubs and metal redistribution nodes;
- G-03: richer/larger craft centers with vessel/sheet demand;
- G-04: diffuse cross-cutting thermal competence around active metalworking;
- G-05: weapon/tool production and frontier-demand zones;
- G-06/G-07: assembly/repair markets, ports, passes and frontier nodes;
- G-08/G-10/G-12 high-skill branches: prestige/ritual/elite demand centers;
- G-09: personal-adornment craft clusters and mobile fine craft;
- G-11: scrap/broker/redistribution hubs, ports and large workshops.

The geographical map emerges from those needs plus seed variation and contact.

---

## 9. Guild diffusion equation

For guild-affinity/skill density `A_g(x,t)`:

```text
A_g(x,t+dt) = local_learning
            + apprentice_migration
            + workshop_branching
            + contact_transfer
            - forgetting
            - demographic/workshop extinction
```

Not a simple isotropic diffusion PDE.

The migration/contact term follows the same graph used by people and objects, but guild skill transmission has its own kernel:

```text
T_g(x->y) ∝ practitioner_mobility
          × relationship/contact frequency
          × establishment viability at y
          × skill transmissibility
```

High-tacit skills spread more slowly than visible simple techniques.

---

## 10. Innovation, divergence and convergence

### Innovation

Small technical changes arise during repeated production:

```text
ΔK ~ N(0, σ_innovation)
```

but are retained only if they improve quality/efficiency or are socially preferred often enough to be transmitted.

### Divergence

Two daughter workshops with the same ancestor can diverge because of:

- different alloys/source stocks;
- different objects demanded;
- different tool/fuel access;
- founder effect in transmitted skills;
- different failure feedback.

### Convergence

Different lineages can independently approach similar successful technical solutions. Therefore similar guild affinity is **not sufficient proof of common ancestry**.

The hidden truth stores both:

```text
skill_similarity
lineage_genealogy
```

as independent dimensions.

This is essential for the late archaeological game.

---

## 11. Guild lineage events

The v2 hidden world supports:

```text
FOUND workshop
BRANCH daughter workshop
MIGRATE workshop/practitioner
MERGE practice/contact network
SPECIALIZE skill subset
GENERALIZE repair/broker repertoire
LOSE_SKILL operation
REACQUIRE operation
EXTINCT workshop lineage
REVIVE descendant from neighboring transmission
```

A `REVIVE` is not resurrection of the same hidden lineage unless actual practitioners/knowledge connect it genealogically.

---

## 12. Production and quality gate

Every workshop chooses production from demand and capability, not a fixed class list.

For class `c`:

```text
production_pressure(w,c,t)
  = demand(x,c,t)
  × capability(w,c,t)
  × material_feasibility(w,c,t)
  × reputation(w,c,t)
```

The object is produced only if pressure crosses a stochastic threshold and workshop capacity is available.

Quality then feeds back into future demand and skill learning.

This implements the requested rule:

> guilds slowly die off unless they keep producing high quality continuously.

More precisely, a guild can survive low output if the skill is simple or transmission is supported elsewhere, but high-complexity traditions lose competence rapidly under long idle periods.

---

## 13. Quality is class-conditional

There is no single universal `quality` scalar internally. Keep a vector:

```text
Q = (
    casting_integrity,
    geometry_accuracy,
    structural_efficiency,
    ductility_control,
    hardness,
    edge_performance,
    joining_integrity,
    thin_sheet_integrity,
    surface_finish,
    repair_integrity
)
```

A class-specific functional:

```text
Q_class = q_c · Q
```

produces the performance/reputation feedback.

This prevents a brilliant polisher from being treated as a brilliant socket caster.

---

## 14. Tool capital and consumables

The big model should track capabilities, not every hammer.

Per workshop store compact stocks/capacities:

```text
hearth_temperature_control
crucible_capacity
mould_capability
core_capability
hammer_anvil_capability
sheet_stakes_capability
fine_tool_capability
abrasive_access
joining_tool_capability
wax_investment_capability
scrap_sorting_capacity
fuel_availability
```

These constrain possible operations.

Tools themselves can be objects in the economy where useful, but the guild model need not instantiate every tool to know whether a workshop can perform an operation.

---

## 15. Resource shocks and local extinction

Guild ecology reacts to:

- copper/tin shortage;
- loss of charcoal/fuel access;
- trade-route shifts;
- settlement decline;
- elite demand collapse;
- warfare/frontier demand increase;
- migration;
- workshop destruction;
- arrival of competing/allied practitioners;
- increased scrap availability.

The same shock affects guilds differently. Tin shortage may strengthen G-11 recycling while depressing some high-tin weapon traditions. Frontier demand may strengthen G-05/G-07 while prestige-surface production contracts.

---

## 16. Relationship to the 50M object episodes

Guilds do not directly move 50M objects.

They create object episodes with:

```text
maker workshop
guild-affinity vector
class
quality vector
owner/use ecology
repairability
recycling attractiveness
```

Those properties determine the subsequent lifetime random walk and recycle/remelt hazards.

On remelt, the next object can be made by a different workshop/guild, creating a metal lineage such as:

```text
G-01/G-04 axe
 -> G-07 repair
 -> G-11 broker/remelt
 -> G-03/G-06 vessel
 -> G-11 remelt
 -> G-05/G-12 sword
 -> G-07 frontier repair
 -> deposition
```

The guild history therefore sits *inside* the metal history.

---

## 17. NetCDF sufficient state for guild ecology

The full v2 direct-NetCDF master should not store every practitioner biography on every metal state.

### World/workshop tables

Store explicit workshop/practitioner-lineage tables separately:

```text
workshop_id
parent_lineage
node/time span
skill vector through time/cohorts
capacity
reputation/quality moments
practitioner counts
resource capability
```

### Metal/object state

Each active packet only needs:

```text
current_workshop/guild exposure
expected workshop transition count
technical_memory_fraction
guild exposure moments/CSR
current object class
represented object episodes
```

### Profile runtime

Condense guild exposure to sparse vectors:

```text
profile_guild_ptr
profile_guild_id
profile_guild_weight
```

plus moments for transition count and technical-memory survival.

The selected 300 artefacts then materialize explicit guild episode sequences conditioned on these statistics.

---

## 18. Archaeological observability of guild history

Different operations leave different measurable traces.

The guild model should emit physical consequences, never direct labels.

Examples:

- G-01/G-02: mould seams, gates, internal defects, socket/core geometry, dimensional patterns;
- G-03/G-04: grain structure, deformation texture, anneal/recrystallization, wall-thickness patterns;
- G-05: edge hardness gradient, cold work, sharpening geometry;
- G-06/G-07: rivets, seams, patches, joins, repair interfaces, mixed local chemistry;
- G-08/G-12: surface layers, abrasion/polish traces, decoration/tool marks;
- G-09: rod/wire morphology, deformation/anneal sequence;
- G-10: complex casting geometry, investment/mould signatures where recoverable, gates/internal porosity;
- G-11: mixed source chemistry, higher provenance entropy, alloy heterogeneity/remelt signatures.

Late-game guild reconstruction must infer latent traditions from these observations rather than reading `G-05` from the object.

---

## 19. Calibration targets for one full v2 world

Before the final big run, small/medium ensembles should demonstrate:

1. all twelve skill attractors can emerge somewhere under plausible conditions;
2. none is guaranteed global survival for 1000 years;
3. several have multiple independent regional branches;
4. high-tacit techniques go locally extinct under sustained low production;
5. high-quality lineages produce more apprentices/daughter workshops on average;
6. poor-quality lineages contract unless protected by unusually strong demand/no competition;
7. G-04/G-05-style thermal/cold-work competence can converge independently;
8. G-11 recycling expands at high scrap availability without becoming the sole explanation for all metal;
9. workshops retain mixed affinities rather than collapsing to one-hot guild labels;
10. guild genealogy and technical similarity are measurably non-identical;
11. object-class mobility distributions respond to the things guilds make;
12. metal lineages accumulate multiple guild episodes naturally through repair/remelt.

---

## 20. What Step 3 receives

The isotope/trace pass can now assume that every metal lineage may encounter multiple guild/workshop episodes and remelts.

Step 3 must therefore determine, for each evidence channel:

```text
what is mass-conserved
what mixes linearly
what fractionates or changes during smelting/remelting
what acquires process contamination
what analytical covariance is expected
what guild/workshop operations can alter it
what survives repeated recycling
```

Crucially, isotope/source evidence and guild evidence remain separate latent dimensions. A G-05 sword can be made from metal that previously passed through G-11 and G-03 lineages, and similar G-05 technique can arise in workshops using entirely different ores.
