import hashlib
import json
import struct
from pathlib import Path

import pytest
import wasmtime
from runtime import Policy, decode_replies, load_seats, local_path, verified_policy


@pytest.fixture
def engine():
    config = wasmtime.Config()
    config.consume_fuel = True
    config.epoch_interruption = True
    value = wasmtime.Engine(config)
    yield value
    value.close()


def module_bytes(step="i32.const 0", buffer="i32.const 1024", size=4):
    return wasmtime.wat2wasm(f"""(module
      (memory (export "memory") 1)
      (func (export "paintbot_init") (param i32))
      (func (export "paintbot_buffer") (param i32) (result i32) {buffer})
      (func (export "paintbot_step") (result i32) {step})
      (func (export "paintbot_output_size") (result i32) i32.const {size}))""")


def test_baseline_is_real_wasi_reactor(engine):
    with wasmtime.Module.from_file(
        engine, str(Path(__file__).with_name("baseline.wasm"))
    ) as module:
        assert all(i.module == "wasi_snapshot_preview1" for i in module.imports)
        policy = Policy(engine, module, 0)
        try:
            assert policy.step(b"") == []
        finally:
            policy.close()


@pytest.mark.parametrize(
    "buffer,size",
    [("i32.const -1", 4), ("i32.const 65535", 4), ("i32.const 0", 100000)],
)
def test_invalid_guest_buffers_fail(engine, buffer, size):
    with wasmtime.Module(engine, module_bytes(buffer=buffer, size=size)) as module:
        policy = Policy(engine, module, 0)
        try:
            with pytest.raises(ValueError):
                policy.step(b"0123")
        finally:
            policy.close()


def test_infinite_guest_exhausts_fuel(engine):
    with wasmtime.Module(
        engine, module_bytes(step="(loop $forever br $forever) i32.const 0")
    ) as module:
        policy = Policy(engine, module, 0)
        try:
            # Invoke directly with a small budget to keep the regression test quick.
            policy.store.set_fuel(1000)
            with pytest.raises(wasmtime.Trap, match="fuel"):
                policy.exports["paintbot_step"](policy.store)
        finally:
            policy.close()


def test_guest_memory_limit(engine):
    with wasmtime.Module(
        engine, module_bytes(step="i32.const 5000 memory.grow")
    ) as module:
        policy = Policy(engine, module, 0)
        try:
            with pytest.raises(ValueError, match="out-of-bounds"):
                policy.step(b"")
        finally:
            policy.close()


def test_instances_do_not_share_memory(engine):
    with wasmtime.Module(engine, module_bytes()) as module:
        a, b = Policy(engine, module, 0), Policy(engine, module, 1)
        try:
            a.memory.write(a.store, b"secret", 500)
            assert bytes(b.memory.read(b.store, 500, 506)) == b"\0" * 6
        finally:
            a.close()
            b.close()


def test_no_network_import(engine):
    data = wasmtime.wat2wasm('(module (import "env" "connect" (func)))')
    with (
        wasmtime.Module(engine, data) as module,
        pytest.raises(wasmtime.WasmtimeError, match="unknown import"),
    ):
        Policy(engine, module, 0)


def test_replies_preserve_mask_and_chat():
    replies = [b"\x84\x10", b"\x81\x02\x00hi"]
    packed = struct.pack("<I", len(replies)) + b"".join(
        struct.pack("<I", len(r)) + r for r in replies
    )
    assert decode_replies(packed) == replies


@pytest.mark.parametrize(
    "data",
    [
        b"",
        struct.pack("<I", 65),
        struct.pack("<II", 1, 4),
        struct.pack("<III", 0, 0, 0),
        struct.pack("<II", 1, 1) + b"\x87",
    ],
)
def test_malformed_replies_rejected(data):
    with pytest.raises(ValueError):
        decode_replies(data)


def test_policy_hash_and_size(tmp_path):
    path = tmp_path / "player.wasm"
    path.write_bytes(b"original")
    seat = {
        "slot": 0,
        "file_uri": path.as_uri(),
        "size_bytes": 8,
        "content_hash": "sha256:" + hashlib.sha256(b"original").hexdigest(),
    }
    assert verified_policy(seat) == b"original"
    path.write_bytes(b"modified")
    with pytest.raises(ValueError, match="mismatch"):
        verified_policy(seat)


def test_sparse_seats_rejected(tmp_path):
    path = tmp_path / "seats.json"
    path.write_text(
        json.dumps({"schema": "coworld-player-seats/1", "seats": [{"slot": 1}]})
    )
    with pytest.raises(ValueError, match="contiguous"):
        load_seats(str(path))


def test_local_file_uri_rejects_remote_authority():
    with pytest.raises(ValueError):
        local_path("file://remote/etc/passwd")


def test_https_hash_verification(tmp_path, monkeypatch):
    import runtime

    data = b"downloaded policy"
    monkeypatch.setattr(
        runtime, "urlopen", lambda *args, **kwargs: __import__("io").BytesIO(data)
    )
    assert (
        verified_policy(
            {
                "slot": 0,
                "file_uri": "https://example.com/player.wasm",
                "size_bytes": len(data),
                "content_hash": "sha256:" + hashlib.sha256(data).hexdigest(),
            }
        )
        == data
    )


def test_s3_uses_standard_credential_chain(monkeypatch):
    import io

    import boto3
    import runtime

    calls = []

    class S3:
        def get_object(self, **kwargs):
            calls.append(kwargs)
            return {"Body": io.BytesIO(b"wasm")}

        def close(self):
            pass

    monkeypatch.setattr(boto3, "client", lambda name, **kwargs: S3())
    assert runtime.read_uri("s3://bucket/policy%20one.wasm") == b"wasm"
    assert calls == [{"Bucket": "bucket", "Key": "policy one.wasm"}]


def test_bad_file_reports_seat_before_launch(tmp_path):
    import subprocess
    import sys

    data = b"corrupted wasm"
    policy = tmp_path / "policy.wasm"
    policy.write_bytes(data)
    document = {
        "schema": "coworld-player-seats/1",
        "seats": [
            {
                "slot": 0,
                "file_uri": policy.as_uri(),
                "size_bytes": len(data),
                "content_hash": "sha256:" + "0" * 64,
                "log_uri": (tmp_path / "seat.log").as_uri(),
                "artifact_uri": (tmp_path / "artifact.zip").as_uri(),
            }
        ],
        "player_status_uri": (tmp_path / "player_status.json").as_uri(),
    }
    seats = tmp_path / "seats.json"
    seats.write_text(json.dumps(document))
    result = subprocess.run(
        [
            sys.executable,
            str(Path(__file__).with_name("host.py")),
            "--seats",
            str(seats),
            "--engine",
            "/nonexistent-engine",
        ],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert result.returncode == 1
    failure = json.loads((tmp_path / "player_failure.json").read_text())
    assert failure["failed_policy_index"] == 0
    assert "mismatch" in failure["message"]
    assert not (tmp_path / "results.json").exists()
    assert (
        json.loads((tmp_path / "player_status.json").read_text())["players"][0][
            "exit_code"
        ]
        == 1
    )
