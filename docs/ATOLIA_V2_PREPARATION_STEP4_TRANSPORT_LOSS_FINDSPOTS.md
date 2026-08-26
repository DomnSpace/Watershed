# Atolia direct-NetCDF v2 preparation — Step 4/5

## Carrier random walks, water-mode escalation, war/theft, broker cycles, loss frontlines and archaeological findspots

Status: preparation pass 4 on `atolia-metal-lineage-v1`.

This is the difficult coupled layer. It connects the Step-1 metal/object ledgers, Step-2 autonomous guild ecology and Step-3 geochemical inventories to the places where metal actually moves, changes owners, is repaired/remelted, disappears and can eventually be found.

The governing principle is:

> **Objects do not follow one origin-to-destination route. They undergo carrier-dependent lifetime random walks. Metal survives through several such object lives and may enter increasingly connected transport/broker networks. Loss occurs on dynamic physical frontlines; modern findspots are a later projection of those losses through changing landscapes and discovery.**

No physical object is given a prewritten itinerary.

---

# 1. Correct the movement semantics

The Step-1 wording `travel_days = distance / speed` is superseded as the primary mobility model.

The user-specified 2–5 km/day scale is interpreted as the displacement scale of **active terrestrial movement episodes** when the carrier ecology supports it: e.g. a warrior on patrol/ranging, an animal moving with a herd/retinue, a craftsperson or merchant moving through a local network.

A sword carried for twenty years is not assumed to travel 3 km every calendar day.

Instead each carrier state generates intermittent displacement:

```text
calendar time
 -> stationary/use periods
 -> active random-walk episodes
 -> ownership/social transfer episodes
 -> occasional mode changes (river/boat/sea)
 -> repair/broker/remelt episodes
```

Distance is accumulated only when the carrier/object/metal actually moves.

---

# 2. Carrier state, not generic object speed

Every current object episode has a latent carrier/use state `C`:

```text
C = (
    carrier_role,
    owner_role,
    home_range,
    network_embedding,
    water_access,
    horse_access,
    social_value,
    functional_value,
    portability,
    frontier_pressure,
    conflict_exposure,
    season,
    ownership_age,
    broker_depth
)
```

Suggested carrier roles:

```text
household_local
farmer_craft_local
warrior_frontier
mounted_warrior_or_retinue
mobile_pastoral
merchant_pack
river_boat_cargo
coastal_boat_cargo
open_sea_cargo
court_gift_prestige
marriage_inheritance_personal
repairer_mobile
workshop_stock
broker_scrap_stock
ritual_custody
concealed_hoard
burial_assemblage
```

These are hidden process states, not player-facing cultural labels.

Guilds influence the probability of entering these states through the objects they make, their customers and their workshop locations.

---

# 3. Object-class carrier ecology

The final mobility kernel is conditional on both object class and social/use state.

### Weapons

`sword`, `dagger`, `spearhead`:

- warrior/frontier home-range random walks;
- repeated patrol/ranging displacement;
- war mobilization and return;
- loot/theft and gift transfer;
- occasional long jumps after owner change;
- river/coastal boat access when armies/retinues/merchants use water transport.

A weapon can accumulate hundreds of kilometres from many modest shifts without one planned 800-km journey.

### Horse/transport fittings

`fitting` can instantiate a horse/vehicle-associated role:

- follows animal/vehicle rather than owner's foot movement;
- larger home range;
- higher cross-frontier probability;
- repair/replacement at hubs and military contexts.

### Agricultural/tool classes

`sickle`, `chisel`, `awl`, many `axe`, `knife` episodes:

- strong local mean reversion around settlement/catchment/work site;
- occasional relocation through marriage, seasonal work, migration, exchange or remelt;
- scrap may subsequently enter a much larger network than the intact tool ever did.

### Personal adornment

`ring`, `pin`, `bead`, `ornament`:

- follows owner life history;
- marriage/gift/inheritance can cause discrete long-distance transfer;
- high value-to-mass increases portability and retention;
- grave/ritual deposition can terminate a pristine final episode.

### Vessels/figurines/prestige goods

