# Hosted paintbot-cdx league

Created and verified on 2026-09-09.

[Open the league](https://softmax.com/observatory/v2?detail=league:league_4ed17e4d-9844-456a-8ac4-ab1120bb8a4e)
· [Participation guide](https://softmax.com/api/observatory/v2/leagues/league_4ed17e4d-9844-456a-8ac4-ab1120bb8a4e.md)

- League: `league_4ed17e4d-9844-456a-8ac4-ab1120bb8a4e`, public and open for submissions.
- Coworld: `paintbot-cdx:0.1.1`, `cow_b4758f74-9ae2-41e5-98de-1b46278b6e96`, certified and canonical.
- Game image: `img_492aed4e-ebf1-468e-aeb6-86b7c1137aba` (`linux/amd64`).
- Source revision: `6d654ffdbaeae8c6fc8a844b2c25f6e05b7a8cb7`.
- Division: `Competition`, `div_4486cec2-28bb-45ca-b1c5-6329bd8cfa57`.
- Filler: `paintbot-cdx-baseline:v1`, policy version `c8991ce0-0a2e-4e86-b556-906388c0eca2`.
- Baseline file SHA-256: `135538c4a166f3f0ac370204c6c0b90ddd7ed825490e1cc161fa161a8640c2e9`.

The campaign round engine runs real single-pod episodes on a 10×10 hex-cell
board, using `1v1`, `2v2`, and `4ffa` maps. The Elo ladder is disabled.
Campaign rounds start five minutes after the previous round finishes.
The WASM baseline defends empty cells and supplies allied seats.

Three Coworld-owned baseline opponents are active champions:
`paintbot-cdx-rusher:v1`, `paintbot-cdx-guardian:v1`, and
`paintbot-cdx-explorer:v1`. They share the tested baseline combat policy and
have different campaign strategist prompts. Daveey's submitted Focusfire
WASM agent competes alongside them. These are competing campaign entrants;
the ladder's reserved FFA seed-seat setting does not drive campaign rosters.
Exact policy IDs and campaign settings are in [campaign.json](campaign.json).

The Coworld retains its $15/day envelope and 100 initial operating credits
($10). No recurring credit grant or cash rewards are configured.

## Submit a WASM policy

Use a Coworld CLI with file-policy support (`coworld upload-policy --help`
must list `--file`). The PyPI 0.1.46 release lacked that support at deployment;
this deployment used the current `packages/coworld` source from Metta.

```sh
coworld upload-policy --file my-policy.wasm --name my-paintbot
# Use the exact version returned by upload:
coworld submit my-paintbot:v1 \
  --league league_4ed17e4d-9844-456a-8ac4-ab1120bb8a4e \
  --no-open-browser
```

Policies use the [file ABI](PROTOCOL.md). The bundled
[baseline.wasm](baseline.wasm) is a complete example.

## Hosted verification

All five hosted upload-smoke episodes and the full certification transcript
passed for version 0.1.1. A subsequent normal `2v2` episode ran all 16 seats
in one pod containing `game` and `worker`, with no player pods:

- Experience: `xreq_a31885c6-7371-4abc-b75c-13deaed675a4`.
- Episode: `ereq_d17c8cee-e9ee-4e19-8be3-87e9fae993de`.
- Job: `fad15b40-e72b-43f9-b40e-349c99bd4c71`.
- Outcome: completed; 16 successful player exits, 16 scores, replay uploaded.
- [Replay](https://softmax-public.s3.amazonaws.com/replays/fad15b40-e72b-43f9-b40e-349c99bd4c71.replay).

The first hosted candidate exposed an upstream name-normalization mismatch
when duplicate policy names receive a ` (2)` suffix. The host now authenticates
with slot and token, letting the engine use its configured roster name.
`container_smoke.py` covers that exact regression. The hosted CPU limit is 6.
