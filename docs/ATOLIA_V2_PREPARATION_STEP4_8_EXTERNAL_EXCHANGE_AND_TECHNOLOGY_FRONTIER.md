# Atolia direct-NetCDF v2 preparation — Step 4.8/5

## Sparse external exchange, exceptional objects, and a moving metallurgical technology frontier

Step 4.8 opens the Atolia world without turning the game into a catalogue of exotic imports. The Atesis/Padanic/Alpine/Adriatic circulation world remains the statistical centre. External networks inject sparse materials, finished objects, craft observations and people whose effects may occasionally persist through recycling or guild learning.

## 1. Principle

```text
local/regional circulation = mass background
interregional Mediterranean/European exchange = important minority
very long-distance exchange = thin tail
exceptional foreign finished object = rarer tail
foreign technique becoming locally reproduced = separate event
```

Distance must not automatically imply importance, prestige, superior quality, or technological transfer.

## 2. External exchange zones

Use broad evidence-bearing gateway systems rather than fantasy direct routes:

```text
Egypt / Nile / Red Sea gateways
Levant / Cyprus / Syrian coast
Anatolia / Aegean
Mesopotamia / Babylonian exchange sphere
Caucasus / Iranian plateau / Central Asian chains
Arabia / Red Sea / Horn of Africa
Northeast Africa / Ethiopia-Eritrea gateways
Central Mediterranean / Sicily / Sardinia
Western Mediterranean / Iberia / Maghreb-Morocco
Atlantic-facing exchange chains
Central Europe
Baltic / amber networks
```

India is represented only through multi-stage eastern exchange chains where chronologically/evidentially admissible; do not create a routine `India -> Atolia` edge. Ethiopia/Horn, Morocco/Maghreb and Babylon are likewise network regions, not mandatory direct trading partners.

## 3. Exchange events carry commodities and information separately

```text
external_exchange_event:
    origin_region
    gateway_sequence
    transport_modes
    commodity_class
    mass
    object_count
    departure/arrival uncertainty
    intermediary_count
    loss_probability
    provenance_information_retained
```

Possible cargo includes copper, tin, gold, silver, lead, amber, glass/faience, ivory, stone, pigments, finished metalwork, scrap and non-metal luxury material. The v2 metal lineage only materializes what affects metal biography or archaeological observation.

## 4. Finished-object imports

A rare external object keeps its foreign manufacturing biography after entering the local circulation field.

Examples may include eastern Mediterranean weapon forms such as a khopesh/sickle-sword, foreign daggers, vessels, fittings, ornaments, ingot fragments or unusual alloy objects.

A khopesh is **possible, not guaranteed**. It should require a low-probability finished-object exchange path and chronological compatibility. Once present it can be used, repaired, copied, deposited, broken or recycled exactly like local metal.

## 5. Copies are not imports

Keep three states distinct:

```text
foreign_object
local_copy_of_foreign_form
hybrid_local_object
```

A locally made khopesh-like/sickle-sword form therefore does not magically inherit Egyptian ore, chemistry or guild history.

## 6. External metal entering recycling

External provenance can disappear morphologically while surviving chemically/isotopically:

```text
foreign ingot/object -> broker/smith -> remelt -> mixed batch -> local object
```

This is a major reason to retain sparse lineage pointers and mixture fractions.

## 7. Exchange should not dominate the player career

Do not enforce an exotic-object quota per career. Sample from the world.

For release calibration, track rather than hard-code:

```text
foreign_finished_object_fraction
external_metal_mass_fraction
very_long_distance_lineage_fraction
external_technology_observation_fraction
successful_external_skill_adoption_fraction
```

The expected player experience should be that most finds are interpretable within the regional world, while an occasional object or hidden material component dramatically expands the inference problem.

## 8. Technology transfer is not object transfer

A travelling object does not automatically teach its manufacture.

Technology may propagate through:

```text
mobile craftsperson
apprenticeship
workshop relocation
captured/enslaved specialist
intermarriage/household transfer
repeated observation of imported objects
repair of foreign objects
shared workshop episode
failed imitation
successful reverse engineering
```

