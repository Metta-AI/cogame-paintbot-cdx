#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
.venv/bin/pytest -q singlepod/test_runtime.py
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
nim c --hints:off -d:release -d:artlogNoCurl -o:"$work/parity" singlepod/parity.nim
"$work/parity" "$work/frames.jsonl"
.venv/bin/python singlepod/check_parity.py "$work/frames.jsonl"
nim c --hints:off -d:release -o:"$work/replay_check" singlepod/replay_check.nim
.venv/bin/python singlepod/local.py --variant ctf-1v1 --ticks 240 --output "$work/episode" --port "${TEST_PORT:-18080}"
"$work/replay_check" "$work/episode/replay.bin"
