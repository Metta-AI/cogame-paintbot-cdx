#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
# nimby sync installs isolated dependencies into this checkout.
nimby sync nimby.lock
if [[ -z "${WASI_SDK_PATH:-}" || -z "${WASMTIME_C_API:-}" ]]; then
  deps=$(tools/runtime_spike/fetch_deps.sh)
  export WASI_SDK_PATH="$(printf '%s\n' "$deps" | sed -n 's/^WASI_SDK_PATH=//p')"
  export WASMTIME_C_API="$(printf '%s\n' "$deps" | sed -n 's/^WASMTIME_C_API=//p')"
fi
nim c --hints:off singlepod/baseline_wasm.nim
nim c --threads:on -d:release -d:noSignalHandler --hints:off -o:singlepod/ctf src/ctf.nim
uv venv --allow-existing .venv
uv pip install --python .venv/bin/python -r singlepod/requirements.txt pytest ruff
