# Atolia direct-NetCDF v2 preparation — Step 3/5

## Isotope, trace-element and metallurgical-memory physics

Status: preparation pass 3 on `atolia-metal-lineage-v1`.

This pass defines how geochemical evidence actually survives ore extraction, smelting, alloying, repeated recycling, workshop contamination, corrosion and laboratory measurement. It replaces the v1 idea of one source mean + independent noise with a physically mixed, covariance-aware system.

The core rule is:

> **Never propagate an isotope ratio as though it were a conserved scalar. Propagate the isotope-bearing element and its isotopic inventory; derive ratios only from that inventory.**

The second rule is:

> **Provenance evidence is not one coordinate. Pb isotopes, Sn isotopes, Cu isotopes, trace elements, inclusions and metallography remember different parts of the metal biography and can disagree for physically valid reasons.**

---

## 0. Scope and source basis

Step 3 is grounded in archaeometallurgical results that are directly relevant to the Atolia world:

- Southeastern Alpine copper ores have published Pb-isotope reference datasets covering Alto Adige/Südtirol, Trentino, Veneto and neighboring Alpine districts; these are explicitly used for prehistoric copper provenance work.
- Bronze Age copper studies routinely combine Pb isotopes with trace chemistry because neither alone gives a unique source solution.
- Late Bronze Age recycling/mixing studies show that Pb-rich components can dominate mixture isotope signatures and hide lower-Pb metal fractions (`ghost fractions`).
- Experimental cassiterite smelting shows measurable Sn-isotope fractionation, especially under incomplete reduction; Sn-isotope source assignment must therefore include process uncertainty.
- Cu isotopes can retain information about ore type/weathering but can also be modified or obscured by co-smelting, alloying and recycled-metal mixing; they are not treated as a clean mine barcode.
- Tin-oxide and other oxidized inclusions can survive multiple remelts and therefore provide technological-history evidence that is neither pure provenance nor pure final-manufacture evidence.

Key literature targets for implementation/calibration include:

- Artioli, Angelini, Nimis & Villa (2016), *A lead-isotope database of copper ores from the Southeastern Alps*, Journal of Archaeological Science 75, 27–39, DOI 10.1016/j.jas.2016.09.005.
- Bruyère et al. (2024), *Trade, recycling and mixing in local metal management strategies of the later Bronze Age south Carpathian Basin*, Journal of Archaeological Science 164, 105957, DOI 10.1016/j.jas.2024.105957.
- Berger et al. (2018), *Tin isotope fractionation during experimental cassiterite smelting*, Journal of Archaeological Science 92, 73–86, DOI 10.1016/j.jas.2018.02.006.
- Mason et al. (2020), *Provenance of tin in the Late Bronze Age Balkans based on probabilistic and spatial analysis of Sn isotopes*, Journal of Archaeological Science 122, 105181.
- Vernet, Ghiara & Piccardo (2019), *Are tin oxides inclusions in early archaeological bronzes a marker of metal recycling?*, Journal of Archaeological Science: Reports 24, 655–662.
- Pernicka et al./review literature on European Bronze Age metal provenance and circulation, including the need to interpret LI matches as consistency rather than unique proof.

Step 3 does **not** hard-code one paper's exact numerical distributions as universal truth. The final source covariance database is an implementation dataset assembled in Step 5.

---

# 1. Replace source means with geological source distributions

The v1 source object is approximately:

```text
source_id
trace_mean[element]
Pb isotope mean[ratio]
```

V2 source field `s` becomes:

```text
SourceGeochemistry_s = (
    source_id,
    ore_district,
    ore_body/subfield,
    mineralization_family,
    chronology,
    mineralogy,
    element_mean_vector,
    element_covariance,
    Pb_isotope_inventory_distribution,
    Sn_isotope_distribution_if_relevant,
    Cu_isotope_distribution_if_relevant,
    inclusion/mineral_phase_distribution,
    capacity/time profile,
    data_quality
)
```

### 1.1 Why covariance matters

A fahlore-derived copper source can simultaneously carry elevated As/Sb/Ag and characteristic Ni/Co/Bi patterns. Drawing every element independently destroys the ore-mineral association that makes chemistry diagnostically useful.

Represent source chemistry in transformed space, e.g. log concentration for strictly positive trace elements:

