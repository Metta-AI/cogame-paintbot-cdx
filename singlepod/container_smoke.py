"""Run the packaged game and its packaged WASM baseline in exactly one container."""

import argparse
import hashlib
import json
import os
import subprocess
import tempfile
import zipfile
from pathlib import Path

import wasmtime

ROOT = Path(__file__).resolve().parent.parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", default="cogame-paintbot-cdx:local")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="paintbot-cdx-container-") as directory:
        root = Path(directory)
        data = subprocess.check_output(
            [
                "docker",
                "run",
                "--rm",
                "--entrypoint",
                "cat",
                args.image,
                "/workspace/ctf/singlepod/baseline.wasm",
            ]
        )
        policy = root / "baseline.wasm"
        policy.write_bytes(data)
        config = next(
            v["game_config"]
            for v in json.loads((ROOT / "coworld_manifest.json").read_text())[
                "variants"
            ]
            if v["id"] == "ctf-1v1"
        ).copy()
        config.update(
            maxTicks=240,
            startWaitTicks=0,
            gameOverTicks=1,
            speed=4,
            seed=7,
            barrageMaxPerSec=0,
        )
        config["players"] = [
            {"name": "coworld-smoke/test:v1"},
            {"name": "coworld-smoke/test:v1 (2)"},
        ]
        (root / "config.json").write_text(json.dumps(config))
        seats = [
            {
                "slot": slot,
                "file_uri": "file:///coworld/baseline.wasm",
                "size_bytes": len(data),
                "content_hash": "sha256:" + hashlib.sha256(data).hexdigest(),
                "log_uri": f"file:///coworld/logs/policy_agent_{slot}.log",
                "artifact_uri": f"file:///coworld/policy_artifact_{slot}.zip",
            }
            for slot in range(2)
        ]
        (root / "seats.json").write_text(
            json.dumps(
                {
                    "schema": "coworld-player-seats/1",
                    "seats": seats,
                    "player_status_uri": "file:///coworld/player_status.json",
                }
            )
        )
        command = [
            "docker",
            "run",
            "--rm",
            "--network",
            "none",
            "--user",
            f"{os.getuid()}:{os.getgid()}",
            "--memory",
            "3g",
            "--cpus",
            "2",
            "-v",
            f"{root}:/coworld",
            "-e",
            "COGAME_PLAYER_SEATS_URI=file:///coworld/seats.json",
            "-e",
            "COGAME_CONFIG_URI=file:///coworld/config.json",
            "-e",
            "COGAME_RESULTS_URI=file:///coworld/results.json",
            "-e",
            "COGAME_SAVE_REPLAY_URI=file:///coworld/replay.bin",
            args.image,
        ]
        subprocess.run(command, check=True, timeout=180)
        results = json.loads((root / "results.json").read_text())
        assert len(results["scores"]) == 2
        assert (root / "replay.bin").read_bytes().startswith(b"COWLDCTF")
        statuses = json.loads((root / "player_status.json").read_text())["players"]
        assert all(s["state"] == "exited" and s["exit_code"] == 0 for s in statuses)
        assert not list(root.glob("policy_artifact_*.zip"))
        for slot in range(2):
            assert (
                "WASM policy started"
                in (root / f"logs/policy_agent_{slot}.log").read_text()
            )
        print(
            "One-container episode passed: 2 WASM seats, results, replay, successful statuses; network disabled"
        )
        failed = root / "malformed"
        failed.mkdir()
        (failed / "baseline.wasm").write_bytes(data)
        malformed = wasmtime.wat2wasm(r"""(module
          (memory (export "memory") 272)
          (data (i32.const 0) "\00\00\00\00abcd")
          (func (export "paintbot_init") (param i32))
          (func (export "paintbot_buffer") (param i32) (result i32) i32.const 1024)
          (func (export "paintbot_step") (result i32) i32.const 0)
          (func (export "paintbot_output_size") (result i32) i32.const 8))""")
        (failed / "malformed.wasm").write_bytes(malformed)
        (failed / "config.json").write_text(json.dumps(config))
        seats[0].update(
            file_uri="file:///coworld/malformed.wasm",
            size_bytes=len(malformed),
            content_hash="sha256:" + hashlib.sha256(malformed).hexdigest(),
        )
        (failed / "seats.json").write_text(
            json.dumps(
                {
                    "schema": "coworld-player-seats/1",
                    "seats": seats,
                    "player_status_uri": "file:///coworld/player_status.json",
                }
            )
        )
        command[command.index(f"{root}:/coworld")] = f"{failed}:/coworld"
        outcome = subprocess.run(command, check=False, timeout=180)
        assert outcome.returncode == 1
        failure = json.loads((failed / "player_failure.json").read_text())
        assert failure["failed_policy_index"] == 0
        assert not (failed / "results.json").exists()
        with zipfile.ZipFile(failed / "policy_artifact_0.zip") as archive:
            assert set(archive.namelist()) == {
                "observation.bin",
                "reply.bin",
                "failure.json",
            }
            assert 0 < len(archive.read("observation.bin")) <= 16 * 1024 * 1024
            assert archive.read("reply.bin") == b"\0\0\0\0abcd"
            metadata = json.loads(archive.read("failure.json"))
            assert metadata == {
                "slot": 0,
                "frame": 1,
                "content_hash": seats[0]["content_hash"],
                "error": "trailing reply bytes",
            }
        assert not (failed / "policy_artifact_1.zip").exists()
        print(
            "Malformed WASM reply failed its seat and retained bounded private evidence"
        )


if __name__ == "__main__":
    main()
