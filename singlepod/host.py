"""One game container: native Paintbot plus file-backed policies hosted in Wasmtime."""

from __future__ import annotations

import argparse
import json
import os
import queue
import secrets
import signal
import subprocess
import threading
import time
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen

import wasmtime
from runtime import (
    Policy,
    load_seats,
    local_path,
    read_uri,
    verified_policy,
    write_json,
)
from websockets.exceptions import ConnectionClosed
from websockets.sync.client import connect

ROOT = Path(__file__).resolve().parent.parent


def run(args: argparse.Namespace) -> int:
    # Replay serving requires the original game's complete CLI and no player instances.
    if os.environ.get("COGAME_LOAD_REPLAY_URI") or any(
        a.startswith("--load-replay") for a in args.engine_args
    ):
        os.execv(args.engine, [args.engine, *args.engine_args])
    document = load_seats(args.seats)
    seats = document["seats"]
    workdir = local_path(document["player_status_uri"]).parent
    workdir.mkdir(parents=True, exist_ok=True)
    config = json.loads(read_uri(args.config, 4 * 1024 * 1024)) if args.config else {}
    count = len(seats)
    if "players" in config and len(config["players"]) != count:
        raise ValueError("player files and configured player count differ")
    if "slots" in config and len(config["slots"]) != count:
        raise ValueError("player files and configured slots differ")
    config.setdefault("players", [{"name": f"player-{i}"} for i in range(count)])
    config.setdefault("slots", [{} for _ in seats])
    if any(slot.get("control", "input") != "input" for slot in config["slots"]):
        raise ValueError(
            "file policies require input-controlled slots; Season 2 play seats use a different protocol"
        )
    if config.get("cogsPerTeam", 1) != 1:
        raise ValueError(
            "the file policy ABI controls one cog per seat; squad registrars use a different protocol"
        )
    tokens = [secrets.token_hex(24) for _ in seats]
    config["tokens"] = tokens
    for slot, token in zip(config["slots"], tokens, strict=True):
        slot["token"] = token
    config.update(minPlayers=count, closedRoster=True, maxGames=1)
    config.setdefault("maxTicks", 10000)
    if config["maxTicks"] <= 0:
        raise ValueError("single-pod episodes require a positive maxTicks")
    config_path = workdir / "engine-config.json"
    write_json(str(config_path), config)
    result_path = workdir / "results.json"
    replay_path = workdir / "replay.bin"
    results_uri = os.environ.get("COGAME_RESULTS_URI", result_path.as_uri())
    replay_uri = os.environ.get("COGAME_SAVE_REPLAY_URI", replay_path.as_uri())
    # Coworld stages outputs locally; requiring that makes successful completion observable.
    result_path = local_path(results_uri)
    local_path(replay_uri)
    if result_path.exists():
        raise ValueError("results path already exists; use a fresh episode directory")
    statuses = [{"slot": s["slot"], "state": "not_started"} for s in seats]
    lock = threading.Lock()
    stop = threading.Event()
    epoch_stop = threading.Event()
    errors: queue.Queue[tuple[int, str]] = queue.Queue()

    def status(
        slot: int, state: str, code: int | None = None, reason: str | None = None
    ):
        with lock:
            statuses[slot] = {
                "slot": slot,
                "state": state,
                "exit_code": code,
                "reason": reason,
            }
            write_json(
                document["player_status_uri"],
                {"schema_version": "1", "players": statuses},
            )

    write_json(
        document["player_status_uri"], {"schema_version": "1", "players": statuses}
    )
    engine_config = wasmtime.Config()
    engine_config.consume_fuel = True
    engine_config.epoch_interruption = True
    engine = wasmtime.Engine(engine_config)

    def epochs():
        while not epoch_stop.wait(0.01):
            engine.increment_epoch()

    ticker = threading.Thread(target=epochs, daemon=True)
    ticker.start()
    modules = {}
    compiled = []
    process = None
    threads = []
    exit_code = 1
    try:
        # Verify all seat files before opening the game lobby; compile shared hashes once.
        for seat in seats:
            try:
                key = seat["content_hash"]
                if key not in modules:
                    modules[key] = wasmtime.Module(engine, verified_policy(seat))
                else:
                    verified_policy(seat)
                compiled.append(modules[key])
            except Exception as error:  # noqa: BLE001 - attribute every guest failure to its seat
                errors.put(
                    (
                        seat["slot"],
                        f"policy load failed: {type(error).__name__}: {error}",
                    )
                )
                return fail(errors, statuses, document, workdir)
        env = dict(
            os.environ,
            COGAME_CONFIG_URI=config_path.as_uri(),
            COGAME_RESULTS_URI=results_uri,
            COGAME_SAVE_REPLAY_URI=replay_uri,
            COGAME_PORT=str(args.port),
        )
        process = subprocess.Popen([args.engine, *args.engine_args], cwd=ROOT, env=env)
        deadline = time.monotonic() + args.timeout
        while True:
            if process.poll() is not None:
                raise RuntimeError(
                    f"game exited before health check: {process.returncode}"
                )
            if time.monotonic() > deadline:
                raise TimeoutError("game startup timed out")
            try:
                with urlopen(
                    f"http://127.0.0.1:{args.port}/health", timeout=1
                ) as response:
                    if response.status == 200:
                        break
            except OSError:
                time.sleep(0.1)

        def play(seat: dict, module: wasmtime.Module):
            slot = seat["slot"]
            log_path = local_path(seat["log_uri"])
            log_path.parent.mkdir(parents=True, exist_ok=True)
            policy = None
            frames = 0
            try:
                with log_path.open("w") as log:
                    policy = Policy(engine, module, slot)
                    # The engine resolves display names from the authenticated roster.
                    query = urlencode(
                        {
                            "slot": slot,
                            "token": tokens[slot],
                        }
                    )
                    with connect(
                        f"ws://127.0.0.1:{args.port}/player?{query}",
                        max_size=16 * 1024 * 1024,
                        open_timeout=30,
                        close_timeout=1,
                        compression=None,
                    ) as ws:
                        ws.send(
                            b"\x87"
                        )  # Suppress sprite pixels; retain labels and walkability.
                        status(slot, "running")
                        log.write(
                            f"WASM policy started slot={slot} hash={seat['content_hash']}\n"
                        )
                        log.flush()
                        while not stop.is_set():
                            try:
                                frame = ws.recv(timeout=0.5)
                            except TimeoutError:
                                continue
                            if not isinstance(frame, bytes):
                                raise TypeError("expected binary Sprite v1 observation")
                            for reply in policy.step(frame):
                                ws.send(reply)
                            if config.get("fastMode", False):
                                ws.send(b"\x85")
                            frames += 1
                        log.write(f"WASM policy finished frames={frames}\n")
            except ConnectionClosed as error:
                # The engine writes results before closing players at normal game over.
                if not stop.is_set() and not result_path.exists():
                    errors.put(
                        (slot, f"player connection closed before results: {error.code}")
                    )
            except Exception as error:  # noqa: BLE001 - attribute every guest failure to its seat
                message = f"{type(error).__name__}: {error}"[:1800]
                with log_path.open("a") as log:
                    log.write(message + "\n")
                errors.put((slot, message))
            finally:
                if policy is not None:
                    policy.close()
                with log_path.open("a") as log:
                    log.write(f"Processed {frames} observation frames\n")

        for seat, module in zip(seats, compiled, strict=True):
            thread = threading.Thread(
                target=play, args=(seat, module), name=f"policy-{seat['slot']}"
            )
            threads.append(thread)
            thread.start()
        while not result_path.exists():
            if not errors.empty():
                return fail(errors, statuses, document, workdir)
            if process.poll() is not None:
                raise RuntimeError(f"game exited before results: {process.returncode}")
            if time.monotonic() > deadline:
                raise TimeoutError("episode exceeded wall-time limit")
            time.sleep(0.05)
        if not errors.empty():
            return fail(errors, statuses, document, workdir)
        json.loads(result_path.read_text())
        if not local_path(replay_uri).is_file():
            raise RuntimeError("game produced results without a replay")
        exit_code = 0
    finally:
        # Keep epoch ticks alive until every policy call has returned or trapped.
        stop.set()
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        # Closing the server wakes recv; epoch interrupts bound any still-running guest.
        for thread in threads:
            thread.join(timeout=65)
        epoch_stop.set()
        ticker.join()
        for i, previous in enumerate(statuses):
            if previous["state"] == "running":
                status(i, "exited", exit_code)
        for module in modules.values():
            module.close()
        engine.close()
    if not errors.empty():
        return fail(errors, statuses, document, workdir)
    return exit_code


