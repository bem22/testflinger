"""Validate a built bundle and create CLI attachment JSON. Does not submit it."""

import argparse
import hashlib
import json
from pathlib import Path
import sys

# Reuse exactly the agent-side preflight, with no physical-device operations.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]
                      / "arm64-smoke/agents/pi5-upstream-01"))
import flash_nonce as runner


def prepare_job(build):
    build = build.resolve(strict=True)
    output = build / "testflinger-job.json"
    output.unlink(missing_ok=True)
    raw = runner.read_file(build, "manifest.json")
    nonce = runner.parse_json(raw).get("nonce")
    if not isinstance(nonce, str):
        raise ValueError("Manifest nonce missing")
    checksum = hashlib.sha256(raw).hexdigest()
    runner.validate_bundle(build, nonce, checksum)
    job = {
        "job_queue": runner.QUEUE,
        "test_data": {
            "test_cmds": f"CONFIRM_FLASH {runner.MAC} {nonce} {checksum}",
            "attachments": [{"local": name, "agent": name} for name in runner.LIMITS],
        },
    }
    runner.validate_job(job)
    temporary = output.with_suffix(".tmp")
    temporary.write_text(json.dumps(job, indent=2) + "\n")
    temporary.replace(output)
    print(f"Prepared {output}")
    print("NOT SUBMITTED. Requires the separately deployed, trusted-lab nonce queue.")
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", type=Path,
                        default=Path(__file__).resolve().parent / "build/workshop")
    args = parser.parse_args()
    prepare_job(args.build)


if __name__ == "__main__":
    main()
