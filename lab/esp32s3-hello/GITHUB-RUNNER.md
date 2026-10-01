# Manual Workshop build on the local runner

The repository runner `freertos-demo` uses the existing Workshop on the AMD64
host. Add the custom runner label `workshop-esp32s3` in the repository's Actions
runner settings. Keep the runner process running under the same host account
that owns Workshop. Workshop must already be Ready; the workflow does not
recreate containers or alter host networking.

## Run a build

1. Open Actions in `bem22/testflinger` and select **Workshop ESP32-S3 build**.
2. Select **Run workflow**, then branch **lab/workshop-esp32s3-build**.
3. Leave **flash_and_test** unchecked for build-only, or check it to explicitly
   replace firmware on the board with MAC `e8:f6:0a:81:84:84` and verify it.
4. Start the run and inspect its build/hardware summaries and uploaded artifact.

The workflow must also exist on the repository's default branch for GitHub to
show the manual trigger. Running it on the default branch deliberately skips
the build. There are no push, pull-request, or scheduled triggers.

This first integration uses the dedicated host worktree at
`$HOME/code/testflinger-workshop-demo`, which Workshop already mounts. It does
not use actions/checkout and will not reset, fetch, or modify that checkout.
Its branch must match the demo branch, its HEAD must equal the dispatched
`GITHUB_SHA`, and it must be clean. Update the host worktree deliberately before
dispatching a newer commit. Old commits or dirty worktrees fail closed.

The host requires the existing CLI virtual environment at
`$HOME/code/tf-venv/.venv`, jq, flock, and Workshop on PATH. No Testflinger login
is used by this build job. Do not run manual builds, edit source, or copy build
outputs concurrently with CI. GitHub runs are serialized without cancellation;
a host lock covers CI build and snapshot creation.

## Outputs and limitations

Each run builds a fresh nonce and copies an allowlisted bundle to a unique
runner temporary directory. The copy is checksum-checked, checked for clean
source provenance, and passed through the hardware-free agent preflight. The
artifact contains images, manifest, checksum inventory, prepared job, SDK
version, and GitHub run metadata. It does not include credential profiles,
previous job receipts, the entire build tree, or runner configuration.

Build-only runs do not submit a Testflinger job. When **flash_and_test** is
enabled, the runner submits to the restricted nonce queue using the existing
dedicated contributor profile outside the Workshop mount. The Pi agent, not
the GitHub runner, accesses the serial device. The manual hardware proof
previously passed as Testflinger job
`255db8ef-d2f7-457b-be7c-7c5a460a37ff` with sequences 0, 1, 2.

## Flash/test behavior and failure recovery

The helper checks the copied bundle, its GitHub run/commit provenance, the
queue owner and idle agent before submission. It assigns a UUID and records a
durable submission intent under
`~/.local/state/testflinger-demo-runs/<run-id>.json` before the first POST.
It then submits once and uploads exactly the six validated attachments under
the required `test/` archive prefix. No POST is automatically retried.

The helper waits up to ten minutes, downloads bounded artifacts without
extracting arbitrary paths, and requires all three phase exit statuses to be
zero, byte-identical manifest, matching MAC/nonce/source metadata, three
increasing serial sequences, three flash verification messages, and exactly
one write-flash invocation. The final artifact includes `hardware/receipt.json`,
phase results and the agent artifact archive, including logs on failure when
available. Artifact upload runs even if the hardware step fails.

The build summary's 'not submitted' statement describes the build step only;
the separate **Flash and test** summary reports the hardware outcome.

GitHub **Re-run jobs** cannot flash again: attempts after the first are rejected,
and the persistent run-ID ledger also prevents repeats. A timeout or connection
failure can leave a job pending/running or already flashed. Inspect the recorded
job ID and server state before manually cancelling or dispatching a new run.
There is no automatic cancellation, firmware rollback, or retry. A new manual
workflow dispatch is a new authorization to flash; do not use it merely to
recover logs. The saved contributor refresh token must remain valid; reset its
login locally if expired, never use the admin profile as a workaround.

## Trust boundary

This is a persistent desktop runner in a public repository, not a sandbox.
Labels and workflow conditions only route/gate this workflow; they cannot stop
other authorized workflows from using the runner. Only trusted maintainers
should modify or dispatch runner workflows. Never approve untrusted pull
requests to execute on this machine. The runner account has access to host
files, including local lab credentials, even though this workflow does not
read them. Use a dedicated isolated account or ephemeral runner before opening
this setup to less-trusted contributors. Workflow artifacts are not secrets;
the nonce is build correlation data, not authentication or hardware attestation.
