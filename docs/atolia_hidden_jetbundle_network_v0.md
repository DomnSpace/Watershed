# Atolia hidden jetbundle network v0

## Player-facing rule

The scenario-level copper throughput target is NEVER exposed to the player. The player sees only archaeological observables: objects, hoards, contexts, workshop clues, analytical results, map distributions and posterior hypotheses.

The hidden generator may use a fixed or soft aggregate corridor-throughput constraint internally, but UI and specimen metadata must not reveal the target value or imply that it is known archaeology.

---

## 1. Generative state

For time slice t, hidden state is:

X_t = {P_t, S_t, F_t, J_t, B_t, W_t, G_t, O_t, H_t, D_t}

where:
- P_t population field
- S_t settlement/hub graph
- F_t ore/source fields and primary production
- J_t latent transport jetbundles
- B_t metal batches and remelt mixtures
- W_t workshops
- G_t technical / symbolic lineages
- O_t manufactured object biographies
- H_t hoard/deposition events
- D_t preservation/discovery state

Use 25-year slices for 1800–1000 BC by default (32 slices). Finer annual variation is generated inside each slice only when needed.

---

## 2. Jetbundle as the central latent object

A jetbundle J_k is not a drawn route. It is a coherent historical flow component:

J_k = (q_k(t), s_k, pi_k, h_k, g_k, omega_k, phi_k, delta_k, r_k)

with:
- q_k(t): time-dependent copper-equivalent mass flux
- s_k: source-mixture vector over ore/source fields
- pi_k: probability distribution over river / coast / road / pass paths
- h_k: hub-transfer vector
- g_k: workshop / technical-lineage affinity
- omega_k: object-class production vector
- phi_k: symbolic / stylistic affinity vector
- delta_k: deposition-mode vector
- r_k: recycling / remelting behavior

Multiple jetbundles may share the Atesis trunk and then diverge. One source can feed several jetbundles; one jetbundle can mix several sources.

Recommended v0: 24–64 latent jetbundles, with K sampled per simulation seed.

---

## 3. Hidden aggregate flux constraint

The hidden scenario applies an aggregate mass constraint at one or more river checkpoints. This is a simulator hyperparameter, not player knowledge.

For checkpoint c:

Q_c = sum_t sum_k q_k(t) * I(J_k crosses c)

The scenario target enters as either:
- hard constrained mode: Q_c = Q_target
- soft Bayesian mode: log Q_c ~ Normal(log Q_target, sigma_Q)

Use soft mode for gameplay Monte Carlo so alternative worlds can remain plausible.

The distribution over jetbundle shares is hierarchical:

w ~ Dirichlet(alpha_1 ... alpha_K)
q_k(t) = Q_t * w_k * g_k(t) / Z_t

where g_k(t) is a smooth temporal pulse (B-spline, log-Gaussian, or piecewise random walk).

The target never appears in exported player-facing GeoJSON.

---

## 4. Network substrate

Use the Watershed repository hydrology as the routing skeleton:
- HydroBASINS downstream topology for basin relations
- HydroRIVERS river geometry for flow corridors
- explicit pass / portage / coast / lagoon edges added as non-hydrological connectors

Each edge e has hidden generalized transport cost:

C_e(t,m) = distance_e * terrain_e * season_e * mode_e(m) + transfer_penalty_e - hub_bonus_e - lineage_bonus_e

Route probability for a jetbundle:

P(pi | J_k,t) proportional to exp(-beta_route * C(pi,t))

Do not force all metal onto shortest paths. beta_route is sampled, creating route diversity and alternate corridors.

---

## 5. Source fields and production

Each source field f has:

F_f = (location, active_interval, production_capacity(t), chemistry, isotope_field, ore_type, fuel_cost, labor_cost)

Primary output:

Q_f(t) ~ LogNormal(mu_f(t), sigma_f)

subject to:
- known archaeological chronology priors
- production-capacity priors
- charcoal / timber availability
- mining and smelting labor