- mostly residence/court/sanctuary/craft-node dwell;
- low-frequency but potentially very large gift/exchange/merchant transfers;
- strong retention until catastrophe, ritual deposition or remelt.

### Ingot and scrap

- weak household attachment;
- broker/merchant/workshop network dominates;
- high probability of river/coastal transport where available;
- repeated local stock circulation before remelt;
- metal can travel much farther than any one finished object episode.

---

# 4. Random-walk kernel

For active land displacement at time `t`, an object draws a correlated local step rather than a shortest path.

Conceptually:

```text
heading_t+1 = persistence * heading_t
            + attraction(home/work/frontier/market/water)
            + stochastic turn

step_length_t ~ carrier_specific_distribution
```

For ordinary terrestrial active days where the 2–5 km prior applies:

```text
step_length ~ bounded/heavy-middle distribution on roughly 2..5 km
```

Mounted/pack/forced-march states may use separate broader kernels in Step 5 calibration.

The walk is constrained to the transport carrier graph and terrain permeability; it cannot cross mountains/water as Euclidean teleportation.

### 4.1 Mean reversion versus exploration

Use a carrier-specific potential:

```text
U(x) =
    home attraction
  + work/grazing attraction
  + market attraction
  + frontier attraction
  + water-access attraction
  - terrain/cost barriers
```

Household tools have strong home attraction. Warriors have a broader, anisotropic frontier potential. Brokers/merchants have market/water-network attraction.

This creates realistic repeated movement without a fixed destination.

---

# 5. Distance and water-mode escalation

The requested intuition is preserved:

> every step a metal/object has already moved should make it increasingly plausible that it has entered a network where the next movement is by boat and can be substantially longer.

But **distance itself is not mystical causal memory**. The causal state is `network_embedding`: accumulated market/frontier/broker/water contacts that are correlated with previous movement.

Maintain:

```text
network_embedding E_net
water_contact_count
ownership_transfer_count
broker_depth
cumulative_metal_distance
current_object_distance
```

Update `E_net` upward after:

- reaching river/coast/port/market/ford/hub;
- ownership transfer;
- broker entry;
- military mobilization;
- long-range gift/exchange;
- remelt in a high-connectivity workshop.

A weak explicit distance term is retained as a proxy for unrepresented contacts.

Probability of entering a water mode:

```text
logit P_water =
    b0
  + b_access * local_water_access
  + b_net    * E_net
  + b_dist   * log1p(current_or_metal_distance / L0)
  + b_value  * portable_value
  + b_trade  * merchant_or_broker_state
  + b_war    * displacement_pressure
  - b_bulk   * handling_cost
```

### 5.1 Boat movement scale

On water-mode entry, the next displacement kernel has a characteristic scale at least around **2× the comparable terrestrial active step**, with a much longer upper tail for river/coastal/open-sea cargo episodes.

Do not cap boats at exactly twice land distance. `2×` is the mode-change floor/median intuition; merchant or prestige cargo can generate tens-to-hundreds of kilometres in one water episode.

---

# 6. Any shore can matter

Do not encode maritime exchange only between a few named ports.

The physical carrier has a **shoreline/river access surface**:

```text
coast vertices
river-bank/navigation vertices
river mouths
lagoons
estuaries
islands
sheltered embayments
known/latent settlement harbours
beaching-compatible shore
```

Any physically reachable shore point can generate embark/disembark with probability depending on:

```text
shelter
slope/beachability
settlement/market intensity
boat availability
river/sea connectivity
weather/season
cargo bulk/value
local conflict
```

Named ports are high-intensity examples, not the only legal water transitions.

### 6.1 Water graph

Water movement is sparse and physical:

```text
river reach -> river reach
river -> estuary/lagoon
shore -> nearby shore
shore -> island
island -> island/shore
coastal -> open-sea jump when state permits
```

Coastal sailing receives a lower generalized cost than arbitrary open-sea crossing. Open-water willingness increases with merchant/prestige network embedding and appropriate vessel access.

---

# 7. Dynamic palaeogeography

The findspot model cannot use only modern coastlines/rivers.

