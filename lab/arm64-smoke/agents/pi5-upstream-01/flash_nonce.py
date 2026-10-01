"""Opt-in trusted-lab nonce workflow. Never executes submitted shell commands.

An unsigned manifest provides integrity/correlation, not authorization or proof
of trustworthy firmware. This queue must be restricted to trusted submitters.
"""

import hashlib
import json
import os
from pathlib import Path
import re
import stat
import tempfile
import time

import flash_hello as hardware

MAC = hardware.MAC
QUEUE = "pi5-esp32s3-workshop-nonce-01"
MARKER = "TF_ESP32S3_HELLO_V2_PASS"
FLASH_FILES = hardware.FLASH_FILES
FLASH_ARGS = hardware.FLASH_ARGS
LIMITS = {
    "bootloader/bootloader.bin": 0x8000,
    "partition_table/partition-table.bin": 0x1000,
    "tf_s3_hello.bin": 0x100000,
    "flasher_args.json": 16384,
    "flash_args": 4096,
    "manifest.json": 65536,
}
CONFIRM = re.compile(r"CONFIRM_FLASH " + re.escape(MAC) + r" ([0-9a-f]{32}) ([0-9a-f]{64})")


def validate_job(job):
    if not isinstance(job, dict) or job.get("job_queue") != QUEUE:
        raise ValueError("Wrong nonce queue")
    data = job.get("test_data")
    command = data.get("test_cmds") if isinstance(data, dict) else None
    match = CONFIRM.fullmatch(command) if isinstance(command, str) else None
    if not match:
        raise ValueError("Require CONFIRM_FLASH with configured MAC, nonce and manifest SHA-256")
    return match[1], match[2]


def read_file(root, name):
    """Read only fixed, bounded, regular files, rejecting symlink components."""
    if name not in LIMITS:
        raise ValueError("Unexpected artifact path")
    root = root.absolute()
    path = root / name
    for component in (path, *path.parents):
        if component.is_symlink():
            raise ValueError(f"Symlink artifact path: {name}")
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= LIMITS[name]:
            raise ValueError(f"Invalid artifact size/type: {name}")
        data = stream.read(LIMITS[name] + 1)
    if not 0 < len(data) <= LIMITS[name]:
        raise ValueError(f"Invalid artifact size: {name}")
    return data


def parse_json(data):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"Duplicate JSON key: {key}")
            result[key] = value
        return result

    result = json.loads(data, object_pairs_hook=unique)
    if not isinstance(result, dict):
        raise ValueError("Expected a JSON object")
    return result


def validate_bundle(root, nonce, manifest_hash):
    """Return captured verified bytes; later flashing uses a private copy."""
    raw = read_file(root, "manifest.json")
    if hashlib.sha256(raw).hexdigest() != manifest_hash:
        raise ValueError("Manifest hash differs from job confirmation")
    manifest = parse_json(raw)
    if (type(manifest.get("schema_version")) is not int or manifest["schema_version"] != 1
            or manifest.get("target") != "esp32s3"
            or manifest.get("project") != "tf_s3_hello"
            or manifest.get("project_version") != "1.0.0"
            or manifest.get("sdk") != {"name": "freertos-esp-idf", "version": "5.5.3"}
            or manifest.get("serial_marker") != MARKER
            or not re.fullmatch(r"[0-9a-f]{32}", nonce)
            or manifest.get("nonce") != nonce):
        raise ValueError("Unexpected manifest schema, target, SDK or nonce")
    source = manifest.get("source")
    if (not isinstance(source, dict) or source.get("git_metadata") != "host-reported"
            or not isinstance(source.get("commit"), str)
            or not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", source["commit"])
            or type(source.get("dirty")) is not bool):
        raise ValueError("Host Git provenance required; build with the host launcher")
    entries = manifest.get("artifacts")
    if not isinstance(entries, list) or len(entries) != 5:
        raise ValueError("Exactly five artifacts required")
    offsets = {name: offset for offset, name in FLASH_FILES.items()}
    captured = {"manifest.json": raw}
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("Invalid artifact entry")
        name = entry.get("path")
        if not isinstance(name, str) or name not in LIMITS or name in captured:
            raise ValueError("Unexpected or duplicate artifact path")
        expected_keys = {"path", "size", "sha256"} | ({"offset"} if name in offsets else set())
        if set(entry) != expected_keys or entry.get("offset") != offsets.get(name):
            raise ValueError("Unexpected artifact fields or flash offset")
        if (type(entry.get("size")) is not int or not 0 < entry["size"] <= LIMITS[name]
                or not isinstance(entry.get("sha256"), str)
                or not re.fullmatch(r"[0-9a-f]{64}", entry["sha256"])):
            raise ValueError("Invalid artifact size or SHA-256")
        data = read_file(root, name)
        if len(data) != entry["size"] or hashlib.sha256(data).hexdigest() != entry["sha256"]:
            raise ValueError(f"Artifact size/hash mismatch: {name}")
        captured[name] = data
    metadata = parse_json(captured["flasher_args.json"])
    if (metadata.get("flash_files") != FLASH_FILES
            or metadata.get("write_flash_args") != FLASH_ARGS
            or metadata.get("flash_settings") != {
                "flash_mode": "dio", "flash_size": "4MB", "flash_freq": "40m"}
            or not isinstance(metadata.get("extra_esptool_args"), dict)
            or metadata["extra_esptool_args"].get("chip") != "esp32s3"):
        raise ValueError("Unexpected flash layout/settings")
    # Do not accept a submitted partition table that moves or enlarges the app.
    partition = "partition_table/partition-table.bin"
    if hashlib.sha256(captured[partition]).hexdigest() != hardware.HASHES[partition]:
        raise ValueError("Partition table differs from the fixed lab layout")
    for name in ("bootloader/bootloader.bin", "tf_s3_hello.bin"):
        data = captured[name]
        # ESP image extended header: magic 0xe9, little-endian chip ID 9 (S3).
        if len(data) < 24 or data[0] != 0xE9 or int.from_bytes(data[12:14], "little") != 9:
            raise ValueError(f"Not an ESP32-S3 image: {name}")
    app = captured["tf_s3_hello.bin"]
    if nonce.encode() + b"\0" not in app or MARKER.encode() not in app:
        raise ValueError("Application nonce/marker mismatch")
    # flash_args is inventoried but never executed or passed to esptool.
    return manifest, captured


