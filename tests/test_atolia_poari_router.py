import importlib.util
import math
from pathlib import Path


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, Path(path))
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_generalized_mean_lenses_order_for_unequal_vector():
    p = load("poari_router", "src/atolia/poari_career_router.py")
    x = [0.2, 0.5, 0.9]
    hm = p.p_mean(x, p=-1)
    gm = p.p_mean(x, p=0)
    am = p.p_mean(x, p=1)
    qm = p.p_mean(x, p=2)
    assert hm < gm < am < qm


def test_level_schedule_moves_from_weak_dimension_drag_to_hotspots():
    p = load("poari_router_schedule", "src/atolia/poari_career_router.py")
    assert p.p_for_level(1) == -1
    assert p.p_for_level(8) == -1
    assert p.p_for_level(9) == 0
    assert p.p_for_level(18) == 0
    assert p.p_for_level(19) == 1
    assert p.p_for_level(25) == 1
    assert p.p_for_level(26) == 2
    assert p.p_for_level(30) == 2


def test_player_key_seed_and_package_id_are_stable_and_distinct():
    pkg = load("player_package", "src/atolia/player_game_package.py")
    a1 = pkg.seed_from_player_key("player-a")
    a2 = pkg.seed_from_player_key("player-a")
    b = pkg.seed_from_player_key("player-b")
    assert a1 == a2
    assert a1 != b
    assert pkg.package_id("player-a") == pkg.package_id("player-a")
    assert pkg.package_id("player-a") != pkg.package_id("player-b")


def test_generator_contract_is_player_safe():
    import json
    spec = json.loads(Path("atolia_game_generator.json").read_text())
    assert spec["player_response"]["objects"] == 300
    assert spec["routing"]["p_schedule"] == {
        "levels_1_8": -1,
        "levels_9_18": 0,
        "levels_19_25": 1,
        "levels_26_30": 2,
    }
    text = json.dumps(spec)
    assert "200000" not in text
    assert "target_tonnes" not in text
