# ESP32-S3-Zero flash and serial validation (lab only)

Branch `lab/esp32s3-flash-hello-config` changes agent 01's queue to
`pi5-esp32s3-flash-hello-01`. Agent 02 is unchanged. This is NOT the identity-only
configuration: it can overwrite the selected board's installed firmware.
The user authorized replacement without a backup.

## Execution

The wrapper retains the pinned Docker image and single serial mapping, but runs
the fixed `/config/flash_hello.py` instead of job-supplied shell commands. It
requires `test_cmds` to equal `CONFIRM_FLASH e8:f6:0a:81:84:84`, but never
executes that string. This is an accident-prevention guard, not authentication.
The lab server allows anonymous job submissions: use only a trusted network.

The script checks all three firmware SHA-256 hashes and the build-generated
flash layout before connecting. It verifies the chip and MAC, runs `write_flash`
once, explicitly verifies flash contents, resets using esptool 4.8.1's USB-aware
`HardReset`, and captures three increasing versioned hello markers for that MAC.
No whole-chip erase, eFuse changes, security overrides, or automatic reflash.
Flash programming necessarily erases the sectors occupied by the new images.
An interrupted flash can leave the board unable to boot until reflashed.

Input is the [validated firmware bundle](../esp32s3-hello/BUILD-VALIDATION.md).
The existing archive must be uploaded directly as Testflinger's attachment archive,
so its files appear immediately under `attachments/`, not inside a nested tarball.
The JSON job file is an API submission template, NOT a CLI auto-packaging recipe.
The attachment entry tells the server to hold the job pending attachment upload.
Upload the bundle with multipart field `file` using POST to
`/v1/job/<job_id>/attachments`. Do not submit until the new queue is registered.

## Activation on the Pi

When both agents are waiting and queues empty, change `agent-host` in model
`upstream-testflinger-arm64` to `config-branch=lab/esp32s3-flash-hello-config`.
Keep `config-dir` unchanged. Both agents restart. The existing LXD serial mapping
must still point to the selected S3. Close serial monitors and manual probes.
Source is delivered by the config repository; no charm rebuild is necessary.

After successful validation, expect complete/setup/test/cleanup status 0 and
`ESP32S3_FLASH_HELLO_PASS`, with identity, flash, verification, and serial logs,
firmware hashes, and result JSON in artifacts. Only one flash job is planned.

## Failure and rollback

Failures save the stage and available logs. The 45-second serial window retries
opening the same guest alias, not writing flash. USB re-enumeration may change
the device major/minor and invalidate Docker's mapping; fail and diagnose rather
than broaden access. Do not assume cleanup success proves firmware success.

After jobs finish, return to `lab/esp32s3-identity-config` for identity-only tests
or `lab/arm64-docker-smoke-config` for hardware-free Docker tests. Changing config
does NOT restore old firmware. No backup exists. Agent 02 and Nordic stay untouched.

Seven offline unit tests passed: confirmation, chip/MAC, real bundle hashes,
bad layout/hash rejection, successful sequencing, stop-on-failure without write
retries, and fragmented serial parsing/timeout. Shell syntax checks passed.
Esptool 4.8.1 validated the ESP-IDF 5.5.3 application's image checksum and hash.
The laptop submission helper verifies the bundle hash and waiting/new-queue state,
records the job ID, then uploads the archive. It refuses to resubmit when that
receipt exists; no automatic retry is made on an ambiguous submission failure.

Hardware execution of this flash workflow is pending. Offline tests cannot prove
ROM flash commands, reset, or serial re-enumeration behavior.
