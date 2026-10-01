# Manual Workshop build on the local runner

The repository runner `freertos-demo` uses the existing Workshop on the AMD64
host. Add the custom runner label `workshop-esp32s3` in the repository's Actions
runner settings. Keep the runner process running under the same host account
that owns Workshop. Workshop must already be Ready; the workflow does not
recreate containers or alter host networking.

## Run a build

1. Open Actions in `bem22/testflinger` and select **Workshop ESP32-S3 build**.
2. Select **Run workflow**, then branch **lab/workshop-esp32s3-build**.
3. Start the run and inspect its build summary and uploaded artifact.

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

The prepared Testflinger job is **not submitted**. This workflow does not access
the serial device, change agent configuration, or flash the board. End-to-end
CI submission and result verification are a separate follow-up to this first
runner build. The manual hardware proof previously passed as Testflinger job
`255db8ef-d2f7-457b-be7c-7c5a460a37ff` with sequences 0, 1, 2.

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