```text
z_s ~ MVN(mu_s, Sigma_s)
concentration_e = exp(z_e)
```

or use empirical resampling/KDE where source datasets are sufficiently large.

Do not force multivariate normality if source data are clearly multimodal. One ore district may contain several mineralization subfields.

### 1.2 Hierarchical geological model

Preferred hierarchy:

```text
ore province
  -> mining district
    -> ore body / mineralization subfield
      -> production batch
```

A sampled smelting batch inherits correlated variation from each level.

This is important because a positive Pb-isotope match to a broad Alpine field may still be non-unique, while trace/mineral chemistry can narrow or contradict the candidate set.

---

# 2. Elemental mass is the conserved basis

For every active metal packet, store element masses rather than only wt%:

```text
M = {
    Cu_kg,
    Sn_kg,
    As_kg,
    Pb_kg,
    Ag_kg,
    Au_kg,
    Fe_kg,
    Zn_kg,
    ...
}
```

Trace elements may be represented as mass fractions or sparse masses when numerically safe.

For mixture of packets `i`:

```text
M_e,mix = sum_i M_e,i
M_total = sum_e M_e,mix
c_e,mix = M_e,mix / M_total
```

This is exact mass accounting before process losses/additions.

Alloy wt% is a derived view.

---

# 3. Isotope inventories, not averaged ratios

## 3.1 General rule

For an isotope-bearing element `E` with isotopes `a,b,...`, propagate isotope amount/mass:

```text
N_E,a
N_E,b
...
```

Then:

```text
R_a/b = N_E,a / N_E,b
```

Mixing is simply:

```text
N_mix,a = sum_i N_i,a
N_mix,b = sum_i N_i,b
R_mix = N_mix,a / N_mix,b
```

This automatically weights the isotope signal by the amount of the element carrying it.

It prevents the wrong operation:

```text
R_mix = sum_i metal_mass_fraction_i * R_i    # WRONG in general
```

when different components have different Pb/Sn/Cu concentrations.

---

# 4. Lead isotope system

## 4.1 Hidden state

For Pb-bearing metal, track at least:

```text
Pb204_amount
Pb206_amount
Pb207_amount
Pb208_amount
Pb_total_mass
Pb_origin_component tags/moments
```

Ratios reported to the laboratory layer:

```text
206Pb/204Pb
207Pb/204Pb
208Pb/204Pb
```

Optionally also derive 206Pb/207Pb etc. without storing extra state.

## 4.2 What Pb isotope evidence remembers

Absent Pb addition/contamination, lead isotope ratios are generally treated as robust through normal metallurgical processing compared with elemental concentrations.

But the measured Pb isotope signature belongs to **the lead atoms in the object**, not automatically to the copper mass.

A copper component with 50 ppm Pb mixed with a small lead-rich component can become nearly invisible in Pb-isotope space.

Therefore v2 explicitly distinguishes:

```text
copper_source_ancestry
Pb_isotope_dominant_source
```

They may differ.

## 4.3 Ghost fractions

Suppose two metal components have masses `m1,m2`, Pb concentrations `cPb1,cPb2`, and isotope inventories corresponding to ratios `R1,R2`.

The effective weighting is approximately proportional to:

```text
w_i ~ m_i * cPb_i
```

not `m_i` alone.

A numerically small metal fraction with high Pb concentration can dominate `R_mix`.

The model must preserve this because real Late Bronze Age studies have observed such masking in recycled/mixed objects.

## 4.4 Natural Pb versus intentionally/accidentally added Pb

The hidden genealogy labels Pb contributions by process role:

```text
ore_residual_Pb
lead_metal_addition
Pb_carried_by_tin
Pb_carried_by_scrap
crucible/flux/fuel/process_contamination
repair_addition_Pb
```

These are developer-truth causal tags, not player-visible labels.

When Pb is deliberately added, LIA may primarily provenance the added lead rather than the copper.

No fixed universal Pb threshold is used to declare provenance valid. Recent work shows that useful thresholds depend on empirical populations and may be far lower than old 1–2 wt% conventions.

## 4.5 Pb likelihood, not nearest-source lookup

At analysis time compute candidate likelihood:

```text
P(source set | Pb isotope vector, Pb concentration, chronology, chemistry)
```

A match means `consistent with`, not `proven uniquely from`.

