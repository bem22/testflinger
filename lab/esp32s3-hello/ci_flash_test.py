"""Single-submit CI hardware demo; never retry a submission or flash."""

import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import tarfile
import time
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]
                      / "arm64-smoke/agents/pi5-upstream-01"))
import flash_nonce as runner

SERVER = "http://testflinger.local"
OWNER = "workshop-demo-submitter"


def save(path, data):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, indent=2) + "\n")
    temporary.replace(path)


class API:
    """Authenticated requests without the CLI's automatic POST replay hooks."""

    def __init__(self):
        import jwt
        import requests
        from testflinger_cli.auth import TestflingerCliAuth

        os.environ["XDG_CONFIG_HOME"] = str(
            Path.home() / ".local/state/testflinger-demo-submitter/config")
        os.environ.pop("TESTFLINGER_CLIENT_ID", None)
        os.environ.pop("TESTFLINGER_SECRET_KEY", None)
        self.auth = TestflingerCliAuth(SERVER)
        self.session = requests.Session()
        self.session.trust_env = False
        self.jwt = jwt

    def request(self, method, endpoint, **kwargs):
        # Fresh authentication before each request; no retry of the request.
        token = self.auth.authenticate()
        if not token:
            raise RuntimeError("Dedicated submitter login is required")
        claims = self.jwt.decode(token, options={"verify_signature": False})
        permissions = claims["permissions"]
        if (permissions.get("role") != "contributor"
                or runner.QUEUE not in (permissions.get("allowed_queues") or [])):
            raise RuntimeError("Expected contributor with nonce queue permission")
        response = self.session.request(
            method, SERVER + endpoint,
            headers={"Authorization": "Bearer " + token},
            timeout=(10, 60), allow_redirects=False, **kwargs)
        if not 200 <= response.status_code < 300:
            raise RuntimeError(f"Testflinger {method} failed: HTTP {response.status_code}")
        return response

    def get_json(self, endpoint):
        response = self.request("GET", endpoint)
        return None if response.status_code == 204 else response.json()


def pack(captured):
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w:gz") as archive:
        for name, data in captured.items():
            member = tarfile.TarInfo("test/" + name)
            member.size = len(data)
            member.mode = 0o644
            archive.addfile(member, io.BytesIO(data))
    return output.getvalue()


def verify(results, archive_path, expected, manifest_hash):
    """Read bounded regular members only; never extract arbitrary archive paths."""
    required = ("result.json", "manifest.json", "serial.log", "identity.log",
                "flash.log", "verify.log")
    captured = {}
    with tarfile.open(archive_path) as archive:
        for index, member in enumerate(archive):
            if index > 64:
                raise ValueError("Too many result archive members")
            if member.name not in {"artifacts/" + n for n in required}:
                continue
            if member.name in captured or not member.isfile() or member.size > 2**20:
                raise ValueError("Unsafe or duplicate result member")
            with archive.extractfile(member) as stream:
                captured[member.name] = stream.read(2**20 + 1)
    if set(captured) != {"artifacts/" + n for n in required}:
        raise ValueError("Missing hardware evidence")
    raw = captured["artifacts/manifest.json"]
    if raw != expected or hashlib.sha256(raw).hexdigest() != manifest_hash:
        raise ValueError("Returned manifest differs from submitted manifest")
    manifest = runner.parse_json(expected)
    result = runner.parse_json(captured["artifacts/result.json"])
    if (result.get("status") != "pass" or result.get("mac") != runner.MAC
            or result.get("nonce") != manifest["nonce"]
            or result.get("manifest_sha256") != manifest_hash
            or result.get("source") != manifest["source"]):
        raise ValueError("Hardware result identity mismatch or failure")
    proof = runner.SerialProof(manifest["nonce"])
    proved = False
    for line in captured["artifacts/serial.log"].decode("utf-8").splitlines():
        if proof.feed(line.strip()):
            proved = True
            break
    sequences = result.get("sequences")
    if (not proved or not isinstance(sequences, list) or len(sequences) != 3
            or any(type(value) is not int for value in sequences)
            or sequences != proof.sequences):
        raise ValueError("Serial proof does not match result sequences")
    if results.get("job_state") != "complete" or any(
        type(results.get(key)) is not int or results[key] != 0
        for key in ("setup_status", "test_status", "cleanup_status")
    ):
        raise ValueError("Setup/test/cleanup did not all succeed")
    if captured["artifacts/verify.log"].count(b"verify OK (digest matched)") != 3:
        raise ValueError("Missing flash verification evidence")
    if results.get("test_output", "").count("--no-stub write_flash ") != 1:
        raise ValueError("Expected exactly one flash invocation")
    return result


