# Live ARM64 upstream charm Docker smoke configuration

Lab-only configuration on `lab/arm64-docker-smoke-config`, separate from the
`feat/agent-host-arm64` contribution branch. This is not an additional charm.
Deploy the already-built Ubuntu 22.04 ARM64 upstream charm with Supervisor.

## Deployment inputs

- config-repo: <https://github.com/bem22/testflinger.git>
- config-branch: lab/arm64-docker-smoke-config
- config-dir: lab/arm64-smoke/agents
- testflinger-server: <http://testflinger.local>

Use one unit in a separate persistent Pi model, for example
`upstream-testflinger-arm64`, and application name `agent-host`. Do not add units
with these same definitions: their server identities would collide.

The guest must resolve `testflinger.local` to the laptop running the server.
Host-only name mappings are not inherited by new LXD containers. The charm's
server URL and the server URLs in both agent definitions must agree.

HTTP is for this trusted lab only: credentials and tokens are unencrypted in
transit. For production, configure HTTPS in both places. This lab also currently
depends on a temporary laptop ingress forwarding repair.

## Credentials

Supply a model-owned Juju secret with `client-id` and `secret-key`, grant it to
`agent-host`, and configure `credentials-secret` with its URI. No credentials or
tokens belong in this repository. The upstream charm writes the shared refresh
token at its default location; both agents use that default. Secret grants in
the retired prototype model do not carry over to the new model.

## Expected behavior

Supervisor should show `pi5-upstream-01` and `pi5-upstream-02` running. Each has
separate execution/results/log directories under the ubuntu user's home, and a
dedicated queue. The command prints its unique marker, hostname, and architecture.

Agent 01 now uses queue `pi5-upstream-docker-smoke-01` and the charm's unchanged
`tf-test` and `tf-cleanup` helpers. The test helper starts the published Jammy
testenv image and installs the guest's device-connector source inside it with
`sudo uv`. The `noprovision` connector runs only its test and no-op cleanup stages;
provisioning remains `/bin/true`. No target device is accessed. Cleanup removes
the named test container. Agent 02 remains the fixed native smoke control.

Submit [job 1](jobs/agent-01.yaml) and [job 2](jobs/agent-02.yaml) with a CLI
configured for the same server. Require each job to complete with test status 0,
the corresponding marker, and `aarch64` output. Confirm both agents return to
waiting. Active Juju status or Supervisor RUNNING alone is insufficient evidence.

Job 1 asserts Docker execution, ARM64, the ubuntu user, and connector-provided
`AGENT_NAME`. It creates `artifacts/docker-smoke.txt`; verify that this file is
present in downloaded job artifacts and that no named container remains after
cleanup. Run job 1 twice to test container-name reuse and cleanup.

Unlike the native baseline, agent 01 now executes job-supplied shell commands.
The lab server permits anonymous submissions: enable this only on a trusted,
access-controlled lab network, not a public endpoint. Upstream's helper mounts
guest source/configuration and SSH material and allows sudo inside the container;
it is not an untrusted-code sandbox. No USB device or Docker socket is passed in.
Both agent processes run as upstream's ubuntu user: separate directories do not
provide security isolation. The test may need outbound package-registry access.

## Activate and roll back

Ensure both agents are waiting and queues are empty before switching the app's
`config-branch` to `lab/arm64-docker-smoke-config`. A config change clones the
definitions, renders helpers, and restarts both agents. The Docker job must not
be submitted until the server reports agent 01 on its new queue. No charm rebuild
or workload source update is needed.

To restore fixed-command behavior, set `config-branch` back to
`lab/arm64-smoke-config` after all jobs finish. This also restores agent 01's
original queue. Do not leave queued Docker jobs behind when rolling back.

## Validation baseline

On 2026-09-23, both native jobs completed with setup/test/cleanup status 0 and
both agents returned to waiting. Job IDs:

- Agent 01: `0c6d0e2d-6dd7-4350-8548-55e166586c5b`
- Agent 02: `2b5e26c4-60aa-4b8d-9a42-31fc15f8f38a`

The Pi guest also ran the Jammy Docker image as ubuntu on ARM64, with
`sudo -n uv --version` reporting uv 0.12.17. Image digest observed:
`sha256:a9ac9063e441bf54f30feb4ceaaa99423aac0329483bc6046f3d2c593c07bf52`.
The upstream helper uses the mutable `jammy` tag, not a pinned digest.
Two consecutive end-to-end Docker jobs passed on 2026-09-23:

- First: `ccd431d1-8afb-4420-9d8d-46745d30f8ac`
- Repeat: `0f7bad91-6766-47a1-846c-5b234e7c6a9f`

Both reached `complete` with setup/test/cleanup status 0. The test assertions
confirmed Docker, ARM64, the ubuntu user, and connector-provided agent identity.
Both artifact archives contained `artifacts/docker-smoke.txt` with the expected
marker and architecture. Cleanup output reported removal of `pi5-upstream-01`;
the second run successfully reused the name with a different container hostname.
Both agents returned to waiting. A direct post-test Docker container listing
has not been collected. Agent 02 was unchanged and waiting, not retested here.

Submission and result/artifact retrieval used this lab's permitted anonymous
contributor API access. The saved CLI agent-role login cannot submit jobs or
download artifacts; no account roles or saved credentials were changed.
USB passthrough, MCU flashing, and hardware tests remain unvalidated.

## Retiring the old prototype

Remove only `lab-agent` from `lab-testflinger-arm64` after any jobs finish.
Keep the controller, server, database, source repositories, and SD backup intact.
Application removal removes unit-local state, so export any needed results first.
The old server-side agent record may remain after removal.