V2 needs time-indexed physical surfaces:

```text
shoreline(x,t)
navigable_river(x,t)
palaeochannel(x,t)
lagoon/wetland(x,t)
delta distributary(x,t)
floodplain(x,t)
pass/land corridor(x,t)
```

At minimum use 25-year physical snapshots with interpolation; finer event timing remains continuous/stochastic.

The northern Adriatic is a key reason: Bronze Age coastal/lagoon landscapes have shifted enough that former sites can now be submerged, buried or reclaimed.

### 7.1 River migration

Rivers are not static lines.

Each alluvial river has probabilities for:

```text
channel migration
avulsion
overbanks/flooding
cutoff/oxbow formation
mouth migration
delta progradation/retreat
```

A metal lost in a live channel can later lie in:

```text
abandoned palaeochannel
floodplain sediment
wetland
reclaimed land
modern river
marine/lagoon sediment
```

Thus old riverbeds naturally become elongated archaeological find/loss bands.

---

# 8. Value increases mobility through social transfer

Do not simply multiply physical speed by value.

Define portable value:

```text
V* = workmanship/status/scarcity/function
     adjusted by mass, bulk and fragility
```

Higher `V*` increases:

- probability of retention rather than discard;
- gift/exchange/inheritance transfer;
- theft/loot attractiveness;
- merchant/broker entry;
- long-distance ownership changes;
- repair rather than immediate remelt for prestige objects.

It can therefore increase cumulative distance while sometimes **reducing ordinary accidental-loss hazard** because owners guard valuable things.

This creates the desired non-monotonic behavior:

```text
high value -> travels farther and is retained longer
           -> more war/theft/boat exposure
           -> fewer trivial household losses
           -> potentially spectacular terminal contexts
```

---

# 9. Theft and loot are transitions, not just loss

Theft usually changes possession first.

```text
owner A -> stolen/loot state -> conceal/sell/gift/remelt/keep -> owner B
```

Hazard increases with:

```text
portable value
war/conflict
market density
frontier instability
low custody
```

Possible outcomes:

- rapid local concealment;
- movement with raiders/army;
- sale into broker network;
- identity-destroying remelt;
- discard during pursuit/flight;
- terminal hoard if never recovered.

This is a major mechanism for long-distance metal without requiring long-distance formal trade.

---

# 10. War field

War is represented as a spatiotemporal pressure field, not only named battles.

```text
W(x,t) = conflict intensity / mobilization / insecurity
```

Generated from a combination of:

```text
frontier gradients
settlement/resource competition
population shocks
trade-route stress
exogenous chronology priors where justified
stochastic conflict outbreaks
```

War modifies several hazards simultaneously:

```text
warrior movement ↑
mounted movement ↑
boat evacuation/transport ↑
theft/loot ↑
weapon repair demand ↑
workshop displacement ↑
hoard concealment ↑
catastrophic abandonment ↑
combat loss ↑
grave deposition context changes
```

The model should therefore produce broad conflict belts and moving frontiers rather than one battle-node magnet.

---

# 11. Hoards are failed retrieval processes

Do not make every hoard an instantaneous archaeological sink.

A concealment event creates a temporary hidden stock:

```text
object/metal -> concealed_hoard
```

with:

```text
concealment location
owner/network identity
intended retrieval time
retrieval probability
conflict persistence
owner survival/return
landscape change
```

Most practical concealments can be retrieved and re-enter circulation.

An archaeological hoard is the subset for which retrieval fails:

```text
P_unrecovered = f(
    owner death/displacement,
    war duration,
    migration,
    secrecy/information loss,
    flooding/channel change,
    settlement abandonment,
    theft,
    random failure
)
```

Ritual/depositional hoards use a separate deliberate-terminal process.

### 11.1 Hoard geography

Concealment prefers locations balancing access and secrecy:

```text
settlement edge
route-adjacent but not route center
river terrace/dry ridge
landmark
field boundary
forest/wetland edge
house/workshop floor
```

The resulting unrecovered hoards form strange bands along social/environmental boundaries rather than a uniform point process.

---

# 12. Loss frontlines

