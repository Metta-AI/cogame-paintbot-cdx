# Validation — 2026-09-09

Verified locally on macOS arm64, plus the Linux arm64 game container:

- Nim 2.2.6 / WASI SDK 33 compiled the full baseline to a 328 KiB WASI reactor.
- 20 Python tests passed: baseline initialization, malformed replies/pointers,
  WASM memory isolation, fuel exhaustion, memory-growth bounds, denied imports,
  seat validation, SHA-256 checks, HTTPS/S3 loaders, and host failure attribution.
- Native and WASM baseline outputs matched for all 241 real Sprite observation
  frames emitted by the parity harness.
- Full two-seat, 16-seat 2v2, 16-seat four-team, and 32-seat four-team games ran
  through the single-pod host and wrote results and per-seat success statuses.
- The canonical native replay engine verified all 2,220 hashes in the 16-seat
  replay and all 2,873 hashes in the 32-seat replay.
- The rebuilt static WASM viewer loaded the 32-seat recording and advanced
  300 frames (449 MiB heap).
- One Linux container, with external networking disabled and a 2-CPU / 3-GiB
  limit, completed a match using its own packaged WASM baseline. Both seats
  exited successfully, and the game wrote results plus a COWLDCTF replay.
- The current local Coworld Pydantic manifest model accepted the package.
  All eight compatible variant configs and the certification config validate
  against the game schema. The observed 2/16/32-seat results validate against
  the results schema.

The original two-billion-fuel limit failed giant-map navigation. The runtime
uses a measured working budget of 20 billion fuel units per observation, with
30-second epoch interruption and a 256-MiB per-instance linear-memory limit.
These are resource bounds, not policy-strength measurements.

`singlepod/test.sh` and `singlepod/container_smoke.py` reproduce the core checks.
The workflow in `.github/workflows/single-pod.yml` builds and tests on Linux.
Hosted Coworld certification/deployment and league changes are not part of
these local results. Vet could not review because no API credentials were
available; compiler checks, lint, adversarial tests and integration tests ran.
