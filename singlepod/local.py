"""Prepare and run a local episode using file policies and a manifest variant."""

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--variant", default="1v1")
    parser.add_argument("--seats", type=int, default=None)
    parser.add_argument("--ticks", type=int, default=None)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--policy", type=Path, action="append")
    args = parser.parse_args()
    manifest = json.loads((ROOT / "coworld_manifest.json").read_text())
    config = next(
        v["game_config"] for v in manifest["variants"] if v["id"] == args.variant
    ).copy()
    count = args.seats or config.get("num_agents", 16)
    config["players"] = [{"name": f"WASM-{i}"} for i in range(count)]
    config.update(
        minPlayers=count, seed=args.seed, startWaitTicks=0, gameOverTicks=1, speed=4
    )
    if args.ticks is not None:
        config["maxTicks"] = args.ticks
    policies = args.policy or [ROOT / "singlepod/baseline.wasm"]
    if len(policies) not in (1, count):
        parser.error("provide one shared policy or exactly one --policy per seat")
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    seats = []
    for slot in range(count):
        policy = policies[slot % len(policies)].resolve()
        data = policy.read_bytes()
        seats.append(
            {
                "slot": slot,
                "file_uri": policy.as_uri(),
                "content_hash": "sha256:" + hashlib.sha256(data).hexdigest(),
                "size_bytes": len(data),
                "log_uri": (output / f"logs/policy_agent_{slot}.log").as_uri(),
                "artifact_uri": (output / f"policy_artifact_{slot}.zip").as_uri(),
            }
        )
    (output / "seats.json").write_text(
        json.dumps(
            {
                "schema": "coworld-player-seats/1",
                "seats": seats,
                "player_status_uri": (output / "player_status.json").as_uri(),
            }
        )
    )
    (output / "config.json").write_text(json.dumps(config))
    return subprocess.call(
        [
            sys.executable,
            str(ROOT / "singlepod/host.py"),
            "--seats",
            str(output / "seats.json"),
            "--config",
            str(output / "config.json"),
            "--port",
            str(args.port),
        ]
    )


if __name__ == "__main__":
    raise SystemExit(main())