The most important Step-4 spatial concept is a continuous **loss-front field** rather than a list of special nodes.

Define environmental/social coordinates:

```text
A(x,t) = accessibility/connectivity
H(x,t) = hydrological boundary intensity
C(x,t) = conflict/frontier pressure
S(x,t) = settlement/market intensity
B(x,t) = boat/transshipment exposure
Q(x,t) = channel/shoreline change rate
R(x,t) = ritual/wetland deposition propensity
```

A generic loss-front score can use both levels and gradients:

```text
F_loss(x,t) =
    wA * |grad A|
  + wH * H
  + wC * C
  + wS * transfer_activity
  + wB * B
  + wQ * |d palaeogeography / dt|
  + wR * R
```

This naturally creates ribbons/patches along:

- riverbanks, fords, ferries and old channels;
- lagoon and delta margins;
- shorelines and transshipment zones;
- passes and frontier corridors;
- settlement edges;
- conflict belts;
- changing river mouths;
- wetland ritual landscapes.

Those are the “weird frontlines” from which the archaeological distribution emerges.

---

# 13. Loss hazards by process

Use explicit competing hazards rather than one generic `loss_probability`.

For an active object/metal packet:

```text
h_accidental_drop
h_river_crossing_loss
h_boat_wreck
h_jettison
h_combat_loss
h_theft_transfer
h_hoard_conceal
h_ritual_deposition
h_grave_deposition
h_settlement_abandonment
h_workshop_debris
h_repair_failure
h_scrap_remelt
h_return/recovery
```

Some are absorbing; some change state.

### 13.1 Boat/river loss

Boat-associated metal can disappear through:

```text
capsize/wreck
storm grounding
harbour/transshipment drop
cargo handling
river crossing/ferry accident
jettison
eroded/abandoned vessel
combat/piracy
```

Whole-cargo losses create **correlated assemblages** rather than independent isolated objects.

### 13.2 War/combat loss

Warrior-carried objects have increased:

- damage;
- abandonment;
- corpse/grave context;
- loot transfer;
- river crossing loss;
- retreat-flight discard.

A combat event need not be a named battlefield to create a localized cluster.

---

# 14. Deltaic catastrophe/submergence as a generic mechanism

The Egyptian example should be treated carefully.

The famous submerged city is Thonis-Heracleion at the Canopic Nile mouth. Its dramatic submergence is much later than most of the Atolia Bronze Age horizon, so v2 must **not** invent a Bronze Age Heracleion catastrophe.

Instead define generic deltaic susceptibility:

```text
D_delta(x,t) = f(
    unconsolidated sediment,
    compaction/subsidence,
    channel migration,
    flood loading,
    seismic/liquefaction susceptibility,
    relative sea level,
    storm/surge exposure
)
```

The Canopic delta can receive a geographically appropriate susceptibility prior, but catastrophic events occur only according to the world chronology/process model.

Similar mechanisms can operate at other deltas/lagoonal coasts without being named sites.

---

# 15. Deposition is not the modern findspot

At terminal loss record:

```text
deposition_xy
deposition_date
deposition_environment
deposition_depth_initial
assemblage_id if correlated event
cause/process
```

Then evolve the deposit separately through the remaining centuries/millennia.

Post-depositional state:

```text
burial_depth
erosion/reworking
channel migration
sedimentation
submergence/emergence
corrosion environment
land-use disturbance
fragmentation
redeposition
```

Final modern coordinate can differ from deposition coordinate.

---

# 16. Palaeochannel and coastal findspot mechanics

### Live-channel loss

Metal lost in water may:

- settle locally;
- roll/transport downstream;
- enter bar/point-bar sediment;
- become buried during flood;
- be reworked several times.

### Channel abandonment

Once the river migrates/avulses, the object can become frozen into an old channel belt.

This creates the desired archaeological pattern:

```text
ancient mobility corridor
 -> high loss exposure
 -> later river abandonment/burial
 -> modern field/quarry/reclamation findspot
```

### Coast

A Bronze Age shoreline object may now be:

