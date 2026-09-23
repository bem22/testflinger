"""Fixed lab flash workflow: validated firmware, exact board, no write retries."""

import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

MAC = "e8:f6:0a:81:84:84"
QUEUE = "pi5-esp32s3-flash-hello-01"
PORT = "/dev/esp32s3"
FLASH_FILES = {
    "0x0": "bootloader/bootloader.bin",
    "0x8000": "partition_table/partition-table.bin",
    "0x10000": "tf_s3_hello.bin",
}
HASHES = {
    "bootloader/bootloader.bin": "54c6a1adcc051dade8ec13d606a0e694822bfcc27f3e874ce130953fd293b444",
    "partition_table/partition-table.bin": "7f00b6c042a89b15b0cac534f82ed988caf29278ff5700b0c511eb1b5bb7c820",
    "tf_s3_hello.bin": "fd0103dc39b517200b83ac294d5289d7bef98f9b227d8fdf7359290d0a7adfbb",
}
FLASH_ARGS = ["--flash_mode", "dio", "--flash_size", "4MB", "--flash_freq", "40m"]
MARKER = re.compile(r"^TF_ESP32S3_HELLO_V1_PASS mac=" + re.escape(MAC) + r" seq=(\d+)$")


def validate_job(job: dict) -> None:
    if job.get("job_queue") != QUEUE or job.get("test_data", {}).get("test_cmds") != f"CONFIRM_FLASH {MAC}":
        raise ValueError("Wrong queue or missing explicit CONFIRM_FLASH MAC")


def validate_bundle(root: Path) -> list[str]:
    """Allow only the previously built images and generated mapping."""
    root = root.resolve(strict=True)
    metadata = json.loads((root / "flasher_args.json").read_text())
    if metadata.get("flash_files") != FLASH_FILES or metadata.get("write_flash_args") != FLASH_ARGS:
        raise ValueError("Firmware flash layout/settings differ from the validated build")
    if metadata.get("extra_esptool_args", {}).get("chip") != "esp32s3":
        raise ValueError("Firmware is not for ESP32-S3")
    args = []
    for offset, name in sorted(FLASH_FILES.items(), key=lambda pair: int(pair[0], 16)):
        path = (root / name).resolve(strict=True)
        if not path.is_relative_to(root) or not path.is_file():
            raise ValueError(f"Unsafe firmware path: {name}")
        if path.stat().st_size > 4 * 1024 * 1024:
            raise ValueError(f"Oversized firmware: {name}")
        if hashlib.sha256(path.read_bytes()).hexdigest() != HASHES[name]:
            raise ValueError(f"Firmware hash mismatch: {name}")
        args.extend([offset, str(path)])
    return args


def validate_identity(output: str) -> None:
    if not re.search(r"^Chip is ESP32-S3(?:\s|$)", output, re.MULTILINE):
        raise ValueError("Unexpected chip identity")
    if not re.search(r"^MAC: " + re.escape(MAC) + r"\s*$", output, re.MULTILINE):
        raise ValueError("Unexpected target MAC; refusing to flash")


def run_tool(args: list[str], log: Path, timeout: int) -> str:
    command = [sys.executable, "-m", "esptool", "--chip", "esp32s3",
               "--port", PORT, "--baud", "115200", "--before", "usb_reset",
               "--after", "no_reset", "--no-stub", *args]
    print("Running:", " ".join(command), flush=True)
    # Log directly to disk, including output produced before failure/timeout.
    with log.open("w") as stream:
        result = subprocess.run(command, stdout=stream, stderr=subprocess.STDOUT,
                                timeout=timeout, check=False)
    output = log.read_text(errors="replace")
    print(output, flush=True)
    if result.returncode:
        raise RuntimeError(f"esptool failed ({result.returncode}); see {log.name}")
    return output


def open_serial():
    import serial

    port = serial.Serial(port=None, baudrate=115200, timeout=1, write_timeout=1, exclusive=True)
    port.dtr = False
    port.rts = False
    port.port = PORT
    port.open()
    return port


def reset_to_app() -> None:
    # Explicit USB timing avoids PID autodetection through the guest device alias.
    from esptool.reset import HardReset

    with open_serial() as port:
        HardReset(port, uses_usb=True)()


def capture_serial(log: Path, timeout: float = 45) -> None:
    """Require three increasing counters from this board; reconnect, never reflash."""
    import serial

    deadline = time.monotonic() + timeout
    previous = None
    count = 0
    pending = b""
    with log.open("wb") as stream:
        while time.monotonic() < deadline:
            try:
                with open_serial() as port:
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
                            match = MARKER.fullmatch(text)
                            if match:
                                sequence = int(match[1])
                                count = count + 1 if previous is not None and sequence > previous else 1
                                previous = sequence
                                if count >= 3:
                                    return
                        pending = pending[-4096:]
            except (serial.SerialException, OSError) as error:
                print(f"Serial reconnect: {error}", flush=True)
                pending = b""
                previous = None
                count = 0
                time.sleep(0.5)
    raise TimeoutError("No three increasing hello markers; inspect serial.log and device mapping")


def main() -> int:
    artifacts = Path("artifacts")
    artifacts.mkdir(exist_ok=True)
    stage = "preflight"
    try:
        if os.getuid() != 1000 or not Path("/.dockerenv").exists():
            raise RuntimeError("Run only as ubuntu in the designated test container")
        validate_job(json.loads(Path("testflinger.json").read_text()))
        flash_files = validate_bundle(Path("attachments"))
        (artifacts / "firmware-hashes.json").write_text(json.dumps(HASHES, indent=2) + "\n")
        stage = "identity"
        validate_identity(run_tool(["read_mac"], artifacts / "identity.log", 60))
        stage = "flash"
        run_tool(["write_flash", "--no-progress", *FLASH_ARGS, *flash_files],
                 artifacts / "flash.log", 180)
        stage = "verify"
        run_tool(["verify_flash", *FLASH_ARGS, *flash_files], artifacts / "verify.log", 180)
        stage = "reset"
        reset_to_app()
        stage = "serial"
        capture_serial(artifacts / "serial.log")
        (artifacts / "result.json").write_text(json.dumps({"status": "pass", "mac": MAC}) + "\n")
        print("ESP32S3_FLASH_HELLO_PASS", flush=True)
        return 0
    except Exception as error:
        (artifacts / "result.json").write_text(json.dumps(
            {"status": "fail", "stage": stage, "error": str(error)}, indent=2) + "\n")
        print(f"FAILED at {stage}: {error}; no automatic flash retry", flush=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())