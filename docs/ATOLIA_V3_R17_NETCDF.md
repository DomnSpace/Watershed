# Atolia v3 R17 / player_17 NetCDF boundary

The game boundary is two NetCDF products, not a shard collection.

- `atolia_runtime_v3.nc` (R17): one small shared generative world resource. It stores the canonical world recipe, exact archaeological cell masses, exact cell/profile checkpoints, and the canonical Phase-07 hydro mend coordinates needed to rebuild selected cells without expanding the full world.
- `player_17.nc`: one private 300-object world slice crystallized from R17 plus the install/safe-specific player key. It contains the full selected Phase-02 through Phase-05 hidden truth needed by Dr. Corrosion and is sealed into the Arkadeon safe.

The 580 Phase-08 JSON fragments are build intermediates only. They are not runtime resources and are not copied into the game.

R17 selection fails closed when a lazily rebuilt cell does not reproduce its canonical SHA-256 checkpoint. Player generation always requires exactly 300 unique object identities. Same player key and R17 reproduce the same 300; a different key produces a different private selection.