Ore-source overlap is real and remains in the game.

---

# 5. Tin: mass, source and isotope history

Tin requires a separate provenance lineage because Sn can be introduced at different stages and from a source unrelated to Cu.

## 5.1 Sn source components

A bronze lineage can acquire tin by:

```text
cassiterite co-smelting with copper ore
cementation / reduction into copper
direct metallic tin addition
addition of pre-existing bronze scrap
high-Sn intermediate/master alloy
```

Each creates different archaeological/process signatures.

## 5.2 Tin isotope hidden state

Preferred reduced isotope representation:

- store sufficient Sn isotope inventory to derive the chosen reported delta system, likely anchored on `120Sn` and `124Sn` initially;
- if storage permits, retain full stable-Sn isotope basis in source/master tables while runtime retains sufficient two-isotope coordinates + covariance.

For δ notation:

```text
delta124Sn = ((R_sample / R_standard) - 1) * 1000 permil
```

Mix in ratio/inventory space, **not by averaging delta values by object mass**.

## 5.3 Smelting fractionation

Experimental cassiterite smelting demonstrates that Sn isotope fractionation is not zero.

Berger et al. observed approximately:

- complete/good reduction: metal offset around 0.09–0.18 permil for Δ124Sn/120Sn relative to cassiterite;
- incomplete reduction can produce much larger offsets, reported up to about 0.88 permil;
- vapour and slags can be considerably more fractionated.

Therefore:

```text
Sn_isotope_after_smelting
= process_fractionate(Sn_isotope_ore,
                      recovery_fraction,
                      redox,
                      temperature,
                      furnace openness,
                      slag/fume loss)
```

The exact process model is stochastic and calibrated, not a fixed universal offset.

## 5.4 Repeated remelting

Bronze remelting/casting may cause smaller Sn-isotope shifts than initial cassiterite smelting, but the literature does not justify assuming zero under all prehistoric redox conditions.

V2 therefore propagates:

```text
Sn_isotope_process_uncertainty
Sn_remelt_fractionation_count
```

and attenuates provenance certainty with repeated poorly constrained remelts.

## 5.5 Tin oxide inclusions

SnO2/cassiterite-like inclusions and other oxidized inclusions can survive multiple remelts in experiments.

This creates a valuable independent evidence channel:

```text
inclusion_history != bulk_Sn_isotope_history
```

An inclusion can preserve evidence of alloying/recycling practice even after bulk metal chemistry has become mixed.

V2 selected-object truth should allow sparse inclusion populations with:

```text
phase
size
composition
oxidation state
survival probability per remelt
likely episode of introduction
```

---

# 6. Copper isotopes

Cu isotope state is useful but deliberately secondary to Pb + trace chemistry for direct provenance.

## 6.1 Hidden coordinate

Track Cu isotope inventory sufficient for:

```text
delta65Cu
```

using `63Cu` and `65Cu` inventories.

## 6.2 Interpretation

Cu isotopes can distinguish broad ore/process histories because near-surface oxidized ores and primary sulfide ores may differ isotopically.

However:

- smelting can fractionate Cu isotopes;
- co-smelting different ore types changes the signature;
- arsenical-copper/alloy choices alter which Cu reservoirs enter the object;
- recycled metal mixes previous signatures.

Therefore δ65Cu is modeled as:

```text
geology + beneficiation/smelting + mixing/recycling
```

not simply `mine_id`.

In the archaeological inference layer it is strongest as an additional discriminator of ore/process family.

---

# 7. Trace-element inheritance

Current v1 trace keys include Sb, Ag, Ni, Co and Bi. V2 expands the basis while keeping each element's process behavior distinct.

Recommended chemistry basis:

```text
major/alloy:
Cu Sn As Pb Ag Au Fe Zn

provenance/process traces:
Sb Ni Co Bi S Se Te Mn possibly Cd where dataset supports it
```

Do not include an element merely because an instrument can detect it. Each tracked element needs one of:

- mass-budget relevance;
- source-discrimination value;
- process-history value;
- corrosion/measurement relevance.

## 7.1 Process transfer law

For process `p` and element `e`:

```text
M_e,out = retention_e,p(state) * M_e,in + addition_e,p
```

where retention may depend on:

