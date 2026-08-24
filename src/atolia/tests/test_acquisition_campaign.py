from __future__ import annotations

import math

import acquisition_campaign as campaign


def test_schedule_is_exactly_300_objects():
    covered = []
    for regime in campaign.REGIMES:
        covered.extend(range(regime.start, regime.end + 1))
    assert covered == list(range(1, 301))


def test_schedule_boundaries_and_poari_lenses():
    assert campaign.regime_for_index(1).name == "stray_tail"
    assert campaign.regime_for_index(50).name == "stray_tail"
    assert campaign.regime_for_index(51).name == "context_followup"
    assert campaign.regime_for_index(70).name == "context_followup"
    assert campaign.regime_for_index(71).name == "random_hoard"
    assert campaign.regime_for_index(100).name == "random_hoard"
    assert campaign.regime_for_index(101).name == "post_hoard_comparison"
    assert campaign.regime_for_index(130).name == "post_hoard_comparison"
    assert campaign.regime_for_index(131).name == "exploratory_dig"
    assert campaign.regime_for_index(190).name == "exploratory_dig"
    assert campaign.regime_for_index(191).name == "discriminating_dig"
    assert campaign.regime_for_index(250).name == "discriminating_dig"
    assert campaign.regime_for_index(251).name == "network_reconstruction"
    assert campaign.regime_for_index(290).name == "network_reconstruction"
    assert campaign.regime_for_index(291).name == "falsification_probe"
    assert campaign.regime_for_index(300).name == "falsification_probe"

    assert campaign.regime_for_index(1).p == -1.0
    assert campaign.regime_for_index(71).p == 0.0
    assert campaign.regime_for_index(191).p == 1.0
    assert campaign.regime_for_index(251).p == 2.0
    assert campaign.regime_for_index(291).p == -1.0


def test_p_measure_preserves_harmonic_geometric_arithmetic_quadratic_order():
    values = {"a": .18, "b": .42, "c": .91}
    weights = {"a": .2, "b": .3, "c": .5}
    hm = campaign.p_measure(values, weights, -1.0)
    gm = campaign.p_measure(values, weights, 0.0)
    am = campaign.p_measure(values, weights, 1.0)
    qm = campaign.p_measure(values, weights, 2.0)
    assert 0 < hm < gm < am < qm <= 1.0


def test_harmonic_action_score_is_weak_dimension_sensitive():
    weights = {"information_gain": .5, "recoverability": .5}
    balanced = campaign.p_measure({"information_gain": .55, "recoverability": .55}, weights, -1.0)
    weak_link = campaign.p_measure({"information_gain": .95, "recoverability": .15}, weights, -1.0)
    assert balanced > weak_link


def test_random_hoard_block_is_exactly_thirty_slots():
    r = next(r for r in campaign.REGIMES if r.name == "random_hoard")
    assert r.end - r.start + 1 == 30
    assert r.site_block_min == 30
    assert r.site_block_max == 30


def test_early_tail_target_is_predominant_not_absolute():
    assert .5 < campaign.EARLY_TAIL_TARGET < 1.0
