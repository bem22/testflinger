# Workshop nonce runner (opt-in, not deployed)

This is a separate trusted-lab workflow for the ESP32-S3 with STA MAC
`e8:f6:0a:81:84:84`. It accepts freshly built Workshop artifacts instead of the
old runner's fixed image hashes. It is not a general-purpose flashing service.

## Scope and trust boundary

- New queue: `pi5-esp32s3-workshop-nonce-01`.
- New runner: `../agents/pi5-upstream-01/flash_nonce.py`.
- New test wrapper: `../scripts/tf-test-esp32s3-nonce.sh`.
- Candidate config: `agent.conf.example`; it is NOT the live agent config.
- The old queue, runner, wrapper, and deployed config are unchanged.
- The new runner imports the old module's device IO helpers without modifying
  its fixed-hash validation or V1 serial parser.

**Only trusted submitters may use this queue.** A manifest, nonce and checksum
are not signatures or authorization. Someone who can submit a job can generate
their own matching hashes and malicious firmware, and firmware can print any
MAC/nonce. This demo correlates a trusted build with a selected physical board;
it does not provide hardware attestation. Do not expose this queue to untrusted
PRs or anonymous users without server-side access controls.

## Prepare a job without submitting or flashing

From `lab/esp32s3-hello`, on the host:

```shell
bash build-workshop-local.sh
python3 prepare-workshop-job.py
```

Use an appropriate host Python 3 environment. The preparation helper needs only
the standard library and this repository; it does not import esptool or access
serial hardware. It applies the same bundle preflight as the runner before
writing `build/workshop/testflinger-job.json`.

The generated JSON is also valid YAML for the Testflinger CLI. It maps six
files (three images, both flash argument files and the manifest), with local
paths relative to the generated job file. The CLI adds the required `test/`
attachment prefix; the runner reads `attachments/test/`.

The confirmation pins all three values:

```text
CONFIRM_FLASH <configured MAC> <build nonce> <manifest SHA-256>
```

After any rebuild, regenerate the job. Do not copy, rebuild, or submit the
bundle concurrently. A changed manifest or image fails preflight rather than
silently flashing a different build. Keep a separate immutable copy of the
bundle and job for each future concurrent CI run.

## Preflight and execution

Before the first device operation, the runner requires:

1. The exact queue, configured MAC and confirmation format.
2. A manifest matching the job's SHA-256 and nonce, schema 1, ESP32-S3,
   `tf_s3_hello` version 1.0.0, and ESP-IDF 5.5.3.
3. Full host-reported Git HEAD and a Boolean dirty state (dirty builds are
   allowed in this lab). Missing Git provenance is rejected.
4. Exactly five inventoried artifacts with fixed relative paths, no duplicates,
   symlinks or special files, bounded sizes and matching hashes.
5. Fixed offsets 0, 0x8000 and 0x10000, DIO/40MHz/4MB flash settings and the
   existing known partition-table hash. Bootloader is at most 32 KiB; app is at
   most 1 MiB. Image headers must identify ESP32-S3.
6. The expected nonce and V2 serial marker embedded in the application image.

Validated image bytes are copied to a private temporary directory. Commands
use those copies, never submitted paths or shell commands. Submitted
`flash_args` is inventoried but never executed; esptool arguments are fixed by
the runner. Extra attachment files are ignored, never executed or flashed.

Execution is exactly:

```text
read_mac -> require physical chip/MAC -> write_flash once -> verify_flash
         -> USB hard reset -> require MAC + nonce + 3 increasing sequences
```

Serial capture has a 45-second deadline. Wrong proof markers reset the counter;
reconnections discard partial lines and previous matches. Device reconnects
never trigger another write. Any stage failure stops later operations. A
failure after writing can leave the board with new or partial firmware; there
is no rollback or automatic reflash.

## Artifacts