- inland due progradation;
- offshore due transgression/subsidence;
- buried beneath lagoon/alluvium;
- eroded away;
- redeposited downslope/alongshore.

The present shoreline must never be used as the ancient loss coordinate without palaeogeographic transformation.

---

# 17. Survival and discovery

Separate:

```text
loss -> burial/preservation -> modern exposure -> discovery -> recording
```

### Preservation

Depends on:

```text
waterlogging/redox
chloride/salinity
soil chemistry
sediment stability
depth
mechanical reworking
object alloy/geometry
```

### Modern exposure/discovery

Depends on a later field:

```text
agriculture/ploughing
construction/quarrying
river dredging
coastal erosion
land reclamation
diving/marine survey
metal detecting where relevant
formal excavation
urban burial depth
```

Thus deeply buried palaeochannel and submerged coastal deposits may have excellent survival but low discovery probability.

This is necessary to avoid equating `not found` with `never there`.

---

# 18. Smart correlated events

The v2 world should include events that act on many represented objects at once:

```text
shipwreck
river-boat wreck
settlement fire/abandonment
workshop destruction
failed hoard retrieval
battle/retreat episode
flood/avulsion
market/port collapse
migration pulse
```

Each event generates an `assemblage_id` and correlated deposition properties.

This is much more realistic and much cheaper than 50M independent Bernoulli losses.

---

# 19. Recycling/broker ecology inside transport

Broker/scrap state is spatial and mobile.

A broker stock has:

```text
node/region
metal mass vector
source/isotope inventories
class-of-origin mixture
guild exposure mixture
stock age
network_embedding
water access
turnover rate
```

Operations:

```text
BUY/ACQUIRE used object
SORT
STORE
MOVE stock
SPLIT batch
MERGE batches
SELL intact object
SEND TO REPAIR
REMELT
TRANSFER to workshop
LOSE/HOARD stock
```

High recycling therefore creates **network memory in the metal economy** without pretending atoms remember routes.

Once a metal enters a successful broker/river/port circuit, subsequent object lives are statistically more likely to remain highly connected until a remelt/ownership event moves it back into a local household ecology.

---

# 20. Computational strategy: let it run overnight without daily stepping

Do not simulate 50M physical objects × 365,000 days.

Use aggregate packet/event simulation.

Each packet represents many statistically exchangeable object episodes/metal mass at one state:

```text
(node/cell,
 carrier state,
 object class,
 time bucket,
 guild/process state,
 chemistry block,
 mobility moments,
 represented_count,
 represented_mass)
```

### 20.1 Compound movement events

Within a residence interval `Δt`, draw counts of active movement episodes:

```text
N_land  ~ Poisson(lambda_land * Δt)
N_water ~ Poisson(lambda_water(state) * Δt)
N_owner ~ Poisson(lambda_transfer * Δt)
```

For small `N`, resolve explicit sparse graph steps.
For large stable packets, use moment/tau-leap propagation across neighboring carrier states.

### 20.2 Adaptive time resolution

Use finer stepping when:

- conflict is high;
- shoreline/river geometry changes;
- water-mode transition occurs;
- broker/remelt event occurs;
- loss hazard becomes large.

Use coarse stepping during long stationary periods.

### 20.3 Split/merge control

Packets split only when their future hazard/mobility distributions differ materially.

Merge packets when they share:

```text
same cell/time/class/carrier/guild bucket
compatible chemistry covariance block
compatible lineage moments
```

with exact preservation of extensive mass/count ledgers and weighted moments.

This is how the model can represent 50M object episodes and a 1000-year world overnight without allocating 50M Python objects.

---

# 21. Direct-NetCDF Step-4 state

Exact/developer loss-event rows should include or derive:

```text
loss_cell_id
loss_xy / palaeo-environment id
loss_date
carrier_role
object_class
current_workshop/guild exposure
cause/hazard channel
assemblage_id
cumulative_metal_distance
current_object_distance
network_embedding
land_active_displacement_count
water_mode_count
ownership_transfer_count
broker_cycle_count
war_exposure
hoard/retrieval state
palaeochannel/coast context
metal chemistry/isotope sufficient state
```