def execute(bundle, api, run_id, commit, ledger_dir, timeout=600):
    output = bundle / "hardware"
    output.mkdir(exist_ok=True)
    receipt = {"status": "fail", "run_id": run_id, "stage": "preflight"}
    try:
        job = runner.parse_json((bundle / "testflinger-job.json").read_bytes())
        nonce, digest = runner.validate_job(job)
        manifest, captured = runner.validate_bundle(bundle, nonce, digest)
        metadata = runner.parse_json((bundle / "github-run.json").read_bytes())
        if (manifest["source"]["commit"] != commit or manifest["source"]["dirty"]
                or metadata.get("commit") != commit or metadata.get("run_id") != run_id
                or metadata.get("repository") != "bem22/testflinger"):
            raise ValueError("Bundle does not belong to this clean CI build")
        restriction = api.get_json("/v1/restricted-queues/" + runner.QUEUE)
        if restriction.get("owners") != [OWNER]:
            raise ValueError("Nonce queue restriction changed")
        agent = api.get_json("/v1/agents/data/pi5-upstream-01")
        if (agent.get("state") != "waiting" or agent.get("job")
                or agent.get("queues") != [runner.QUEUE]):
            raise ValueError("Nonce agent is not idle on the expected queue")
        jobs = api.get_json("/v1/queues/" + runner.QUEUE + "/jobs") or []
        if any(j.get("job_state") not in ("complete", "cancelled") for j in jobs):
            raise ValueError("Nonce queue has outstanding work")
        archive = pack(captured)
        # Construct only the known job fields; never forward arbitrary commands.
        job_id = str(uuid.uuid4())
        job = {"job_id": job_id, "job_queue": runner.QUEUE, "test_data": {
            "test_cmds": f"CONFIRM_FLASH {runner.MAC} {nonce} {digest}",
            "attachments": [{"agent": name} for name in runner.LIMITS]}}
        receipt.update(job_id=job_id, nonce=nonce, mac=runner.MAC,
                       manifest_sha256=digest, stage="submission_intent")
        ledger_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        # Exclusive durable intent BEFORE any POST. Reruns cannot double-submit.
        ledger_path = ledger_dir / f"{run_id}.json"
        try:
            with ledger_path.open("x") as ledger:
                json.dump(receipt, ledger)
                ledger.flush()
                os.fsync(ledger.fileno())
        except FileExistsError:
            # Preserve the original ID when reporting a blocked repeat.
            receipt = runner.parse_json(ledger_path.read_bytes())
            raise
        save(output / "receipt.json", receipt)
        print(f"Testflinger job ID (recorded before submission): {job_id}", flush=True)
        response = api.request("POST", "/v1/job", json=job).json()
        if response.get("job_id") != job_id:
            raise ValueError("Server did not preserve the proposed job ID")
        receipt["stage"] = "attachments"
        save(output / "receipt.json", receipt)
        api.request("POST", f"/v1/job/{job_id}/attachments",
                    files={"file": ("attachments.tar.gz", archive, "application/x-gzip")})
        receipt["stage"] = "waiting"
        deadline = time.monotonic() + timeout
        while True:
            results = api.get_json(f"/v1/result/{job_id}")
            save(output / "phase-results.json", results)
            state = results.get("job_state")
            print(f"Testflinger {job_id}: {state}", flush=True)
            if state in ("complete", "cancelled"):
                break
            if time.monotonic() >= deadline:
                raise TimeoutError("Job still pending; inspect recorded ID before any new run")
            time.sleep(5)
        receipt["stage"] = "artifacts"
        archive_path = output / "artifacts.tar.gz"
        with api.request("GET", f"/v1/result/{job_id}/artifact", stream=True) as response:
            size = 0
            with archive_path.open("wb") as stream:
                for chunk in response.iter_content(65536):
                    size += len(chunk)
                    if size > 10 * 2**20:
                        raise ValueError("Hardware artifact exceeds 10 MiB")
                    stream.write(chunk)
        receipt["stage"] = "verification"
        result = verify(results, archive_path, captured["manifest.json"], digest)
        receipt.update(status="pass", stage="complete", sequences=result["sequences"],
                       source_commit=commit,
                       archive_sha256=hashlib.sha256(archive_path.read_bytes()).hexdigest())
        return receipt
    except Exception as error:
        # Do not expose response bodies, JWTs, or request headers in CI artifacts.
        receipt["error"] = f"{type(error).__name__}: {error}"
        raise
    finally:
        save(output / "receipt.json", receipt)
        print(json.dumps(receipt, indent=2), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", type=Path)
    args = parser.parse_args()
    env = os.environ
    if (env.get("GITHUB_REPOSITORY") != "bem22/testflinger"
            or env.get("GITHUB_EVENT_NAME") != "workflow_dispatch"
            or env.get("GITHUB_REF") != "refs/heads/lab/workshop-esp32s3-build"
            or env.get("RUNNER_NAME") != "freertos-demo"
            or env.get("GITHUB_RUN_ATTEMPT") != "1"):
        raise RuntimeError("Only first-attempt manual demo runs may submit hardware jobs")
    run_id = env["GITHUB_RUN_ID"]
    if not run_id.isdigit():
        raise ValueError("Invalid run ID")
    os.umask(0o077)
    try:
        result = execute(args.bundle, API(), run_id, env["GITHUB_SHA"],
                         Path.home() / ".local/state/testflinger-demo-runs")
        summary = f"Hardware PASS: job {result['job_id']}; MAC {result['mac']}; nonce {result['nonce']}; sequences {result['sequences']}"
        return_code = 0
    except Exception as error:
        summary = f"Hardware FAILED ({type(error).__name__}). Inspect hardware/receipt.json and the recorded job before any new run. No automatic retry."
        return_code = 1
    with Path(env["GITHUB_STEP_SUMMARY"]).open("a") as stream:
        stream.write("\n## Flash and test\n\n" + summary + "\n")
    print(summary)
    return return_code


if __name__ == "__main__":
    raise SystemExit(main())