A jetbundle chooses source proportions:

s_k ~ Dirichlet(a_source)

but incompatible / inactive sources are masked at each t.

---

## 6. Metal-batch graph

Metal travels as batches, not as an abstract scalar.

For batch b:

B_b = (mass, date, source_mix, chemistry, isotopes, alloy_state, recycle_fraction, parent_batches)

Operations:
- split
- merge
- alloy
- remelt
- refine
- repair-feed
- export

Mass conservation:

sum mass(parents) + fresh_input = product_mass + recoverable_scrap + irreversible_loss

Chemistry is mixed mass-weightedly with process-specific fractionation / contamination terms. Isotope vectors are conserved unless the modeled process explicitly affects them.

This graph is the bridge between flux theory and laboratory provenance tests.

---

## 7. Workshop field

Workshop w:

W_w = (location, active_interval, workers, capacity, parent_lineage, technical_vector, demand_vector, access_vector)

Technical vector theta_w includes:
- alloy target
- mould family
- casting method
- hammer / anneal sequence
- join method
- surface treatment
- repair behavior
- scrap tolerance
- dimensional habits

Lineage inheritance:

theta_child = theta_parent + innovation_noise + local_adaptation

Workshop lineage movement and metal movement are independent latent processes. This allows:
- same technique, different source
- same source, different technique
- same symbolism, different technique

---

## 8. Object production

Objects are generated from workshop throughput and local demand.

For object class c:

P(c | w,t,J_k) proportional to local_demand_c(t) * omega_k[c] * workshop_skill_w[c] * status_context

Object o:

O_o = (class, mass, batch_id, workshop_id, manufacture_date, technical_signature, symbolic_signature, use_history, repair_history, movement_history)

A single object may move between jetbundles after manufacture through exchange, inheritance, raiding, gift, repair or recycling.

Do not instantiate every transient object as a heavyweight Python object. Use aggregate production counts by workshop/class/time slice, then materialize individual biographies only for objects that enter deposition candidates or are selected for the game.

---

## 9. Object-count scale

The simulator should be able to represent tens to hundreds of millions of manufacture/use events while storing only aggregates.

For workshop w and class c in slice t:

N_wct ~ Poisson(M_wct / mean_mass_c)

where M_wct is copper-alloy mass allocated to that class.

Store:
- aggregate count
- mass moments
- batch-mixture proportions
- lineage proportions

Materialize individual object biographies only after deposition sampling. This keeps the model computationally tractable while allowing the archaeological record to originate from a genuinely huge hidden population of objects.

---

## 10. Hoard and deposition generator

Deposition event h:

H_h = (location, date, mode, selector, size, age_profile, bundle_mix)

Modes include:
- founder / scrap hoard
- finished-object hoard
- ritual/selective deposit
- personal wealth deposit
- grave assemblage
- settlement loss
- river / wetland deposit
- workshop debris
- catastrophic abandonment

The selector is essential. A hoard is NOT an unbiased local sample.

Example:

P(o in h) proportional to
local_availability(o) *
class_preference_h(o) *
metal_value_h(o) *
symbolic_affinity_h(o) *
fragmentation_preference_h(o) *
age_kernel_h(o)

This is where jetbundles become visible as overlapping object clusters rather than drawn historical arrows.

---

## 11. Preservation and discovery filter

For deposited object o:

p_survive(o) = f(material, corrosion_environment, burial_depth, disturbance, fire, waterlogging)

p_discover(o) = f(land_use, excavation_intensity, erosion, construction, collecting_history, detector_bias)

p_catalog(o) = f(object_recognizability, museum_practice, publication_bias, sampling_policy)

Observed archaeology:

Y ~ Bernoulli(p_survive * p_discover * p_catalog)

This filter must be strong enough that the player never sees a representative sample of the hidden economy.

---

## 12. Game specimen selector: 300 objects