Profile condensation retains covariance blocks for:

```text
(distance, water_mode_count, network_embedding, broker_depth)
(loss cause, carrier role, context)
(remelt, source entropy, guild transitions)
```

plus sparse context/assemblage distributions.

---

# 22. Replace v1 shortest-route dependence

The existing `artifact_mobility.py` uses a temporally weighted Dijkstra origin-to-destination path and chooses a deposition position along that route. That remains useful as a **reference/corridor potential**, not the v2 biography generator.

V2 uses shortest/generalized-cost paths only to construct attraction/permeability fields and to accelerate long-range transitions.

Actual biography:

```text
local correlated random walk
+ social ownership jumps
+ river/coastal mode changes
+ broker cycles
+ war/displacement perturbations
+ remelt resets of object identity
```

This is the conceptual break from v1.

---

# 23. Empirical anchors without special-node overfitting

Use real archaeological/geoarchaeological cases as calibration anchors for **mechanisms**, not mandatory story beats.

Examples:

- Bronze Age Fenland metal deposition supports strongly structured river/wetland deposition rather than uniform water loss.
- Northern Adriatic Bronze Age coastal/lagoon sites demonstrate that ancient coastal settings can now be submerged, buried or altered by reclamation and relative sea-level change.
- Thonis-Heracleion demonstrates how deltaic unconsolidated sediments, subsidence/liquefaction and changing coastline can later submerge major port landscapes; use as geomorphic analogy, not a Bronze Age catastrophe event.
- Submerged/palaeoshore archaeology around the Mediterranean demonstrates that modern coastlines are not adequate proxies for prehistoric coastlines.

Known sites can receive small data-backed environmental priors where appropriate, but no named place receives a magical deposition bonus merely because it is famous today.

---

# 24. Calibration targets before the giant build

A medium-size Step-4 ensemble should demonstrate all of the following:

1. Household tools mostly remain local during a single object life.
2. Warrior-associated weapons accumulate broader, repeated frontier movement.
3. High portable value raises long-distance ownership/boat transfer without simply increasing speed.
4. Water-mode probability rises with real network/water embedding and weakly with accumulated movement.
5. Water episodes have a longer displacement distribution than terrestrial active episodes.
6. Any suitable river/shore can act as an embarkation surface; named ports are concentrations, not gates.
7. Intact objects can remain local while their recycled metal reaches 500–1000+ km cumulative distance.
8. Theft/loot frequently transfers objects rather than immediately destroying them.
9. War increases mobility, repair, hoarding, loss and workshop displacement simultaneously.
10. Most practical hoards are retrieved; unrecovered hoards arise from failed retrieval/deposition processes.
11. River/coast loss events form bands along palaeochannels/shorelines rather than present-day node dots.
12. Shipwreck/abandonment events create correlated assemblages.
13. Palaeogeographic change can move the modern findspot environment away from the ancient deposition environment.
14. Deep/submerged deposits can survive well while remaining difficult to discover.
15. High-value objects have lower trivial-drop loss but higher exposure to gift/loot/boat/war pathways.
16. The 50M Atesis-crossing object-episode target can emerge without forcing 50M explicit agents.
17. Atesis crossing remains a true path-surface event, not source identity.
18. Mass/isotope conservation remains valid through movement, broker merge/split and remelt.
19. Runtime profile covariance reproduces joint water/distance/broker/remelt behavior.
20. No acquisition/career code uses hidden loss truth to select desirable artefacts.

---

# 25. What Step 5 receives

The final implementation/freeze pass can now assume:

```text
world-scale metal/object accounting
+ autonomous evolving guild skills
+ process-aware isotope/trace inventories
+ carrier-specific random walks
+ water-mode escalation
+ value/social transfer
+ war/theft/broker ecology
+ dynamic palaeogeography
+ explicit loss-front fields
+ post-depositional findspot transformation
```

Step 5 must choose the exact graph/palaeogeographic carrier resolution, direct-NetCDF schema, event/tau-leap implementation, chunk sizes, compression and benchmark thresholds; then validate on small/medium worlds before launching the one final large overnight v2 master build.
