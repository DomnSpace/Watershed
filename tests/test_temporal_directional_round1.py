from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
ATOLIA = ROOT / "src" / "atolia"
sys.path.insert(0, str(ATOLIA))

import temporal_directional_model as temporal


class Edge:
    def __init__(self, a="upper", b="lower", mode="river_down"):
        self.a, self.b, self.mode = a, b, mode


def test_adriatic_aegean_pulse_is_temporal_not_permanent():
    peak = temporal.field_temporal_activation("adriatic_ionian_aegean", 1225)
    early = temporal.field_temporal_activation("adriatic_ionian_aegean", 1750)
    assert peak > early
    assert peak > 1.7


def test_rhine_sword_direction_is_stronger_than_danube_sword_direction():
    edge = Edge()
    rhine = temporal.directional_log_bias("sword", {"rhine_north_sea": 1.0}, edge, "upper", "lower", 1300)
    danube = temporal.directional_log_bias("sword", {"danube_sava_morava": 1.0}, edge, "upper", "lower", 1300)
    assert rhine > 0
    assert rhine > 4 * danube


def test_direction_reverses_when_traversal_reverses():
    edge = Edge()
    down = temporal.directional_log_bias("sword", {"rhine_north_sea": 1.0}, edge, "upper", "lower", 1300)
    up = temporal.directional_log_bias("sword", {"rhine_north_sea": 1.0}, edge, "lower", "upper", 1300)
    assert down == -up


def test_awl_has_low_route_temperature_and_local_character():
    assert temporal.route_temperature("awl", "river_down", 1300) < temporal.route_temperature("sword", "river_down", 1300)
    assert temporal.route_temperature("awl", "sea", 1200) < temporal.route_temperature("sword", "sea", 1200)


def test_troy_like_origin_prior_is_soft_normalized_mixture():
    prior = temporal.destination_origin_prior("western_anatolia")
    assert abs(sum(prior.values()) - 1.0) < 1e-12
    assert prior["danubian"] == .30
    assert prior["aegean_greek"] == .30
    assert prior["adriatic_padanic"] == .30


def test_production_multiplier_distinguishes_rhine_from_danube_sword_production():
    rhine = temporal.production_multiplier("sword", "rhine", 1300)
    danube = temporal.production_multiplier("sword", "lower_danube", 1300)
    assert danube > rhine
