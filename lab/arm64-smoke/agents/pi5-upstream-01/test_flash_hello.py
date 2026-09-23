"""Offline guards and sequencing tests. Never opens a physical device."""

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import flash_hello as hello

BUILD = Path(__file__).resolve().parents[3] / "esp32s3-hello" / "build"


class FlashTests(unittest.TestCase):
    def test_exact_confirmation(self):
        hello.validate_job({"job_queue": hello.QUEUE,
                            "test_data": {"test_cmds": f"CONFIRM_FLASH {hello.MAC}"}})
        for job in ({}, {"job_queue": hello.QUEUE},
                    {"job_queue": "pi5-esp32s3-identity-01"},
                    {"job_queue": hello.QUEUE, "test_data": {"test_cmds": "echo hello"}}):
            with self.assertRaises(ValueError):
                hello.validate_job(job)

    def test_identity(self):
        good = f"Chip is ESP32-S3 (QFN56) (revision v0.2)\nMAC: {hello.MAC}\n"
        hello.validate_identity(good)
        for output in ("", good.replace("ESP32-S3", "ESP32-C3"),
                       good.replace(hello.MAC, "ac:a7:04:bc:d2:cc")):
            with self.assertRaises(ValueError):
                hello.validate_identity(output)

    @unittest.skipUnless((BUILD / "flasher_args.json").exists(), "Local build needed")
    def test_real_bundle(self):
        args = hello.validate_bundle(BUILD)
        self.assertEqual(args[::2], ["0x0", "0x8000", "0x10000"])

    def test_bad_layout_and_hash(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            metadata = {"flash_files": hello.FLASH_FILES,
                        "write_flash_args": hello.FLASH_ARGS,
                        "extra_esptool_args": {"chip": "esp32s3"}}
            for name in hello.HASHES:
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"not firmware")
            (root / "flasher_args.json").write_text(json.dumps(metadata))
            with self.assertRaisesRegex(ValueError, "hash mismatch"):
                hello.validate_bundle(root)
            metadata["flash_files"] = {"0x0": "other.bin"}
            (root / "flasher_args.json").write_text(json.dumps(metadata))
            with self.assertRaisesRegex(ValueError, "layout/settings"):
                hello.validate_bundle(root)

    def run_mocked_main(self, fail_stage=None):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original_path = Path

            def isolated_path(name):
                return original_path("/.dockerenv") if name == "/.dockerenv" else root / name

            (root / "testflinger.json").write_text(json.dumps({
                "job_queue": hello.QUEUE,
                "test_data": {"test_cmds": f"CONFIRM_FLASH {hello.MAC}"}}))
            events = []

            def tool(args, log, timeout):
                events.append(args[0])
                if args[0] == fail_stage:
                    raise RuntimeError("injected tool failure")
                return f"Chip is ESP32-S3 (QFN56)\nMAC: {hello.MAC}\n"

            with patch.object(hello, "Path", side_effect=isolated_path), \
                 patch.object(Path, "exists", return_value=True), \
                 patch.object(hello.os, "getuid", return_value=1000), \
                 patch.object(hello, "validate_bundle", return_value=["0x0", "fake.bin"]), \
                 patch.object(hello, "run_tool", side_effect=tool), \
                 patch.object(hello, "reset_to_app", side_effect=lambda: events.append("reset")), \
                 patch.object(hello, "capture_serial", side_effect=lambda log: events.append("serial")):
                code = hello.main()
            result = json.loads((root / "artifacts/result.json").read_text())
            return code, events, result

    def test_success_sequence(self):
        code, events, result = self.run_mocked_main()
        self.assertEqual(code, 0)
        self.assertEqual(events, ["read_mac", "write_flash", "verify_flash", "reset", "serial"])
        self.assertEqual(result["status"], "pass")

    def test_failures_never_retry_flash(self):
        for stage, expected in (("read_mac", ["read_mac"]),
                                ("write_flash", ["read_mac", "write_flash"]),
                                ("verify_flash", ["read_mac", "write_flash", "verify_flash"])):
            code, events, result = self.run_mocked_main(stage)
            self.assertEqual(code, 1)
            self.assertEqual(events, expected)
            self.assertEqual(result["status"], "fail")

    def test_serial_parser(self):
        import serial

        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "serial.log"
            reads = [b"boot\n", f"TF_ESP32S3_HELLO_V1_PASS mac={hello.MAC} seq=".encode(),
                     b"7\n", f"TF_ESP32S3_HELLO_V1_PASS mac={hello.MAC} seq=8\n".encode(),
                     f"TF_ESP32S3_HELLO_V1_PASS mac={hello.MAC} seq=9\n".encode()]
            with patch.object(hello, "open_serial") as opened:
                opened.return_value.__enter__.return_value.read.side_effect = reads
                hello.capture_serial(log, timeout=2)
            self.assertIn(b"seq=9", log.read_bytes())
            with patch.object(hello, "open_serial", side_effect=serial.SerialException("absent")), \
                  patch.object(hello.time, "sleep"), \
                  patch.object(hello.time, "monotonic", side_effect=[0, 0, 1]):
                with self.assertRaises(TimeoutError):
                    hello.capture_serial(log, timeout=0.01)


if __name__ == "__main__":
    unittest.main()