def fail(errors, statuses, document, workdir) -> int:
    slot, message = errors.get_nowait()
    statuses[slot] = {
        "slot": slot,
        "state": "exited",
        "exit_code": 1,
        "reason": message[:1800],
    }
    write_json(
        document["player_status_uri"], {"schema_version": "1", "players": statuses}
    )
    write_json(
        os.environ.get(
            "COGAME_PLAYER_FAILURE_URI", (workdir / "player_failure.json").as_uri()
        ),
        {"failed_policy_index": slot, "message": message[:1800]},
    )
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seats", default=os.environ.get("COGAME_PLAYER_SEATS_URI"))
    parser.add_argument("--config", default=os.environ.get("COGAME_CONFIG_URI"))
    parser.add_argument("--engine", default=str(ROOT / "singlepod/ctf"))
    parser.add_argument(
        "--port", type=int, default=int(os.environ.get("COGAME_PORT", "8080"))
    )
    parser.add_argument("--timeout", type=float, default=1800)
    args, args.engine_args = parser.parse_known_args()
    if (
        not args.seats
        and not os.environ.get("COGAME_LOAD_REPLAY_URI")
        and not any(a.startswith("--load-replay") for a in args.engine_args)
    ):
        parser.error("COGAME_PLAYER_SEATS_URI or --seats is required")

    def interrupted(signum, frame):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, interrupted)
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
