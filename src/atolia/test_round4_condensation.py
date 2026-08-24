from __future__ import annotations

import math

import archaeological_condensation_v3 as c


def row(mode="river_wetland_deposit", obj="sword", distance=900.0, physical=2.0, field=1.2, recycle=0, repairs=0):
    return {
        "candidate_id": "x",
        "importance_weight": 12.0,
        "production_cell_truth": {"object_class": obj, "origin_region": "atolia_core"},
        "deposition_truth": {"mode": mode, "region": "aegean"},
        "biography_truth": {
            "route_distance_km_expected": distance,
            "physical_crossings_expected": physical,
            "field_crossings_expected": field,
            "recycle_count": recycle,
            "repair_count": repairs,
            "source_entropy_expected": .5,
            "guild_family_truth": "g01",
        },
    }


def test_probability_chain_is_explicit_product():
    r = row()
    p = c.observation_probability(r)
    assert 0 < p["p_survival"] <= 1
    assert 0 < p["p_discovery"] <= 1
    assert 0 < p["p_record"] <= 1
    assert math.isclose(p["p_observed_given_loss"], p["p_survival"] * p["p_discovery"] * p["p_record"], rel_tol=1e-12)


def test_wetland_survives_better_but_is_discovered_less_than_workshop():
    wet = row(mode="river_wetland_deposit")
    shop = row(mode="workshop_debris")
    assert c.survival_probability(wet) > c.survival_probability(shop)
    assert c.discovery_probability(wet) < c.discovery_probability(shop)


def test_recycling_reduces_survival_integrity():
    clean = row(recycle=0, repairs=0)
    worked = row(recycle=5, repairs=3)
    assert c.survival_probability(worked) < c.survival_probability(clean)


def test_catalogue_contract_exact_30k_and_deterministic():
    rows = [row(), row(mode="workshop_debris", obj="awl", distance=40, physical=0, field=0)]
    for i, r in enumerate(rows):
        r["candidate_id"] = f"x{i}"
    c.assign_observation_truth(rows)
    a, sa = c.weighted_poisson_catalogue(rows, target_catalogue=30_000, seed=17)
    b, sb = c.weighted_poisson_catalogue(rows, target_catalogue=30_000, seed=17)
    assert len(a) == 30_000
    assert len(b) == 30_000
    assert [x["source_candidate_id"] for x in a] == [x["source_candidate_id"] for x in b]
    assert math.isclose(sa["represented_archaeological_intensity"], sb["represented_archaeological_intensity"], rel_tol=1e-12)


def test_enrichment_ratio_detects_tail_enrichment():
    before = {"distance_bin": {"0-100": .9, "1400+": .1}}
    after = {"distance_bin": {"0-100": .6, "1400+": .4}}
    e = c.enrichment_ratios(before, after)
    assert e["distance_bin"]["1400+"] > 1.0
    assert e["distance_bin"]["0-100"] < 1.0