```text
redox
slag chemistry
temperature
dwell time
furnace/crucible environment
starting alloy
```

Do **not** use one generic exponential `trace decay with recycle count`.

## 7.2 Important caution: arsenic

V2 must not encode the folk rule that As simply decreases linearly with every remelt.

Thermodynamic/experimental discussion of Cu-As systems shows arsenic behavior is more complicated; under some remelting conditions As may remain stable or even become relatively enriched as Cu oxidizes preferentially.

Therefore As loss/enrichment is process-state dependent.

## 7.3 Tin and other traces under oxidizing conditions

Tin, Co, Ni and other elements can partition differently into metal, slag and oxide phases depending on oxygen potential and process conditions.

The exact Bronze Age transfer coefficients are uncertain; Step 5 should use broad calibrated process distributions rather than modern industrial constants copied directly.

---

# 8. Gold and silver

The Step-1 Au and Ag primary-mass ledgers remain real metal streams, but their isotope systems are handled more selectively than Cu/Pb/Sn.

## 8.1 Silver

For silver-rich metal streams:

- Pb isotopes can provenance associated lead/silver ores when geological baselines support it;
- Ag stable isotopes can add information but natural/archaeological variation is narrow and analytical precision requirements are high;
- combined Ag + Pb isotope models are more useful than Ag isotope alone.

V2 reserves:

```text
Ag107_amount
Ag109_amount
```

only for explicit precious-metal packets or selected-object materialization, not necessarily every bronze circulation packet.

## 8.2 Gold

Gold provenance is particularly difficult if represented only by bulk Au composition.

Potential evidence channels include:

```text
Ag/Cu trace composition
PGE inclusion chemistry
Os isotope composition of refractory PGE inclusions
Pb isotope of associated ore/impurity where applicable
```

PGE inclusions in ancient placer gold can preserve Os isotope signals because they are refractory, but this is **not universal to all gold sources or all gold objects**.

V2 therefore does not force one `gold_isotope_source` scalar. It stores precious-metal provenance through optional inclusion/source modules when geologically justified.

---

# 9. Source ancestry versus measured chemistry

Every selected artefact has two separate hidden objects:

```text
metal_ancestry_truth
material_state_truth
```

Example:

```text
metal_ancestry_truth:
  52% Cu mass originally southeastern Alpine source A
  23% Cu mass source B
  25% recycled regional stock
  Sn primarily source T1
  Pb signal dominated by later Pb-rich T1/addition

material_state_truth:
  current bulk alloy wt%
  current isotope inventories
  current trace vector
  surviving inclusions
```

The measured laboratory values are generated only from `material_state_truth`.

The player must infer ancestry indirectly.

---

# 10. Mixing depth and information loss

Repeated recycling does not erase all information at the same rate.

Define evidence-memory channels:

```text
M_source_mass       # exact ancestry remains in hidden truth
M_Pb_discriminative
M_Sn_discriminative
M_Cu_discriminative
M_trace_cluster
M_inclusion
M_microstructure
M_morphology
```

These are not all monotone functions of recycle count.

Examples:

- exact hidden source mass ancestry never disappears mathematically;
- Pb source discrimination may collapse abruptly after a Pb-rich addition;
- Sn isotope discrimination may drift due smelting/remelt fractionation;
- trace clusters may blur through mixture but some element ratios remain informative;
- old microstructure is mostly reset by full remelt;
- refractory inclusions may survive several remelts;
- final morphology resets at remelt.

This gives the game physically meaningful partial amnesia.

---

# 11. Isotope/trace covariance in NetCDF

V1 runtime stores marginal means and variances independently. V2 cannot do that for isotope/chemistry state.

## 11.1 Exact master

The developer master may store exact loss-state sufficient values for:

```text
Pb isotope inventories or ratios + Pb concentration
Cu isotope coordinate/inventory
Sn isotope coordinate/inventory
major element masses
selected trace coordinates
process counters
```

No repeated source dictionaries.

## 11.2 Profile condensation

For each `(production cohort, loss node, time bucket)` profile retain covariance blocks for physically coupled variables.

Recommended blocks:

### Block A — recycling/provenance

```text
remelt_count
source_entropy
cumulative_metal_distance
workshop_transition_count
```

### Block B — lead system

```text
log(Pb concentration)
206Pb/204Pb
207Pb/204Pb
208Pb/204Pb
```