Represent a `skill_observation` separately from `skill_acquisition`.

## 9. Ahmose-era benchmark

Early New Kingdom Egyptian copper-alloy/bronze weapons demonstrate that by roughly the mid-2nd millennium BCE sophisticated weapon production, composite construction, finishing and decorative metalwork already existed. Contemporary and earlier Bronze Age metallography elsewhere also demonstrates deliberate cycles of deformation and annealing; therefore **cold-work + anneal is a baseline technology, not a late-game Atolian super-skill**.

The simulation must not imply that 1200–1000 BCE smiths are 'unlocking annealing' for the first time.

Instead, the guild technology state tracks control quality:

```text
anneal_known
anneal_temperature_control
anneal_time_control
anneal_cycle_count_control
work_reduction_control
final_cold_work_control
section_specific_treatment
recrystallization_targeting
grain_size_control
hardness_gradient_control
crack_avoidance_skill
alloy_specific_process_control
```

Thus a guild can know annealing yet still make a poor blade because timing, work reduction, alloy or thermal control is wrong.

## 10. Five centuries of development do not mean a linear tech tree

The 1550 -> 1050 BCE horizon should produce branching, loss, rediscovery and specialization rather than `bronze level +500 years`.

```text
skill(t+1) = transmission
           + practice learning
           + local experimentation
           + external observation
           - master death
           - workshop collapse
           - resource mismatch
           - low production volume
           - migration
```

High skill survives only where enough relevant production continues.

## 11. Guild skill vector

For each workshop/guild lineage maintain bounded competencies such as:

```text
ore_selection
beneficiation
roasting
smelting_redox_control
slag_control
refining
alloy_dosing
arsenic_handling
tin_control
lead_control
melt_temperature_control
mould_design
lost_wax
sheet_raising
wire_work
joining/riveting
casting_feeding
porosity_control
hot_work
cold_work
anneal_control
work_anneal_sequence
edge_hardening_by_work
section_gradient_control
straightening
surface_finishing
polishing
repair
patching
recasting
scrap_sorting
colour_control
composite_object_assembly
quality_assessment
```

These are competencies, not RPG magic abilities. The existing 12 guild identities should map to weighted subsets and specializations of this shared metallurgical state rather than each guild owning physically exclusive laws.

## 12. Development frontier

Define the frontier as best demonstrated practice currently present anywhere in the simulated connected world:

```text
F_k(t) = max_workshop quality(skill_k,t)
```

But local guild g only possesses:

```text
S_gk(t) <= F_k(t)
```

Knowledge diffusion depends on contact and reproduction success. This allows Egypt, Cyprus, the Aegean, Alps, Italy, Balkans and other regions to lead different skills at different times.

## 13. Quality is measurable in objects

Skill must alter physical outputs:

```text
porosity
inclusion population
segregation/coring
recrystallized fraction
grain size/deformation proxy
residual strain
crack probability
edge hardness proxy
section thickness variance
alloy composition variance
surface finish
repair durability
```

The later Dr Corrosion measurement game can infer these imperfectly from metallography, hardness, XRF/EDS, CT/radiography, isotope and corrosion observations.

## 14. Annealing specifically

The useful progression is not:

```text
no annealing -> annealing
```

but approximately:

```text
accidental/intermittent thermal softening
-> recognized work/anneal cycling
-> reliable recrystallization
-> alloy-aware annealing
-> geometry-aware sequence
-> controlled final work hardening
-> repeatable section-specific mechanical properties
```

Different workshops can occupy different positions simultaneously, and advanced practice can vanish when its practitioner lineage dies.

## 15. Guild competition and borrowing

When two guild/workshop lineages interact:

```text
P(skill transfer) = f(
    contact duration,
    shared work,
    apprentice mobility,
    skill observability,
    recipient prerequisite skill,
    economic incentive,
    secrecy,
    social affinity,
    production repetition
)
```