The 300 Dr. Corrosion objects are selected from the discovered/catalogued population, not directly from production.

Selector objective:

Score(o) =
coverage_time +
coverage_space +
coverage_source +
coverage_technique +
coverage_object_class +
coverage_hoard +
diagnostic_information +
difficulty_target -
redundancy

Use constrained stratified selection:
- 30 archaeometallurgy levels x 10 objects
- preserve chronological progression
- intentionally include false friends and ambiguous provenance
- ensure repeated jetbundles appear across distant objects so the player can discover them
- ensure some visually similar objects belong to different jetbundles
- ensure some chemically similar objects belong to different technical lineages

The final 300 should contain enough repeated latent structure to reconstruct the network but never enough to trivially read it off.

---

## 13. Bayesian inference available to Dr. Corrosion

The player-facing hypothesis engine estimates posterior links such as:

P(source_f | chemistry, isotopes, chronology)
P(workshop_w | metallography, dimensions, manufacture sequence)
P(lineage_g | technique, repair, decoration, time)
P(jetbundle_k | source, workshop, location, chronology, hoard context)

But J_k itself should not initially be named or visible. The UI first shows pairwise / cluster evidence. Jetbundle-like clusters become explicit only when enough evidence accumulates.

---

## 14. Hidden-vs-visible schema

NEVER export to ordinary game data:
- scenario total throughput
- true source mix
- true jetbundle ID
- true workshop lineage ID
- true transport route
- true deposition-mode label when archaeologically ambiguous
- simulator posterior ground truth

Player-visible exports may contain:
- findspot and dating uncertainty
- object description
- preservation state
- available test menu
- measured test results with uncertainty
- known excavation context
- published typological comparison
- player's own inferred relationships

A developer/debug build may expose the ground truth under a separate switch.

---

## 15. Jetbundle reconstruction score

For each latent bundle k, define how recoverable it is from the sampled 300:

R_k = I(source separation) * I(technical separation) * I(spatial recurrence) * I(temporal recurrence) * I(sample count)

During dataset generation, reject seeds where:
- every bundle is obvious
- no bundle is recoverable
- one bundle dominates nearly all 300 specimens

Target a mixture of:
- ~20% easy bundles
- ~50% recoverable only after multiple test types
- ~20% ambiguous / overlapping
- ~10% deliberately unresolved

---

## 16. Necessary jetbundle topology for v0

Do not hard-code cultural names. Require only structural bundle families:

1. upper-Atesis feeders -> southbound trunk
2. Trentino/eastern-Alpine feeders -> Atesis trunk
3. cross-Alpine/pass imports joining the trunk
4. Po-plain west/east redistribution bundles
5. Adriatic coastal export bundles
6. Adriatic return / import bundles
7. Tyrrhenian / Apennine cross-feed bundles
8. Danubian / eastern-Alpine competing routes
9. local workshop-recycling loops
10. prestige-object low-mass/high-distance bundles

Each family should instantiate several stochastic bundles with different time spans and source/technical associations.

---

## 17. Minimal simulation loop

For each Monte Carlo seed:

1. sample population / settlement field
2. sample active source capacities
3. sample jetbundle count and temporal profiles
4. solve network flow under soft checkpoint aggregate constraint
5. instantiate batch graph
6. allocate batches to workshops
7. propagate technical lineages
8. generate aggregate object production
9. materialize deposition candidates
10. generate hoards / losses / graves / wet deposits
11. apply preservation and discovery filters
12. produce archaeological catalogue
13. select 300 curriculum specimens
14. run recoverability diagnostics
15. reject / retain seed

The retained seed becomes one playable archaeological world.

---

## 18. Core anti-spoiler test

A valid build must permit the player to infer a high-flow Atesis-centered network without ever being told:
- that the Atesis is the correct trunk
- how much mass crossed it
- how many jetbundles exist
- whether Atolia is one cultural system

The dataset should support competing explanations until enough independent evidence accumulates.
