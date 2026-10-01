"""Offline CI orchestration tests: no HTTP or physical-device access."""

import io
import json
from pathlib import Path
import tarfile
import unittest

import ci_flash_test as ci
from test_flash_nonce import NonceTests, NONCE


class Response:
    status_code = 200

    def __init__(self, data=None, content=b""):
        self.data = data
        self.content = content

    def json(self):
        return self.data

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def iter_content(self, size):
        yield self.content


class FakeAPI:
    def __init__(self, fixture):
        self.fixture = fixture
        self.posts = []
        self.failure = None
        self.running = False
        self.restricted = True
        self.busy = False
        self.results = {"job_state": "complete", "setup_status": 0,
                        "test_status": 0, "cleanup_status": 0,
                        "test_output": "--no-stub write_flash "}
        self.result = {"status": "pass", "mac": ci.runner.MAC, "nonce": NONCE,
                       "manifest_sha256": fixture.hash,
                       "source": fixture.manifest["source"], "sequences": [7, 8, 9]}

    def archive(self):
        files = {"result.json": json.dumps(self.result).encode(),
                 "manifest.json": (self.fixture.root / "manifest.json").read_bytes(),
                 "identity.log": b"MAC verified", "flash.log": b"flashed",
                 "verify.log": b"verify OK (digest matched)\n" * 3,
                 "serial.log": "\n".join(
                     f"{ci.runner.MARKER} mac={ci.runner.MAC} nonce={NONCE} seq={i}"
                     for i in (7, 8, 9)).encode()}
        output = io.BytesIO()
        with tarfile.open(fileobj=output, mode="w:gz") as archive:
            for name, data in files.items():
                member = tarfile.TarInfo("artifacts/" + name)
                member.size = len(data)
                archive.addfile(member, io.BytesIO(data))
        return output.getvalue()

    def get_json(self, endpoint):
        if "restricted-queues" in endpoint:
            return {"owners": [ci.OWNER] if self.restricted else []}
        if "agents/data" in endpoint:
            return {"state": "waiting", "job": {}, "queues": [ci.runner.QUEUE]}
        if endpoint.endswith("/jobs"):
            return [{"job_state": "waiting"}] if self.busy else []
        return {"job_state": "test"} if self.running else self.results

    def request(self, method, endpoint, **kwargs):
        if method == "POST":
            self.posts.append(endpoint)
            if self.failure == endpoint or self.failure == "upload" and endpoint.endswith("attachments"):
                raise TimeoutError("injected ambiguous request failure")
            if endpoint == "/v1/job":
                # Receipt must exist before submission, not just after return.
                receipt = json.loads((self.fixture.root / "hardware/receipt.json").read_text())
                assert receipt["job_id"] == kwargs["json"]["job_id"]
                assert receipt["stage"] == "submission_intent"
                return Response({"job_id": kwargs["json"]["job_id"]})
            with tarfile.open(fileobj=io.BytesIO(kwargs["files"]["file"][1])) as archive:
                assert set(archive.getnames()) == {"test/" + n for n in ci.runner.LIMITS}
            return Response()
        return Response(content=self.archive())


class CITests(unittest.TestCase):
    def setUp(self):
        self.fixture = NonceTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.root
        self.fixture.manifest["source"]["dirty"] = False
        self.fixture.save_manifest()
        ci.save(self.root / "testflinger-job.json", self.fixture.job)
        ci.save(self.root / "github-run.json", {
            "run_id": "42", "commit": "b" * 40, "repository": "bem22/testflinger"})
        self.api = FakeAPI(self.fixture)
        self.ledger = self.fixture.base / "ledger"

    def execute(self, **kwargs):
        return ci.execute(self.root, self.api, "42", "b" * 40, self.ledger, **kwargs)

    def test_success(self):
        result = self.execute()
        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["sequences"], [7, 8, 9])
        self.assertEqual(len(self.api.posts), 2)

    def test_no_repeat_submission(self):
        first = self.execute()
        with self.assertRaises(FileExistsError):
            self.execute()
        self.assertEqual(len(self.api.posts), 2)
        receipt = json.loads((self.root / "hardware/receipt.json").read_text())
        self.assertEqual(receipt["job_id"], first["job_id"])

    def test_ambiguous_submission_never_retries(self):
        self.api.failure = "/v1/job"
        with self.assertRaises(TimeoutError):
            self.execute()
        self.assertEqual(self.api.posts, ["/v1/job"])
        self.assertTrue((self.ledger / "42.json").exists())

    def test_upload_failure_never_retries(self):
        self.api.failure = "upload"
        with self.assertRaises(TimeoutError):
            self.execute()
        self.assertEqual(len(self.api.posts), 2)
        self.assertTrue((self.root / "hardware/receipt.json").exists())

    def test_poll_timeout_retains_job(self):
        self.api.running = True
        with self.assertRaises(TimeoutError):
            self.execute(timeout=0)
        self.assertEqual(len(self.api.posts), 2)
        receipt = json.loads((self.root / "hardware/receipt.json").read_text())
        self.assertIn("job_id", receipt)

    def test_unrestricted_queue_never_submits(self):
        self.api.restricted = False
        with self.assertRaises(ValueError):
            self.execute()
        self.assertEqual(self.api.posts, [])

    def test_busy_queue_never_submits(self):
        self.api.busy = True
        with self.assertRaises(ValueError):
            self.execute()
        self.assertEqual(self.api.posts, [])

    def test_wrong_build_never_submits(self):
        with self.assertRaises(ValueError):
            ci.execute(self.root, self.api, "42", "c" * 40, self.ledger)
        self.assertEqual(self.api.posts, [])

    def test_wrong_nonce_fails_with_artifacts(self):
        self.api.result["nonce"] = "c" * 32
        with self.assertRaises(ValueError):
            self.execute()
        self.assertTrue((self.root / "hardware/artifacts.tar.gz").exists())

    def test_wrong_sequences_fail(self):
        self.api.result["sequences"] = [1, 2, 3]
        with self.assertRaises(ValueError):
            self.execute()

    def test_failed_phase_fails(self):
        self.api.results["test_status"] = 1
        with self.assertRaises(ValueError):
            self.execute()

    def test_duplicate_flash_fails(self):
        self.api.results["test_output"] *= 2
        with self.assertRaises(ValueError):
            self.execute()


if __name__ == "__main__":
    unittest.main()
