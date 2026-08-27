# Atolia v2 mobile handoff — 2026-08-27

Branch: `atolia-v2-step4-9-workshop-tools`

Purpose: freeze the successful local execution state so work can continue from mobile/GitHub for the next two travel days without requiring the Windows machine.

## Current execution checkpoint

The first direct-NetCDF v2 benchmark completed end-to-end:

```text
production cells: 256
particles/cell: 2
exact terminal states: 512
profiles: 510
workshops: 3200
tools: 22746
hydro rows: 5030
master: cache/atolia_master_v2.nc
runtime: cache/atolia_runtime_v2.nc
```

Validator result from the local run:

```text
errors: []
ok: true
warnings:
  - legacy/fallback geochemistry
  - provisional graph-derived hydrology
```

Important successful invariants:

```text
Cu closure error ~ -7.3e-12 kg
Sn closure error ~ 9.1e-13 kg
source mixtures sum ~ 1.0
runtime omits exact state rows
max cumulative metal distance ~ 1865 km
max current-object distance ~ 495 km
states with remelt: 249/512
states with repair: 233/512
states with water movement: 499/512
states with Atesis crossing: 78/512
```

This is sufficient to stop local/offline execution work for now.

## Critical interpretation: mass share != object incidence

The benchmark reports:

```text
realized_atesis_primary_cu_share ~= 0.8858
```

Do **not** interpret this as "88.6% of all final pieces are Atolia copper" and do not immediately force it to 0.20.

The current benchmark selected the first 256 production cells, so this primary-mass share is biased toward early/A tesis-heavy cells and is not a representative whole-world calibration sample.

More importantly, even in the final world these are different quantities:

```text
A) fraction of total primary Cu mass associated with Atesis
B) fraction of final objects containing any Atesis-associated metal
C) fraction of each object's mass that is Atesis-associated
D) number of Atesis crossings in a lineage biography
```

With strong recycling/mixing, B can be much larger than A.

For a simple independent-contribution approximation,

```text
P(any Atesis metal in an object) = 1 - (1-p)^n
```

where `p` is the Atesis mass/source contribution probability and `n` is the effective number of independently mixed contributions.

At `p=0.20` and `n=8`:

```text
1 - 0.8^8 ~= 0.832
```

So a world with ~20% Atesis-associated Cu mass can plausibly have ~80% of sufficiently recycled/mixed objects contain *some* Atesis metal. The v2 model should explicitly measure this instead of conflating mass share with incidence.

## Next code task: benchmark selection

Replace positional:

```python
selected = all_cells[:cell_limit]
```

with deterministic stratified benchmark sampling across at least:

```text
time
bundle family
object class
Atesis-source fraction
source entropy
regional/source family
```

The benchmark should span the full 2000-1000 BCE horizon and both Atesis-rich and Atesis-poor cells.

This is a benchmark/calibration fix only. Full mode still processes all cells and is not subject to this sampling bias.

## Next diagnostic: Atesis incidence

Add separate release diagnostics:

```text
primary_atesis_cu_mass_share
object_episode_any_atesis_fraction
terminal_object_any_atesis_fraction
terminal_object_atesis_mass_fraction_mean
terminal_object_atesis_mass_fraction_quantiles
atesis_lineage_crossing_fraction
atesis_source_ancestry_entropy
```

This requires each explicit aggregate particle/state to retain an Atesis-associated Cu inventory (or equivalent source-mixture lineage state), not only an initial cell source fraction.

During remelt/mixing:

```text
M_Atesis,new = sum(M_Atesis,input_i)
M_Cu,new     = sum(M_Cu,input_i)
f_Atesis     = M_Atesis,new / M_Cu,new
```

`any_atesis = f_Atesis > epsilon` is then a separate incidence statistic.

## Mobile tasks for the next two travel days

No large local build is required. Work can continue remotely in GitHub/chat on:

1. **Stratified benchmark selector** and incidence diagnostics.
2. **Real Step-3 geochemistry input** covering the currently missing sources: Balkan, Britain/Wales, central Rhine Europe, eastern Alps, Iberia/west Med, Liguria/Tuscany, lower Danube/Balkans, Trentino East, Upper Atesis, Veneto pre-Alps, western Alps/Rhone.
3. **Real Step-4.5 palaeohydrology ingestion specification/data adapters** for Po/Adige/northern Adriatic first, then broader Mediterranean.
4. **Upper-river mine occurrence catalogue** for Südtirol/Trentino with evidence class separation: geological occurrence / evidenced ancient mining / simulated active mine.
5. **External exchange tails** and rare-object diagnostics without quotas.
6. **Workshop/tool lineage refinement** where archaeological/tool evidence improves actual process envelopes.

Do not start the canonical full overnight run until real geochemistry and real palaeohydrology inputs are present or the scientific gates are deliberately overridden for a noncanonical test.

## What not to do during travel

Do not:

```text
rerun the same biased 256-cell benchmark
force the 88.6% benchmark primary share to 20% by hand
interpret primary-mass share as object incidence
tune the final 300 career objects to fit Atoliamaxx
merge the branch into unrelated game repos
```

## Resume command on the Windows machine later

```powershell
git switch atolia-v2-step4-9-workshop-tools
git pull
python -m pytest src/atolia/tests/test_v2_step5.py -q
python src/atolia/build_v2_direct_world.py `
  --mode benchmark `
  --hypothesis hypotheses/atolia_v2_2000_1000_structural.json
python src/atolia/validate_v2_direct_world.py
```

Only rerun after benchmark stratification/incidence diagnostics have landed.

## Current scientific status

The strongest conclusion from the first successful benchmark is not a specific historical percentage. It is that the v2 machinery now simultaneously supports:

```text
conserved metal inventories
multiple object lives through recycling
repair
water-heavy mobility
long cumulative metal biographies
workshop/tool lineages
hydrological carrier uncertainty
late correlated terminal deposition
direct NetCDF master -> runtime
```

That is a sufficient checkpoint to switch from laptop execution to mobile model/data work.