class SerialProof:
    def __init__(self, nonce):
        self.pattern = re.compile(
            r"^" + MARKER + r" mac=" + re.escape(MAC)
            + r" nonce=" + re.escape(nonce) + r" seq=([0-9]{1,10})$")
        self.sequences = []

    def feed(self, line):
        match = self.pattern.fullmatch(line)
        if not match or int(match[1]) > 0xFFFFFFFF:
            if line.startswith("TF_ESP32S3_HELLO_"):
                self.sequences.clear()
            return False
        sequence = int(match[1])
        if self.sequences and sequence <= self.sequences[-1]:
            self.sequences.clear()
        self.sequences.append(sequence)
        return len(self.sequences) >= 3


def capture_serial(log, nonce, timeout=45):
    import serial

    deadline = time.monotonic() + timeout
    proof = SerialProof(nonce)
    pending = b""
    with log.open("wb") as stream:
        while time.monotonic() < deadline:
            try:
                with hardware.open_serial() as port:
                    while time.monotonic() < deadline:
                        data = port.read(512)
                        if not data:
                            continue
                        stream.write(data)
                        stream.flush()
                        pending += data
                        while b"\n" in pending:
                            line, pending = pending.split(b"\n", 1)
                            text = line.decode("utf-8", errors="replace").strip()
                            print(text, flush=True)
                            if proof.feed(text):
                                return proof.sequences
                        pending = pending[-4096:]
            except (serial.SerialException, OSError) as error:
                print(f"Serial reconnect: {error}", flush=True)
                pending = b""
                proof = SerialProof(nonce)
                time.sleep(0.5)
    raise TimeoutError("No three increasing serial markers matching the configured MAC and build nonce")


def run_workflow(job, root, artifacts):
    """Caller checks the execution environment; preflight precedes any device IO."""
    artifacts.mkdir(parents=True, exist_ok=True)
    stage = "preflight"
    result = {"status": "fail", "mac": MAC}
    try:
        nonce, manifest_hash = validate_job(job)
        result.update(nonce=nonce, manifest_sha256=manifest_hash)
        manifest, captured = validate_bundle(root, nonce, manifest_hash)
        (artifacts / "manifest.json").write_bytes(captured["manifest.json"])
        result["source"] = manifest["source"]
        with tempfile.TemporaryDirectory(prefix="tf-nonce-") as directory:
            private = Path(directory)
            args = []
            for offset, name in sorted(FLASH_FILES.items(), key=lambda item: int(item[0], 16)):
                path = private / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(captured[name])
                args.extend((offset, str(path)))
            stage = "identity"
            hardware.validate_identity(hardware.run_tool(["read_mac"], artifacts / "identity.log", 60))
            stage = "flash"
            hardware.run_tool(["write_flash", "--no-progress", *FLASH_ARGS, *args],
                              artifacts / "flash.log", 180)
            stage = "verify"
            hardware.run_tool(["verify_flash", *FLASH_ARGS, *args], artifacts / "verify.log", 180)
            stage = "reset"
            hardware.reset_to_app()
            stage = "serial"
            result["sequences"] = capture_serial(artifacts / "serial.log", nonce)
        result["status"] = "pass"
        print("ESP32S3_WORKSHOP_NONCE_PASS", flush=True)
        return 0
    except Exception as error:
        result.update(stage=stage, error=str(error))
        print(f"FAILED at {stage}: {error}; no automatic flash retry", flush=True)
        return 1
    finally:
        (artifacts / "result.json").write_text(json.dumps(result, indent=2) + "\n")


def main():
    if os.getuid() != 1000 or not Path("/.dockerenv").exists():
        raise RuntimeError("Run only as ubuntu in the designated test container")
    try:
        job = parse_json(Path("testflinger.json").read_bytes())
    except Exception as error:
        artifacts = Path("artifacts")
        artifacts.mkdir(exist_ok=True)
        (artifacts / "result.json").write_text(json.dumps({
            "status": "fail", "stage": "preflight", "error": str(error)
        }, indent=2) + "\n")
        print(f"Invalid job: {error}; no device access", flush=True)
        return 1
    return run_workflow(job, Path("attachments/test"), Path("artifacts"))


if __name__ == "__main__":
    raise SystemExit(main())