### Block C — tin system

```text
Sn wt fraction
delta124Sn
Sn process-fractionation uncertainty
```

### Block D — trace chemistry

A low-rank PCA/factor representation or sparse covariance over selected log-trace elements rather than an enormous dense matrix.

### Block E — guild/process memory

```text
technical_memory
remelt_count
repair_count
selected process-exposure moments
```

The runtime sampler draws these blocks jointly, not independently.

---

# 12. Source-mixture representation

Do not store only normalized source labels after multiple recycling.

For hidden selected-object truth preserve mass fractions by source ancestry:

```text
source_mass_fraction[source_id]
```

For the huge runtime, use compressed representation:

```text
dominant_source_id
dominant_source_fraction
source_entropy
source_component_count expectation
source_family exposure CSR
```

plus isotope/trace covariance.

When a selected object is materialized, reconstruct a plausible explicit source mixture conditional on all of those together.

The reconstruction is rejected if its implied isotope/trace state is inconsistent with the sampled profile block beyond tolerance.

---

# 13. Process contamination

Workshops can alter measured geochemistry without adding a major intended alloy component.

Potential contributors:

```text
crucible ceramic/refractory
slag carryover
charcoal/fuel ash
flux
old melt adhering to crucible
repair metal
metal tools/contact
Pb/Sn-bearing additions
```

V2 represents contamination as explicit small-mass additions with their own chemistry where important, not as arbitrary Gaussian noise.

Analytical noise is added later by the instrument model.

---

# 14. Corrosion and sampling

The buried object's bulk composition is not identical to every measured surface spot.

Keep three layers:

```text
bulk_metal_truth
corrosion/alteration_truth
sampled_material_truth
```

Surface XRF can be biased by corrosion/encrustation and selective elemental enrichment/depletion.

A cleaned core/microdrill measurement samples much closer to bulk metal.

Pb isotope contamination from burial/environment must be separately possible for compromised surface samples, while a clean core has much lower contamination probability.

---

# 15. Instrument model v2

The current `instrument_measurement_model.py` adds independent Gaussian uncertainty to the three Pb ratios. V2 should upgrade this substantially.

## 15.1 Pb isotope MC-ICP-MS style measurement

Return:

```text
ratio vector
full analytical covariance matrix
Pb concentration
preparation/sample location
quality flags
```

Measurement covariance matters because isotope ratios sharing a denominator are correlated.

## 15.2 Sn isotope tool

Add explicit tool:

```text
sn_isotopes
```

with:

```text
delta124Sn or selected standardised delta vector
analytical uncertainty
process-fractionation uncertainty kept separate from analytical uncertainty
```

The latter is inference uncertainty, not instrument noise.

## 15.3 Cu isotope tool

Add:

```text
cu_isotopes -> delta65Cu
```

with interpretation explicitly noting source/process ambiguity.

## 15.4 High-resolution chemistry

Keep XRF as useful screening, but introduce a destructive/high-quality chemistry tool conceptually equivalent to ICP-MS/ICP-OES for trace-element work:

```text
bulk_chemistry
```

This can reveal low-ppm trace structures that XRF cannot robustly resolve.

## 15.5 Inclusion analysis

Add SEM-EDS/metallographic inclusion observations for selected samples:

```text
phase composition
size class
location
confidence
```

This is crucial for surviving tin oxides, sulfides, Pb-rich inclusions, slags and remelt evidence.

---

# 16. Bayesian provenance logic

The game should never return:

```text
Pb isotope = source X
```

Instead compare hypotheses.

For candidate source mixture/model `H`:

```text
P(H | data)
propto
P(Pb isotopes | H, process)
* P(trace chemistry | H, process)
* P(Sn isotope | H, process)
* P(Cu isotope | H, process)
* P(inclusions | H, process)
* P(chronology/context | H)
* P(H)
```

The player may have several explanations:

```text
single Alpine Cu source + external tin
mixed Alpine/Carpathian recycled Cu
local Cu + Pb-rich imported tin/addition
foreign finished object
local recasting of foreign metal
```

The likelihood can favor different explanations without needing a unique mine assignment.

---

# 17. Deep provenance paradoxes v2 should intentionally generate

The best model should naturally produce difficult cases such as:

### Case A — Pb ghost fraction

```text
70% low-Pb Alpine Cu
30% high-Pb imported/recycled component
```

Measured Pb isotope appears almost entirely like the 30% component.

Trace chemistry still hints at the Alpine majority.

### Case B — foreign tin, local copper

Pb carried by tin dominates the LI signature while Cu trace chemistry is local.

### Case C — multiple recycled Alpine sources

Pb isotope remains within a broad Alpine field, but no single mine fits trace covariance.

### Case D — Sn isotope shifted by poor smelt

Tin source is correct geologically, but incomplete reduction shifts δ124Sn enough to make naive nearest-source matching fail.

### Case E — remelted foreign object

Morphology and final guild are local; metal isotopes/trace ancestry are foreign.

### Case F — old inclusion survives

Bulk composition looks homogenized after several melts, but a refractory inclusion retains evidence of an earlier alloying route.

### Case G — convergent guild, different ore

Two workshops independently make similar high-quality edges using completely different metal sources.

These are features, not bugs.

---

# 18. Southeastern Alpine / Atesis model implications

The v2 Atolia world has an unusually strong opportunity because southeastern Alpine Pb-isotope baselines are real and comparatively well studied.

The source model should distinguish at minimum:

```text
Alto Adige / Südtirol subfields
Trentino subfields
Veneto / southeastern Alpine subfields
northern Austrian Alpine systems where relevant
fahlore-dominant versus chalcopyrite-dominant systems
external comparison fields: Balkans, Tuscany, Cyprus/Aegean, Iberia, etc.
```

But the source model must use actual sampled distributions rather than these geographic labels as isotope values.

The literature supports the importance of southeastern Alpine copper in northern Italy and the Po Valley, and documents Trentino-derived copper reaching into the western/central Balkans by the early Middle Bronze Age. This makes the broad connected world scientifically defensible without forcing every long-distance metal biography to be Alpine.

---

# 19. Precision policy

Master truth uses more precision than player measurement.

Recommended:

```text
mass ledgers: float64
Pb isotope inventories / ratios: float64
Sn/Cu isotope state: float64
trace-factor latent coordinates: float32 or float64 after error test
runtime profile means/covariances: float32 acceptable only after round-trip validation
```

Never quantize isotope fields merely to save a few MB before measuring the effect on source likelihoods.

---

# 20. Validation gates for isotope/trace physics

Before the giant v2 build:

1. Mixing two packets conserves every tracked element mass.
2. Isotope inventory is conserved under pure mixing/remelt when no process fractionation/addition is enabled.
3. Derived Pb ratios reproduce analytical concentration-weighted mixing exactly.
4. A Pb-rich minor component can dominate the Pb isotope ratio without dominating Cu mass.
5. Sn smelting fractionation responds to modeled recovery/redox state and can exceed simple analytical error.
6. Repair addition changes chemistry only by its actual added mass.
7. Full remelt resets microstructure but not source/isotope inventory.
8. Source covariance survives production sampling; trace elements are not independently randomized.
9. Source-mixture reconstruction from a runtime profile reproduces profile chemistry/isotope covariance statistically.
10. Surface measurement bias is distinct from bulk geochemical truth.
11. Analytical uncertainty and process/provenance uncertainty are stored separately.
12. Repeated recycling lowers provenance identifiability on average but does not force monotonic loss in every evidence channel.
13. Pb-isotope matching can exclude sources without requiring unique positive assignment.
14. External Pb/Sn additions can correctly break the equivalence `Pb provenance == Cu provenance`.
15. Same latent world seed reproduces isotope/chemistry truth exactly.

---

# 21. What Step 4 receives

Step 4 — transport/broker/recycling ecology — can now treat every circulation event as moving a **physically characterized metal packet**, not a generic bronze label.

It may:

- combine packets at brokers/workshops;
- add tin/lead/repair metal;
- remelt and change object class;
- alter trace elements according to process state;
- fractionate Sn/Cu isotopes where appropriate;
- preserve Pb isotope inventories unless Pb is added/lost/contaminated;
- accumulate metal distance independently of current-object random walk;
- carry guild histories independently of geological source histories.

Step 4 must never alter isotope ratios directly as a storytelling shortcut. It acts on element/isotope inventories through actual movement, mixing and metallurgy.
