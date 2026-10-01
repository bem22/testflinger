"""Offline nonce runner tests. All physical-device IO is mocked."""

import ast
import hashlib
import json
import os
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch

import flash_nonce as runner

NONCE = "a" * 32
BUILD = Path(__file__).resolve().parents[3] / "esp32s3-hello/build/workshop"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def image(payload=b""):
    header = bytearray(24)
    header[0] = 0xE9
    header[12] = 9
    return bytes(header) + payload


class NonceTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.root = self.base / "test"
        self.root.mkdir()
        metadata = {
            "flash_files": runner.FLASH_FILES, "write_flash_args": runner.FLASH_ARGS,
            "flash_settings": {"flash_mode": "dio", "flash_size": "4MB", "flash_freq": "40m"},
            "extra_esptool_args": {"chip": "esp32s3"},
        }
        self.files = {
            "bootloader/bootloader.bin": image(b"boot"),
            "partition_table/partition-table.bin": b"fixed test partition",
            "tf_s3_hello.bin": image(runner.MARKER.encode() + b"\0" + NONCE.encode() + b"\0"),
            "flasher_args.json": json.dumps(metadata).encode(),
            "flash_args": b"not executed",
        }
        offsets = {name: offset for offset, name in runner.FLASH_FILES.items()}
        self.manifest = {
            "schema_version": 1, "nonce": NONCE, "target": "esp32s3",
            "project": "tf_s3_hello", "project_version": "1.0.0", "serial_marker": runner.MARKER,
            "sdk": {"name": "freertos-esp-idf", "version": "5.5.3"},
            "source": {"commit": "b" * 40, "dirty": True, "git_metadata": "host-reported"},
            "artifacts": [],
        }
        for name, data in self.files.items():
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            entry = {"path": name, "size": len(data), "sha256": sha(data)}
            if name in offsets:
                entry["offset"] = offsets[name]
            self.manifest["artifacts"].append(entry)
        # Only synthetic fixture tests replace this constant. The real-bundle
        # test below uses the actual fixed lab partition hash.
        patched = patch.dict(runner.hardware.HASHES, {
            "partition_table/partition-table.bin": sha(self.files["partition_table/partition-table.bin"])
        })
        patched.start()
        self.addCleanup(patched.stop)
        self.save_manifest()

    def save_manifest(self):
        raw = json.dumps(self.manifest).encode()
        (self.root / "manifest.json").write_bytes(raw)
        self.hash = sha(raw)
        self.job = {"job_queue": runner.QUEUE, "test_data": {
            "test_cmds": f"CONFIRM_FLASH {runner.MAC} {NONCE} {self.hash}"}}

    def validate(self):
        return runner.validate_bundle(self.root, NONCE, self.hash)

    def test_valid_bundle(self):
        manifest, files = self.validate()
        self.assertEqual(manifest["nonce"], NONCE)
        self.assertEqual(len(files), 6)

    def test_exact_confirmation(self):
        self.assertEqual(runner.validate_job(self.job), (NONCE, self.hash))
        for job in ({}, {"job_queue": runner.hardware.QUEUE},
                    {"job_queue": runner.QUEUE, "test_data": {"test_cmds": "echo owned"}},
                    {"job_queue": runner.QUEUE, "test_data": None},
                    {"job_queue": runner.QUEUE, "test_data": {"test_cmds": f"CONFIRM_FLASH {runner.MAC}"}}):
            with self.subTest(job=job), self.assertRaises(ValueError):
                runner.validate_job(job)

    def test_manifest_and_artifact_tamper(self):
        with self.assertRaisesRegex(ValueError, "Manifest hash"):
            runner.validate_bundle(self.root, NONCE, "0" * 64)
        (self.root / "tf_s3_hello.bin").write_bytes(b"tamper")
        with self.assertRaisesRegex(ValueError, "size/hash mismatch"):
            self.validate()

    def test_wrong_nonce_and_target(self):
        for key, value in (("nonce", "c" * 32), ("target", "esp32"), ("schema_version", True)):
            original = self.manifest[key]
            self.manifest[key] = value
            self.save_manifest()
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.validate()
            self.manifest[key] = original

    def test_unavailable_provenance(self):
        self.manifest["source"] = {"commit": None, "dirty": None}
        self.save_manifest()
        with self.assertRaisesRegex(ValueError, "provenance"):
            self.validate()

    def test_unsafe_duplicate_offsets_and_sizes(self):
        entries = self.manifest["artifacts"]
        original = dict(entries[0])
        cases = ({"path": "../../outside"}, {"path": "/tmp/firmware"},
                 {"path": "tf_s3_hello.bin", "offset": "0x10000"},
                 {"offset": "0x1000"}, {"size": True}, {"size": 0x8001})
        for changes in cases:
            entries[0] = original | changes
            self.save_manifest()
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.validate()

    def test_symlink_and_fifo_rejected(self):
        path = self.root / "flash_args"
        path.unlink()
        outside = self.base / "outside"
        outside.write_bytes(self.files["flash_args"])
        path.symlink_to(outside)
        with self.assertRaisesRegex(ValueError, "Symlink"):
            self.validate()
        path.unlink()
        os.mkfifo(path)
        with self.assertRaisesRegex(ValueError, "size/type"):
            self.validate()

    def test_duplicate_json_keys(self):
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            runner.parse_json(b'{"nonce": "a", "nonce": "b"}')

    def replace_artifact(self, name, data):
        (self.root / name).write_bytes(data)
        entry = next(e for e in self.manifest["artifacts"] if e["path"] == name)
        entry.update(size=len(data), sha256=sha(data))
        self.save_manifest()

    def test_self_consistent_wrong_layout(self):
        metadata = json.loads(self.files["flasher_args.json"])
        metadata["write_flash_args"] = ["--flash_mode", "qio"]
        self.replace_artifact("flasher_args.json", json.dumps(metadata).encode())
        with self.assertRaisesRegex(ValueError, "layout/settings"):
            self.validate()

    def test_self_consistent_wrong_partition(self):
        self.replace_artifact("partition_table/partition-table.bin", b"different partition")
        with self.assertRaisesRegex(ValueError, "Partition table"):
            self.validate()

    def test_self_consistent_wrong_image_or_nonce(self):
        self.replace_artifact("tf_s3_hello.bin", image(b"old firmware"))
        with self.assertRaisesRegex(ValueError, "nonce/marker"):
            self.validate()
        self.replace_artifact("tf_s3_hello.bin", b"not ESP" * 10)
        with self.assertRaisesRegex(ValueError, "Not an ESP32-S3"):
            self.validate()

    def workflow(self, failure=None, wrong_mac=False):
        events = []

        def tool(args, log, timeout):
            events.append(args[0])
            if args[0] == failure:
                raise RuntimeError("injected tool failure")
            if args[0] in ("write_flash", "verify_flash"):
                for name in runner.FLASH_FILES.values():
                    self.assertTrue(any(Path(arg).name == Path(name).name for arg in args))
                self.assertFalse(any(str(self.root) in arg for arg in args))
            mac = "00:00:00:00:00:00" if wrong_mac else runner.MAC
            return f"Chip is ESP32-S3 (QFN56)\nMAC: {mac}\n"

        def reset():
            events.append("reset")
            if failure == "reset":
                raise RuntimeError("injected reset failure")

        def capture(log, nonce):
            events.append("serial")
            self.assertEqual(nonce, NONCE)
            if failure == "serial":
                raise TimeoutError("wrong nonce")
            return [7, 8, 9]

        artifacts = self.base / "artifacts"
        with patch.object(runner.hardware, "run_tool", side_effect=tool), \
             patch.object(runner.hardware, "reset_to_app", side_effect=reset), \
             patch.object(runner, "capture_serial", side_effect=capture):
            code = runner.run_workflow(self.job, self.root, artifacts)
        return code, events, json.loads((artifacts / "result.json").read_text())

    def test_workflow_success(self):
        code, events, result = self.workflow()
        self.assertEqual(code, 0)
        self.assertEqual(events, ["read_mac", "write_flash", "verify_flash", "reset", "serial"])
        self.assertEqual(result["nonce"], NONCE)
        self.assertEqual(result["sequences"], [7, 8, 9])

    def test_failure_sequence_no_retries(self):
        order = ["read_mac", "write_flash", "verify_flash", "reset", "serial"]
        for index, stage in enumerate(order):
            with self.subTest(stage=stage):
                code, events, result = self.workflow(stage)
                self.assertEqual(code, 1)
                self.assertEqual(events, order[:index + 1])
                self.assertEqual(result["status"], "fail")

    def test_wrong_mac_never_writes(self):
        code, events, result = self.workflow(wrong_mac=True)
        self.assertEqual((code, events, result["stage"]), (1, ["read_mac"], "identity"))

    def test_preflight_failure_never_touches_device(self):
        (self.root / "flash_args").unlink()
        code, events, result = self.workflow()
        self.assertEqual((code, events, result["stage"]), (1, [], "preflight"))

    def test_agent_secure_filter(self):
        repo = Path(__file__).resolve().parents[4]
        tree = ast.parse((repo / "agent/src/testflinger_agent/agent.py").read_text())
        function = next(node for node in tree.body
                        if isinstance(node, ast.FunctionDef) and node.name == "secure_filter")
        namespace = {"Path": Path, "tarfile": tarfile}
        exec(compile(ast.Module(body=[function], type_ignores=[]), "agent_filter", "exec"), namespace)
        archive_path = self.base / "attachments.tar.gz"
        with tarfile.open(archive_path, "w:gz") as archive:
            for name in runner.LIMITS:
                archive.add(self.root / name, arcname=f"test/{name}")
        extracted = self.base / "extracted"
        extracted.mkdir()
        with tarfile.open(archive_path) as archive:
            archive.extractall(extracted, filter=namespace["secure_filter"])
        runner.validate_bundle(extracted / "test", NONCE, self.hash)