Transferred skills begin noisy. Repetition can stabilize them; lack of production makes them decay.

## 16. Exceptional objects as technology probes

A foreign high-quality weapon is interesting because it can create several futures:

```text
use and deposit unchanged
repair locally
copy morphology badly
copy morphology successfully
learn one process detail
learn several process details
recycle it and erase morphology
```

This creates rare objects that are narratively exciting without making external trade the explanation for the whole local technology stack.

## 17. NetCDF sparse additions

Suggested groups:

```text
/external/regions
/external/gateways
/external/exchange_events
/external/event_membership
/external/skill_observations
/external/skill_transfers
/technology/workshop_skill_state
/technology/frontier
```

Object and metal truth remain pointers to existing lineage tables.

## 18. Temporal storage

Do not store every skill every day. Store change points:

```text
skill_event_ptr
skill_event_time
skill_id
old_level
new_level
cause
source_workshop_or_region
confidence
```

Reconstruct workshop state at time t by applying events to its initial vector. This is compatible with the ECMWF-style compact runtime approach.

## 19. External provenance uncertainty

Long-distance exchange increases uncertainty. Preserve distributions over gateway/origin candidates rather than assigning false precision.

```text
origin_candidate_ptr
origin_candidate_region
origin_probability
```

Isotope/chemistry evidence can later update these probabilities without rewriting hidden physical truth.

## 20. Calibration / anti-exoticism tests

Run worlds with:

```text
external exchange off
commodity-only exchange
commodity + finished-object exchange
full exchange + skill transfer
```

Check whether core Atesis/Alpine metallurgical evolution remains viable in all but deliberately resource-starved scenarios.

If turning external exchange off destroys every local guild, the external model is too dominant.

## 21. Historical grounding targets for Step 5

Use external evidence to constrain *possibility and magnitude*, not script history. Particularly useful anchors include:

- eastern Mediterranean copper/tin and oxhide-ingot networks;
- Egypt-Levant-Cyprus-Aegean interaction;
- Alpine/central-European metal exchange;
- Baltic amber moving south through central Europe toward the Po/Adriatic and Aegean;
- central/western Mediterranean exchange through Sardinia/Sicily/Iberia;
- changing eastern versus European tin contributions through the second millennium BCE;
- sparse luxury-material chains reaching beyond the Mediterranean.

India/Horn/Maghreb/Mesopotamia should enter through these chain mechanisms unless specific evidence warrants a stronger direct link.

## 22. Release invariants

1. Regional circulation remains dominant by object count and metal mass unless evidence/calibration explicitly says otherwise.
2. Very-long-distance objects are a tail, not a quota.
3. External object, external metal, foreign style and transferred technique are separate variables.
4. Imported morphology does not imply imported metal.
5. Recycled imported metal does not imply imported morphology.
6. Annealing is already baseline Bronze Age craft knowledge; later development concerns control, sequencing and specialization.
7. Technology can improve, branch, stagnate, migrate and disappear.
8. Guild skill only survives through transmission plus sufficiently repeated practice.
9. The best connected-world technique is not automatically known locally.
10. Exceptional objects can influence local learning but do not automatically teach their production.
11. Long-distance provenance retains uncertainty.
12. Named exotic regions cannot be inserted simply to make player finds exciting.
13. No external-trade mechanism may erase ore, recycling, guild, isotope or metallurgical lineage truth.

## 23. Result

Step 4.8 gives v2 an open boundary without surrendering the local model:

```text
external world
     |
 commodities / people / rare objects / observations
     v
regional Atolia circulation <-> guild learning and forgetting
     |
     v
50-million-object metal biography world
     |
     v
rare extraordinary careers amid a dominant regional population
```

A player can therefore eventually encounter something as startling as an Egyptian-style sickle sword, Baltic amber-associated assemblage, eastern tin component or remote luxury-metal lineage. The interesting scientific question is then not 'look, an exotic!', but which parts of its **form, metal, manufacture, repair history and technological influence actually travelled together**.
