# Atolia v3 phase 03 — source metallurgy contract

Branch: `atolia-v3-03-source-metallurgy`

Phase 03 adds material state to the phase-02 metal genealogy. It does **not**
change the v1 world/circulation spine and it does **not** create a parallel
particle simulator.

```text
v1 LossStratum
  -> phase-02 weighted MetalLineage
       -> existing metal batches + existing parent graph
            -> phase-03 BatchChemistry
```

The batch IDs, parent links, particle IDs and object episodes are inherited
exactly from phase 02.

## Conservation basis

The conserved state is mass, not concentration and not isotope ratio.

For every metal batch phase 03 stores elemental masses on the current basis:

```text
Cu Sn As Pb Ag Fe Zn Sb Ni Co Bi
```

and the Pb isotope inventory:

```text
Pb204 Pb206 Pb207 Pb208
```

For each batch:

```text
sum(element_mass_kg) = metal_mass_kg
sum(Pb isotope mass)  = Pb element mass
```

A remelt output is calculated only from the phase-02 parent contributions:

```text
child_element_e
  = sum_parent (contribution_parent / parent_metal_mass) * parent_element_e

child_Pb_isotope_i
  = sum_parent (contribution_parent / parent_metal_mass) * parent_Pb_isotope_i
```

There is no separate remelt counter used as a chemistry shortcut.

## Pb isotope rule

Pb isotope ratios are derived views, never conserved coordinates.

Source ratios are converted to isotope inventories using relative atom counts
and isotope masses. Mixtures add the isotope inventories and only then derive:

```text
206Pb/204Pb
207Pb/204Pb
208Pb/204Pb
```

This preserves the important distinction between copper ancestry and the source
that dominates the Pb carried by the final metal. A small metal component with a
large Pb concentration can dominate the measured Pb isotope signature.

The phase-03 master therefore stores source-resolved Pb carrier mass separately
from total metal ancestry and exposes `pb_dominant_source_id` as a developer
truth diagnostic.

## Source calibration status

The repository does **not** currently contain the empirical source-geochemistry
covariance database or the empirical Pb source covariance that the earlier Step-3
preparation document specified for the canonical model.

Phase 03 therefore refuses to invent such covariance.

Current source inputs are explicitly marked:

```text
provisional-legacy-v1-means-no-empirical-covariance
```

The inherited v1 source fields provide:

- fixed Sb, Ag, Ni, Co and Bi concentration means;
- fixed Pb isotope ratio means.

These are retained as legacy calibration means, not promoted to an empirical
multivariate source distribution.

The model also needs a Pb carrier concentration to convert those ratios to an
actual inventory. Until the source dataset is supplied, phase 03 uses one frozen,
auditable Pb-ppm prior per current v1 source. These values are **not measurements**
and are never resampled during a build.

Consequences:

- the current phase can test physical mixing and persistence semantics;
- it can generate internally consistent developer truth;
- it must **not** be presented as a calibrated archaeological source-attribution
  model;
- canonical/full scientific release remains gated on replacing these provisional
  source rows with the frozen empirical source dataset.

## Tin and alloying boundary

The repository also does not yet contain a resolved tin-source database.

Phase 03 therefore tracks Sn as real elemental mass but marks the alloy recipe as:

```text
provisional-object-class-alloy-prior-v1
```

Sn, As, Fe and Zn additions in root/recycle-pool packets are transparent process
priors used to establish conserved chemistry mechanics. They are not assigned a
fabricated ore provenance.

The current phase does not yet implement calibrated Sn-isotope fractionation,
Cu-isotope fractionation, slag/fume transfer coefficients, inclusions, corrosion
or laboratory measurement. Those require the appropriate evidence/calibration
inputs rather than guessed universal coefficients.

## NetCDF additions

Phase 03 appends:

```text
/sources/geochemistry
/metallurgy/batches
/metallurgy/elements
/metallurgy/pb_isotopes
/metallurgy/source_pb
```

The phase-01 `phase` and `spine_sha256` remain untouched. Root attributes link
phase 03 to both immutable predecessors:

```text
phase03_spine_sha256
phase03_biography_sha256
phase03_metallurgy_sha256
```

The reader recomputes the complete phase-03 hash after bulk-reading the tables.

## Gate

G4/phase-03 acceptance requires:

1. phase-01 G2 remains green;
2. phase-02 genealogy tests remain green;
3. every chemistry batch closes in total element mass;
4. every Pb inventory closes to Pb element mass;
5. Pb ratios round-trip through inventory representation;
6. every remelt child equals the contribution-weighted parent inventories;
7. phase-03 batch IDs equal phase-02 batch IDs exactly and in the same order;
8. phase-03 NetCDF write/read/hash roundtrip is exact;
9. the fast real smoke path runs the real v1 kernel and phases 01-03 end to end;
10. no v3 execution path imports `build_v2_direct_world` or `_simulate_particle`.
