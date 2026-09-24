# One-command firmware submission

Run on the laptop from this directory:

```bash
bash lab-cli.sh submit --poll flash-hello.yaml
```

This is a REAL firmware replacement, not a dry run. Each invocation submits a
new job and can reflash the board. Do not repeat after an ambiguous network error;
inspect the existing job first. No backup is taken. The old API submission receipts
do not prevent deliberate new CLI submissions.

## Where the firmware comes from

`flash-hello.yaml` lists every file under `test_data.attachments`:

- `local` is a laptop path, resolved relative to the YAML file.
- `agent` is its destination relative to the phase's attachment directory.
- The CLI automatically adds `test/` to archive members for `test_data`.
- The CLI packages the files, submits the job, and uploads its archive.
- The Pi agent extracts the files under `attachments/test/`.

No hand-built tarball, shell `bundle` variable, or separate curl upload is needed.
The binary files are ignored local build outputs; cloning the branch alone does
not download them. The deployed runner still accepts only the validated firmware
hashes and the expected MAC. Rebuilding can change hashes and require review.

## CLI profile

`lab-cli.sh` invokes the non-snap CLI installed in the laptop's existing
`~/code/tf-venv/.venv` environment. Override `TESTFLINGER_LAB_CLI` for another
non-snap installation. It passes arguments to the real CLI without implementing
its own packaging, upload, or flashing logic.

The launcher uses an independent XDG profile under ignored `build/cli-profile`
and clears credential environment variables. The existing snap agent login is
untouched. This trusted lab explicitly permits anonymous contributor submissions
with OIDC disabled; this is not a production authentication recommendation.

## Evidence

`--poll` streams job output. Require complete state, setup/test/cleanup all zero,
and `ESP32S3_FLASH_HELLO_PASS`; complete alone is insufficient.

For an existing job (replace JOB_ID):

```bash
bash lab-cli.sh results JOB_ID
bash lab-cli.sh poll JOB_ID
```

These read results without flashing again. Serial and verification logs are also
stored in the job artifacts. The Pi's v2 configuration does not need changing.

## Setup validation (2026-09-24)

The independent CLI profile successfully read queues, target agent status, and
the previous successful flash result. The installed CLI packed all five YAML
attachments with the correct `test/` prefix. The actual agent extraction filter
accepted that archive, and the runner validated the extracted hashes and layout.
The CLI submission/upload flow was also exercised with network submission mocked.
No new hardware job was submitted during this switch.
