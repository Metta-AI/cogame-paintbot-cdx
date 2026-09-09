"""Compare WASM replies to native baseline replies for every recorded observation."""

import base64
import json
import sys
from pathlib import Path

import wasmtime
from runtime import Policy


def main(path):
    config = wasmtime.Config()
    config.consume_fuel = True
    config.epoch_interruption = True
    with (
        wasmtime.Engine(config) as engine,
        wasmtime.Module.from_file(
            engine, str(Path(__file__).with_name("baseline.wasm"))
        ) as module,
    ):
        policy = Policy(engine, module, 0)
        try:
            count = 0
            with open(path) as frames:
                for count, line in enumerate(frames, 1):
                    row = json.loads(line)
                    actual = policy.step(base64.b64decode(row["frame"]))
                    expected = [base64.b64decode(reply) for reply in row["replies"]]
                    if actual != expected:
                        raise AssertionError(
                            f"frame {count}: WASM {actual!r} != native {expected!r}"
                        )
            print(f"Native/WASM parity: {count} identical observation/action frames")
        finally:
            policy.close()


if __name__ == "__main__":
    main(sys.argv[1])
