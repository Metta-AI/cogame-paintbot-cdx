# Paintbot in one pod

This repository ports the full Paintbot engine from
[Metta-AI/coworld-ctf](https://github.com/Metta-AI/coworld-ctf), revision
`34ad7f3e` (2026-09-09; including the viewer updates merged during this port).

One container runs the native game and a Python launcher. The launcher hosts all
player policies inside Wasmtime, one isolated instance per seat. Policies are
single WASM files, not containers or executables. Internal loopback WebSockets
connect the instances to the existing game so its simulation, fog of war,
scoring, maps, health/global endpoints, and replay lifecycle remain intact.
There are no player pods or per-policy operating-system processes.

The compiled baseline is [baseline.wasm](baseline.wasm). Its source adapter
imports the complete upstream `players/baseline/baseline.nim`; the existing
transport-free `BaselineComponent` supplies the decisions. The WASM artifact
has no companion files. The [policy ABI](PROTOCOL.md) supports custom policies
in any language that can export the listed WASM functions.

## Build and play

Requires Nim 2.2.6, Nimby, Python/uv and a C compiler. The build script downloads
the checksum-pinned WASI SDK and Wasmtime C API using the upstream helper, and
installs Nim dependencies into this checkout.

```sh
./singlepod/build.sh
.venv/bin/python singlepod/local.py --variant ctf-1v1 --ticks 240 \
  --output singlepod/runs/example --port 8080
```

Open `http://localhost:8080/client/global` while the game is running. The output
directory contains `results.json`, `replay.bin`, per-seat logs and
`player_status.json`. Use a new output directory for each episode. Omit `--ticks`
to run the variant's normal duration. Pass `--policy path/to/policy.wasm` once
for every seat to share that file, or pass it once per seat for a mixed roster.

```sh
./singlepod/test.sh
```

This checks malformed policies, memory isolation, resource limits, file digests,
241 native/WASM observation/action comparisons, and a complete match whose
replay is replayed through the original engine with every hash checked.

## Container / Coworld

```sh
docker build -t cogame-paintbot-cdx:local .
```

Use `coworld_manifest.json` as the package manifest. It declares
`game.player_runtime: game-hosted` and a file-backed baseline player. Supply the
built game image in `{{GAME_IMAGE}}` when packaging. The launcher accepts the
current Coworld variables:

- `COGAME_PLAYER_SEATS_URI`: seat document and policy file locations.
- `COGAME_CONFIG_URI`: the original game config JSON.
- `COGAME_RESULTS_URI` and `COGAME_SAVE_REPLAY_URI`: local result/replay outputs.
- `COGAME_PLAYER_FAILURE_URI`: structured seat failure output.
- `COGAME_PORT`: viewer and health port, default 8080.
- `COGAME_LOAD_REPLAY_URI`: bypass policies and run the upstream replay server.

The launcher verifies the roster, assigns private connection tokens, and runs
one finite episode. A failure of any policy fails the episode and identifies its
seat. Guests receive no access to those tokens or the seat document. The manifest
reserves 2 CPUs / 2 GiB and caps the pod at 8 CPUs / 12 GiB; each guest is capped
at 256 MiB. Hosted certification and deployment are separate from local builds.

The static replay viewer is the upstream build:
`tools/build_replay_viewer.sh "$PWD/static-replay-viewer"`. It uses the same
simulation sources and `COWLDCTF` recordings. All upstream art, viewer source,
game rules, tests, and shell modules remain in this repository.

## League formats and scope

The main manifest exposes the eight direct-input variants: `default`, `1v1`,
`2v2`, `4ffa`, `4ffa8`, `ctf-default`, `ctf-1v1`, and `battle-royale`. `default` is the classic default.
The names `1v1` and `2v2` count entrant policies, not individual cogs: those
formats normally have 16 seats. `ctf-1v1` is a two-seat local smoke format.

Live inspection on 2026-09-09 found Elite Paintbot
(`15cf0b94-6081-4750-9c8f-49493da4ced2`) configured for landscape competition
with `1v1`, `2v2`, and `4ffa`. The former campaign league
(`b8fa9b35-ac22-48cf-a03f-07b397aff1c7`) now runs Season 2 battle royale, with
its campaign flag disabled. The campaign/landscape boards and scheduling live
in Coworld, outside this game repository; this port supplies their game variants
and does not create or change live leagues.

File policies here control Sprite v1 actuators. The deprecated LLM squad KOTH
variant and Season 2 play-seat variants are retained in the reference manifest,
not advertised as compatible file-policy variants. The upstream Season 2 play-call
shell and its game-side logic remain in the engine, but the file-policy ABI
is not the Season 2 LLM play-seat upload protocol. Battle-royale simulation can
run with input seats. LLM policy containers must be ported to the file ABI before
being used as file-backed entrants.
