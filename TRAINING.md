# Paintbot CDX training

`tools/train_bridge.nim` runs the production Arena simulation without a
websocket. It accepts every certified variant in `coworld_manifest.json`.
Seat 0 is the learner. The bridge sends its inputs through Sprite v1 and
reads only its fogged player frames. `semantic_view.sprite_v1_base64` is the
exact frame; `visible_objects` lists policy-facing labels and positions from
that frame. The 11 numeric values contain time, self position and life,
aim, trigger readiness, visible actors and pickups, and map dimensions.
Actions are all 256 Sprite v1 input masks.

The shipped baseline drives seat 0 and the other seats in two-team games.
Its role and color model is limited to red and blue. Four- and 16-team games
use deterministic legal movement and periodic shots for opponents instead.
These opponents see no simulation state.

Compile the native bridge with the pinned Nim dependencies:

```sh
nimby --global sync nimby.lock
nim c -d:release --path:. --path:src --path:players/baseline \
  --out:train-bridge tools/train_bridge.nim
python3 tests/test_train_bridge.py ./train-bridge
```

The bridge command is `./train-bridge coworld_manifest.json VARIANT
[MAX_TICKS]`. `MAX_TICKS` creates a bounded curriculum: it disables the
classic grenade barrage, which otherwise disables the draw ceiling, and
shortens the post-game countdown. The default uses the certified game rules.
Use the bounded form for smoke tests and baseline imitation. Full games are
needed for outcome learning; 32-tick draws give every seat the same score.

Pass this command to `recipes.external.coworld.train` for native PufferLib
or `recipes.external.coworld_metta_rl.train` for Metta RL. Set `players` to
the variant's `num_agents`, `seat=0`, and a finite timestep limit. For
PufferLib imitation, enable the recipe's teacher loss to learn from the
shipped baseline. `max_decisions` must cover the game or its curriculum.

Metta post-training can learn text decisions over the visible label projection:

```sh
python3 tools/export_posttrain.py ./train-bridge /tmp/cdx-data 10 ctf-1v1 32
```

The exporter records whole games, splits them by episode, and writes
`train.jsonl`, `validation.jsonl`, and `manifest.json`. The completion is a
JSON mask. The player runtime consumes WASM files with a 24 Hz Sprite
interface; a text model trained on this data needs a WASM inference adapter
before it can play in a hosted game.
