# Pi nonce deployment branch

This branch selects the nonce queue and test wrapper for agent 01. Unlike the
build branch, its canonical agent configuration is intended for deployment.
Agent 02's configuration is unchanged. The opt-in implementation and historical
readiness notes are in README.md; this document describes the deployment delta.

- Config repository: https://github.com/bem22/testflinger.git
- Deployment branch: `lab/workshop-esp32s3-nonce-config`
- Config directory: `lab/arm64-smoke/agents`
- Target: `agent-host` in Pi model `upstream-testflinger-arm64`
- Build-source commit: `89d1c62a1f43c4f2fa6986c9ec31c6bb4bce3084`
- Original configured branch: `lab/esp32s3-flash-hello-v2-config`
- Observed deployed revision before the change:
  `98a83e8e806d0da306960682254433fed09ecf9a`
- Exact rollback branch: `lab/pi5-pre-nonce-20261001`

The supported charm config update signals **all running agents** with USR1 to
restart when idle. The user approved agent 02's idle restart, but not changes
to its configuration. Stop idle agent 01 before updating the branch; start it
only after verifying deployed file hashes and the restricted queue owner
`workshop-demo-submitter`. Do not submit firmware as part of configuration
deployment. Existing build artifacts are not committed or deployed here.

## Rollback

Check both queues and agents for active work. Stop idle agent 01, set the charm's
`config-branch` to `lab/pi5-pre-nonce-20261001`, wait for the config-changed hook
to finish successfully, verify revision and configuration, then start agent 01.
This again permits agent 02 to restart when idle. The old configured branch
has the same agent configuration but a later repository revision; use the
rollback branch above when exact restoration is required.

Rollback restores the original fixed-hash queue and wrapper, not firmware.
Neither deploying nor rolling back this configuration flashes the device.