class SerialTests(unittest.TestCase):
    @staticmethod
    def line(sequence, nonce=NONCE, mac=runner.MAC):
        return f"{runner.MARKER} mac={mac} nonce={nonce} seq={sequence}"

    def test_matching_increasing(self):
        proof = runner.SerialProof(NONCE)
        self.assertFalse(proof.feed("boot noise"))
        self.assertEqual([proof.feed(self.line(i)) for i in (7, 8, 9)], [False, False, True])

    def test_mismatches_and_restarts(self):
        for bad in (self.line(8, nonce="c" * 32), self.line(8, mac="00:00:00:00:00:00"),
                    self.line(0x100000000), "TF_ESP32S3_HELLO_V1_PASS mac=anything seq=8"):
            proof = runner.SerialProof(NONCE)
            proof.feed(self.line(7))
            self.assertFalse(proof.feed(bad))
            self.assertEqual([proof.feed(self.line(i)) for i in (9, 10, 11)], [False, False, True])
        for values in ((7, 7, 8, 9), (9, 0, 1, 2)):
            proof = runner.SerialProof(NONCE)
            self.assertEqual([proof.feed(self.line(i)) for i in values], [False, False, False, True])

    def test_fragmented_serial_capture(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(runner.hardware, "open_serial") as opened:
            data = ("boot\n" + "\n".join(self.line(i) for i in (7, 8, 9)) + "\n").encode()
            opened.return_value.__enter__.return_value.read.side_effect = [data[:31], data[31:]]
            log = Path(directory) / "serial.log"
            self.assertEqual(runner.capture_serial(log, NONCE, timeout=2), [7, 8, 9])
            self.assertEqual(log.read_bytes(), data)

    def test_serial_timeout(self):
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(runner.time, "monotonic", side_effect=[0, 46]):
            with self.assertRaises(TimeoutError):
                runner.capture_serial(Path(directory) / "serial.log", NONCE)

    def test_reconnect_discards_previous_matches(self):
        import serial

        with tempfile.TemporaryDirectory() as directory, \
             patch.object(runner.hardware, "open_serial") as opened, \
             patch.object(runner.time, "sleep"):
            read = opened.return_value.__enter__.return_value.read
            read.side_effect = [
                (self.line(7) + "\n" + self.line(8) + "\n").encode(),
                serial.SerialException("disconnected"),
                (self.line(9) + "\n").encode(),
                (self.line(10) + "\n" + self.line(11) + "\n").encode(),
            ]
            sequences = runner.capture_serial(Path(directory) / "serial.log", NONCE, timeout=2)
            self.assertEqual(sequences, [9, 10, 11])
            self.assertEqual(opened.call_count, 2)


class RealBundleTests(unittest.TestCase):
    @unittest.skipUnless((BUILD / "manifest.json").exists(), "Workshop build required")
    def test_real_workshop_bundle(self):
        raw = (BUILD / "manifest.json").read_bytes()
        manifest = json.loads(raw)
        runner.validate_bundle(BUILD, manifest["nonce"], sha(raw))


if __name__ == "__main__":
    unittest.main()
