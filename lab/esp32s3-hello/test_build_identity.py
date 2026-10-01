"""Offline tests; synthetic artifacts do not prove hardware execution."""

import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import build_identity as identity


class IdentityTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.project = Path(temporary.name)
        self.build = self.project / "build/workshop"
        self.build.mkdir(parents=True)
        for name in identity.INPUT_FILES:
            (self.project / name).write_text("fixture\n")
        (self.project / "main").mkdir()
        (self.project / "main/hello.c").write_text("fixture\n")
        environment = patch.dict(os.environ, {}, clear=True)
        environment.start()
        self.addCleanup(environment.stop)

    def prepare(self):
        return identity.prepare(self.project, self.build)

    def artifacts(self, state):
        for name in identity.ARTIFACTS:
            path = self.build / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"artifact")
        (self.build / "tf_s3_hello.bin").write_bytes(
            identity.MARKER.encode() + b"\0" + state["nonce"].encode() + b"\0"
        )
        identity.write_json(self.build / "flasher_args.json", {
            "flash_files": identity.FLASH_FILES,
            "extra_esptool_args": {"chip": "esp32s3"},
        })
        identity.write_json(self.build / "project_description.json", {
            "target": "esp32s3", "project_name": "tf_s3_hello", "project_version": "1.0.0",
        })
        (self.build / "idf-version.txt").write_text("ESP-IDF v5.5.3\n")

    def test_fresh_nonce_and_header(self):
        first = self.prepare()
        second = self.prepare()
        self.assertNotEqual(first["nonce"], second["nonce"])
        self.assertRegex(second["nonce"], r"^[0-9a-f]{32}$")
        self.assertIn(second["nonce"], (self.build / "identity/tf_build_identity.h").read_text())
        self.assertIsNone(second["source"]["commit"])
        self.assertIsNone(second["source"]["dirty"])

    def test_host_metadata(self):
        with patch.dict(os.environ, {"TF_SOURCE_COMMIT": "a" * 40, "TF_SOURCE_DIRTY": "true"}):
            state = self.prepare()
        self.assertEqual(state["source"]["commit"], "a" * 40)
        self.assertTrue(state["source"]["dirty"])

    def test_invalid_metadata(self):
        for values in ({"TF_SOURCE_COMMIT": "HEAD"}, {"TF_SOURCE_DIRTY": "false"},
                       {"TF_SOURCE_COMMIT": "a" * 40, "TF_SOURCE_DIRTY": "maybe"}):
            with self.subTest(values=values), patch.dict(os.environ, values), self.assertRaises(ValueError):
                self.prepare()

    def test_manifest_hashes_and_offsets(self):
        state = self.prepare()
        self.artifacts(state)
        manifest = identity.finalize(self.project, self.build)
        self.assertEqual(manifest["nonce"], state["nonce"])
        self.assertEqual(len(manifest["artifacts"]), 5)
        for entry in manifest["artifacts"]:
            path = self.build / entry["path"]
            self.assertEqual(entry["sha256"], identity.digest(path))
            self.assertEqual(entry["size"], path.stat().st_size)
        self.assertEqual(manifest["artifacts"][2]["offset"], "0x10000")
        self.assertEqual(json.loads((self.build / "manifest.json").read_text()), manifest)

    def test_new_build_invalidates_previous_manifest(self):
        state = self.prepare()
        self.artifacts(state)
        identity.finalize(self.project, self.build)
        self.prepare()
        self.assertFalse((self.build / "manifest.json").exists())

    def test_wrong_nonce_rejects_stale_firmware(self):
        state = self.prepare()
        self.artifacts(state)
        self.prepare()
        with self.assertRaisesRegex(ValueError, "expected build nonce"):
            identity.finalize(self.project, self.build)
        self.assertFalse((self.build / "manifest.json").exists())

    def test_source_change_rejected(self):
        state = self.prepare()
        self.artifacts(state)
        (self.project / "main/hello.c").write_text("changed")
        with self.assertRaisesRegex(ValueError, "Source files changed"):
            identity.finalize(self.project, self.build)

    def test_wrong_target_rejected(self):
        state = self.prepare()
        self.artifacts(state)
        identity.write_json(self.build / "project_description.json", {"target": "esp32"})
        with self.assertRaisesRegex(ValueError, "Unexpected firmware"):
            identity.finalize(self.project, self.build)

    def test_wrong_mapping_rejected(self):
        state = self.prepare()
        self.artifacts(state)
        identity.write_json(self.build / "flasher_args.json", {"flash_files": {}})
        with self.assertRaisesRegex(ValueError, "Unexpected flash mapping"):
            identity.finalize(self.project, self.build)

    def test_missing_artifact_leaves_no_manifest(self):
        state = self.prepare()
        self.artifacts(state)
        (self.build / "flash_args").unlink()
        with self.assertRaises(FileNotFoundError):
            identity.finalize(self.project, self.build)
        self.assertFalse((self.build / "manifest.json").exists())


if __name__ == "__main__":
    unittest.main()
