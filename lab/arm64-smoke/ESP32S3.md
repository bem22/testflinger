# ESP32-S3 identity job (lab only)

Branch: `lab/esp32s3-identity-config`. Agent 01 serves only
`pi5-esp32s3-identity-01`; agent 02 remains the unchanged native control.
This branch extends the successful Docker baseline described in [README](README.md).
It does not modify the charm or the ARM64 contribution branch.

## Known hardware and manual validation

- Selected USB serial: `E8:F6:0A:81:84:84` (Espressif `303a:1001`).
- Manual ROM response: ESP32-S3 QFN56 revision v0.2, embedded flash 4 MB,
  embedded PSRAM 2 MB, MAC `e8:f6:0a:81:84:84`.
- Pi LXD guest: `juju-05a78d-0`, Ubuntu 22.04 ARM64.
- Instance device `esp32s3-serial`: `unix-char`, source
  `/dev/serial/by-id/usb-Espressif_USB_JTAG_serial_debug_unit_E8:F6:0A:81:84:84-if00`,
  guest path `/dev/esp32s3`, UID/GID 1000, mode 0660, `required=false`.
- Docker mapping: `--device=/dev/esp32s3:/dev/esp32s3:rw`.
- Manual esptool 4.8.1 `read_mac` succeeded only after explicitly selecting
  `--before usb_reset`; automatic PID detection through the alias failed.

The mapping is instance-local, outside the charm, and must be recreated if Juju
replaces the machine. It selects the board, not a transient ttyACM number.
USB disconnect/re-enumeration during a running Docker job remains unvalidated;
device major/minor mappings inside an existing container may become stale.
Do not broaden access to compensate without diagnosis.

## Behavior and safety

The lab wrapper invokes the same noprovision `runtest` connector as the Docker
baseline and retains upstream `tf-cleanup`. It pins the previously tested image
digest and installs esptool 4.8.1 with the guest's connector source. Transitive
Python dependencies and the guest's workload source are not pinned here.
Package installation occurs only in the disposable test container.

Only the selected serial device is exposed. There is no privileged mode, raw USB
bus mount, Docker socket, or SSH credential mount. Source/configuration mounts
are read-only. Test commands run as ubuntu, but the image permits passwordless
sudo: this is not an untrusted-code sandbox. Both Supervisor agents share a UID
and Docker access, so assigning the board to agent 01 is not security isolation.
Use a trusted, access-controlled network: this lab permits anonymous submissions.
Close all other serial monitors and do not run a manual probe concurrently.

The supplied job does not erase/write flash or eFuses. It resets the board into
its ROM bootloader and leaves it there (`--after no_reset`). Normal firmware
execution is interrupted. Press EN/RESET afterward to return to normal boot.
The chip/MAC assertions detect the wrong target only after communication begins.

## Activate and validate

With both agents waiting and queues empty, set application `agent-host` in Pi
model `upstream-testflinger-arm64` to `config-branch=lab/esp32s3-identity-config`.
Leave `config-dir=lab/arm64-smoke/agents` unchanged. This restarts both agents.
No charm rebuild or manual helper installation is needed: agent 01 invokes the
versioned wrapper via `/bin/bash` from the cloned configuration repository.

Wait for server-side registration on the new queue before submitting
[the identity job](jobs/agent-01.yaml). Require:

1. Job complete with setup/test/cleanup status 0.
2. `ESP32S3_IDENTITY_PASS` in output.
3. Artifacts `esp32s3-identity.txt` and `identity-status.txt` containing the
   expected chip/MAC transcript and success marker.
4. Successful container removal, both agents waiting, and a second successful job.

End-to-end queued hardware validation is pending. Only the manual Docker probe
has passed so far. Firmware flashing remains out of scope.

## Rollback

After jobs finish and this queue is empty, restore
`config-branch=lab/arm64-docker-smoke-config` for hardware-free Docker testing,
or `lab/arm64-smoke-config` for fixed native commands. The LXD serial mapping
persists independently; remove instance device `esp32s3-serial` if it is no
longer needed. Never remove all devices or change the shared LXD profile.
