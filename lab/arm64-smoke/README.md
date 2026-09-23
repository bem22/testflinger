# Live ARM64 upstream charm smoke configuration

Lab-only configuration on `lab/arm64-smoke-config`, separate from the
`feat/agent-host-arm64` contribution branch. This is not an additional charm.
Deploy the already-built Ubuntu 22.04 ARM64 upstream charm with Supervisor.

## Deployment inputs

- config-repo: <https://github.com/bem22/testflinger.git>
- config-branch: lab/arm64-smoke-config
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

Submit [job 1](jobs/agent-01.yaml) and [job 2](jobs/agent-02.yaml) with a CLI
configured for the same server. Require each job to complete with test status 0,
the corresponding marker, and `aarch64` output. Confirm both agents return to
waiting. Active Juju status or Supervisor RUNNING alone is insufficient evidence.

No device connector, Docker test environment, flashing, or job-supplied shell
command is exercised here. Use only trusted, hardware-free smoke jobs. Both
processes run as upstream's ubuntu user: separate directories do not provide
security isolation. Changes to repository configuration/actions may restart
agents and interrupt jobs; schedule them accordingly.

## Retiring the old prototype

Remove only `lab-agent` from `lab-testflinger-arm64` after any jobs finish.
Keep the controller, server, database, source repositories, and SD backup intact.
Application removal removes unit-local state, so export any needed results first.
The old server-side agent record may remain after removal.
