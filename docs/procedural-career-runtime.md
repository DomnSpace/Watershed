# Procedural archaeology career runtime

This branch is a reproducible generator source, not the final Dr. Corrosion frontend.

## Offline

Python 3.11+ is enough for the archaeology generator. From the repository root:

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate
pip install -r requirements-atolia.txt
python generate_player_game.py test-player-001 --out out/test-player-001.json
```

The same player key under the same generator version recreates the same 300-object career. A different key produces a different deterministic hidden world / archaeological record / career / measurement realization.

Developer inspection only:

```bash
python generate_player_game.py test-player-001 --debug --out out/test-player-001-debug.json
```

Never ship a debug package to a player.

## Tiny HTTP seam

For local frontend development:

```bash
python serve_player_game.py
```

Then request:

```text
GET http://127.0.0.1:8765/game?player_key=test-player-001
```

The server caches immutable player packages under `out/player_cache/<generator-version>/`. `/health` exposes only the generator version.

A production website can implement the same endpoint with a serverless function, job worker, or small service. The service should keep a checkout/container image pinned to a generator version, generate once, cache the result, and return only the player-safe JSON.

The browser should not fetch hidden hypothesis JSON, debug truth, guild identities, true jetbundles, or route traces. `atolia_game_generator.json` is the neutral client/runtime contract.

## POARI routing

The selector is implemented as a concrete p-measure route over the archaeological possibility field.

- `Phi_t`: surviving/catalogued candidate field.
- `G_t`: hidden provenance, workshop, guild, hoard and transport graph.
- `pi_t`: current policy over candidates for a curriculum slot.
- `theta_t`: curriculum, anti-spoiler bounds, recurrence roles, target distributions and p schedule.

The generalized mean schedule is:

- Levels 1–8: `p=-1`, weak-dimension/harmonic drag. A candidate with one bad dimension is strongly penalized.
- Levels 9–18: `p=0`, geometric overlap. Multiple evidence dimensions must coexist.
- Levels 19–25: `p=1`, arithmetic accumulation. Independent evidence can accumulate.
- Levels 26–30: `p=2`, quadratic/hotspot regime. Rare highly informative objects can dominate when the curriculum permits them.

After the first 300 selections an involutive rewrite may swap only independent/background slots. The slot identities and recurrence structure remain fixed while world-shape coherence is improved across region, bundle, source and object-class distributions. The default global coherence emphasizes the geometric lens while retaining harmonic weak-dimension pressure.

## Save compatibility

A final game should store at least:

```text
generator_version
package_id
player_key or a stable server-side equivalent
selected object ids (recommended compatibility checkpoint)
player progress/state
```

For long-lived saves, do not silently regenerate an old campaign with a newer generator version. Pin old campaigns to the version that created them.
