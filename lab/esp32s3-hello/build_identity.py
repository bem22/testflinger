"""Build identity and unsigned artifact inventory; not a hardware authorization."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
from datetime import datetime, timezone


FLASH_FILES = {
    "0x0": "bootloader/bootloader.bin",
    "0x8000": "partition_table/partition-table.bin",
    "0x10000": "tf_s3_hello.bin",
}
ARTIFACTS = (*FLASH_FILES.values(), "flasher_args.json", "flash_args")
MARKER = "TF_ESP32S3_HELLO_V2_PASS"
INPUT_FILES = (
    "CMakeLists.txt", "sdkconfig.defaults", "workshop.yaml",
    "build-workshop.sh", "build-workshop-local.sh", "build_identity.py",
)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_inventory(project):
    paths = [project / name for name in INPUT_FILES]
    for directory in ("main", ".workshop"):
        paths.extend(p for p in (project / directory).rglob("*") if p.is_file())
    return {p.relative_to(project).as_posix(): digest(p) for p in sorted(paths)}


def write_json(path, value):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def prepare(project, build):
    commit = os.environ.get("TF_SOURCE_COMMIT")
    dirty = os.environ.get("TF_SOURCE_DIRTY")
    if commit is not None and not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", commit):
        raise ValueError("TF_SOURCE_COMMIT must be a full Git object ID")
    if (commit is None) != (dirty is None) or dirty not in (None, "true", "false"):
        raise ValueError("Provide both TF_SOURCE_COMMIT and TF_SOURCE_DIRTY=true/false")
    identity = build / "identity"
    identity.mkdir(parents=True, exist_ok=True)
    # Invalidate a previous successful build even when called outside the shell.
    (build / "manifest.json").unlink(missing_ok=True)
    nonce = secrets.token_hex(16)
    state = {
        "nonce": nonce,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "source": {
            "commit": commit,
            "dirty": None if dirty is None else dirty == "true",
            "git_metadata": "host-reported" if commit else "unavailable",
            "files_sha256": source_inventory(project),
        },
    }
    (identity / "tf_build_identity.h").write_text(
        f'#pragma once\n#define TF_BUILD_NONCE "{nonce}"\n'
    )
    write_json(identity / "build.json", state)
    print(f"Build nonce: {nonce}")
    if commit is None:
        print("Git metadata unavailable: use bash build-workshop-local.sh on the host")
    return state


def finalize(project, build):
    manifest_path = build / "manifest.json"
    manifest_path.unlink(missing_ok=True)
    state = json.loads((build / "identity/build.json").read_text())
    nonce = state["nonce"]
    if not isinstance(nonce, str) or not re.fullmatch(r"[0-9a-f]{32}", nonce):
        raise ValueError("Invalid build nonce")
    if source_inventory(project) != state["source"]["files_sha256"]:
        raise ValueError("Source files changed during the build; rebuild before submission")
    metadata = json.loads((build / "project_description.json").read_text())
    if metadata["target"] != "esp32s3" or metadata["project_name"] != "tf_s3_hello":
        raise ValueError("Unexpected firmware project or target")
    if (build / "idf-version.txt").read_text().strip() != "ESP-IDF v5.5.3":
        raise ValueError("Unexpected ESP-IDF version")
    flash = json.loads((build / "flasher_args.json").read_text())
    if flash["flash_files"] != FLASH_FILES or flash["extra_esptool_args"]["chip"] != "esp32s3":
        raise ValueError("Unexpected flash mapping or chip")
    binary = (build / "tf_s3_hello.bin").read_bytes()
    if nonce.encode() + b"\0" not in binary or MARKER.encode() not in binary:
        raise ValueError("Firmware does not contain the expected build nonce and marker")
    artifacts = []
    for name in ARTIFACTS:
        path = build / name
        size = path.stat().st_size
        if not size:
            raise ValueError(f"Empty artifact: {name}")
        artifact = {"path": name, "size": size, "sha256": digest(path)}
        for offset, filename in FLASH_FILES.items():
            if filename == name:
                artifact["offset"] = offset
        artifacts.append(artifact)
    manifest = {
        "schema_version": 1,
        "nonce": nonce,
        "serial_marker": MARKER,
        "target": "esp32s3",
        "project": metadata["project_name"],
        "project_version": metadata["project_version"],
        "sdk": {"name": "freertos-esp-idf", "version": "5.5.3"},
        "started_at": state["started_at"],
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "source": state["source"],
        "artifacts": artifacts,
    }
    # Publication is last: consumers must require this file, not just .bin files.
    write_json(manifest_path, manifest)
    print(f"Build manifest: {manifest_path}")
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "finalize"))
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--build", type=Path, required=True)
    args = parser.parse_args()
    {"prepare": prepare, "finalize": finalize}[args.action](args.project, args.build)


if __name__ == "__main__":
    main()