`result.json` always reports the workflow's success or failure stage (provided
the artifact directory is writable). Validated jobs also record the expected
MAC, nonce and manifest digest; successful jobs include the accepted sequence
numbers. The validated manifest is copied alongside identity, flash, verify
and serial logs as those stages run. The wrapper attempts to collect artifacts
even when the test fails, then preserves the failure exit code. Setup failures
before Python starts may have no structured result and must not count as pass.

## Deployment gate: same agent, not an additional agent

The deployed Pi agent configuration and Juju configuration remain unchanged.
Server-side queue access controls and the agent 01 restart performed during
readiness checks are recorded below.

Before deploying:

1. Verify Testflinger reachability from the Pi and agent guest, authentication,
   and that agent 01 is idle with no queued/in-progress hardware job.
2. Restrict the nonce queue to trusted submitters or use an isolated trusted lab
   server. The existing lab's anonymous submission policy is not suitable for
   untrusted network access to this arbitrary-firmware queue.
3. Publish/review the demo branch and preserve the existing config revision.
4. Stop agent 01, deploy both Python modules and the new wrapper, then select
   this example config through the charm's supported configuration mechanism.
   Keep the same serial-device mapping and cleanup behavior. Do not register
   another agent against this board. Agent 02 remains unchanged.
5. Check the agent advertises only the nonce queue, then explicitly approve one
   manual firmware replacement before submission. No backup is made.

Once those gates are satisfied, submission from the firmware directory is:

```shell
bash nonce-cli.sh submit --poll build/workshop/testflinger-job.json
```

That command **does flash the board** when consumed by the new runner; it has
not been run as part of the offline validation. Require setup/test/cleanup
exit statuses of zero and a passing result artifact with the expected MAC,
nonce and manifest digest. A job marked complete alone is insufficient.

`nonce-cli.sh` uses the dedicated contributor login stored under
`~/.local/state/testflinger-demo-submitter/`, outside the Workshop mount.
It never uses the independent admin profile or the older anonymous lab CLI
profile. Authentication refresh tokens are private local files, not repository
artifacts. The generated submitter password is not retained; an administrator
can reset it if the saved refresh token expires.

### Readiness checks on 2026-10-01

- Guest HTTP access to Testflinger returned 200 and the serial device was present.
- Agent 01's old queue contained only terminal jobs; no test containers existed.
- Both long-running agents had 403 polling failures despite the charm being
   active. Restarting only idle agent 01 restored authenticated registration and
   polling. Agent 02 was not restarted or reconfigured.
- Created contributor `workshop-demo-submitter` with no elevated priority.
- Registered the nonce queue temporarily on stopped agent 01 in maintenance,
   restricted it through the server API to that contributor, then restored
   the old queue metadata and restarted agent 01 unchanged.
- A non-flashing anonymous submission probe was rejected with HTTP 401
   (no job created). The dedicated contributor refreshed successfully with
   the nonce queue in its allowed queues.
- The nonce runner is not yet deployed. The Pi host itself cannot resolve
   `testflinger.local`; the guest can. Host DNS was not modified.

The queue restriction is server-side and persists independently of which agent
advertises it. Confirm it still names the dedicated contributor immediately
before enabling the new runner. Contributor access to other unrestricted queues
is governed by normal server policy; this account is not globally limited to
only the nonce queue.

To return to the old demo, wait for idle, stop agent 01, restore the previous
config/revision and restart it; do not change agent 02 or run both wrappers in
parallel. Restoring agent config does not restore firmware on the board.

## Offline validation

From `lab/arm64-smoke/agents/pi5-upstream-01`:

```shell
python3 -m unittest -v test_flash_nonce test_flash_hello
```

The host environment needs pyserial for the mocked serial tests. Tests never
open a real device. The real-bundle preflight test uses existing Workshop
artifacts when present; synthetic fixtures mock only the partition hash within
their tests. Tests also extract a generated archive using the actual agent
`secure_filter` and validate the extracted files.
