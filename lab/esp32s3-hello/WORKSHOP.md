# Workshop firmware build

This action builds the existing ESP32-S3 hello firmware with the local
FreeRTOS/ESP-IDF Workshop SDK. It does not use the Docker build image, access
the board, flash firmware, or submit a Testflinger job.

## Prerequisites

- An AMD64 Linux host with Workshop and its backend configured.
- The local `freertos-esp-idf` SDK, version 5.5.3, installed using `sdkcraft try`
  from the `freertos-esp-sdk` checkout. The SDK currently declares AMD64 only.
  This definition uses `try-freertos-esp-idf`, not an assumed Store channel.
- Network access for initial base/SDK setup. This is not an offline build claim.

The local SDK's `setup-project` hook invokes `uv` without installing it.
The in-project `build-prereqs` SDK runs first and installs uv 0.8.22 from its
upstream Linux AMD64 release with a pinned SHA-256 checksum. This workaround
changes only this Workshop, not the host or the existing SDK checkout.

## Run

From this directory (the firmware project, not the repository root):

```shell
workshop launch
bash build-workshop-local.sh
```

Launch once. For an existing stopped Workshop, use `workshop start` before
running the action. After changing the definition, use `workshop refresh`.

The explicit `--` separates the action name from the optional Workshop name,
so the same command works non-interactively in a future CI runner.

The host launcher passes the full Git HEAD and repository dirty state to
`workshop run --non-interactive -- build`. No Git credentials or extra host
directories are mounted. Directly invoking the Workshop action still builds,
but records Git commit and dirty state as `null` rather than inventing provenance.
Use the host launcher for the demo and future GitHub runner.

The firmware directory is the Workshop project mounted at `/project`; no
extra host mounts, SSH-agent connections, or hardware resources are requested.

## Outputs

Artifacts are written into the host-visible `build/workshop/` directory:

- `bootloader/bootloader.bin`
- `partition_table/partition-table.bin`
- `tf_s3_hello.bin`
- `flasher_args.json` and `flash_args`
- `SHA256SUMS` and `idf-version.txt`
- `manifest.json`: nonce, serial marker, target, SDK/project versions, build
  timestamps, host-reported Git metadata, source input hashes, and artifact
  paths, sizes, SHA-256 hashes, and flash offsets

The action activates ESP-IDF explicitly, requires version 5.5.3, and checks that
all five expected flash artifacts exist by generating and verifying SHA-256
checksums. Its separate build directory and sdkconfig avoid reusing Docker's
CMake cache or changing the old build outputs.

These hashes are an artifact inventory, not a signature or trusted manifest.
The existing flash job YAML still references the original `build/` outputs,
and its hardware runner accepts only the previously validated fixed hashes.
Do not submit this new output through that job. Use the separate nonce job
preparation helper and runner after satisfying their deployment gates.
Hardware serial validation and GitHub Actions are separate next steps.

The separate manifest-aware runner and non-submitting job preparation helper
are now implemented for offline testing. See
[the nonce runner deployment gates](../arm64-smoke/nonce-demo/README.md)
before attempting a hardware job; the nonce queue has not been deployed.

## Build-time identity

Each action invocation creates a fresh random 128-bit nonce (32 lowercase hex
characters) before compilation. A generated C header embeds it in the app;
changing the header forces recompilation even on an incremental build. It is
not generated at boot, so resetting one firmware image retains its nonce.

Workshop firmware emits once per second:

```text
TF_ESP32S3_HELLO_V2_PASS mac=<STA MAC> nonce=<32 hex characters> seq=<number>
```

The separate nonce runner compares the MAC against its configured board
identity and the nonce against the submitted manifest, and requires three
increasing sequence numbers. The build manifest does not establish that any
device has executed the firmware, and it is not signed or an authorization to
flash. The previous runner and fixed-hash job are unchanged and must not be
used for these new artifacts.

The non-Workshop CMake path retains the V1 marker when no identity directory
is supplied. The original lab worktree and its existing binaries are untouched.

Builds sharing the output directory are serialized using `flock`. A new action
removes the old manifest before doing any work. Finalization checks the target,
flash mapping, SDK version, nonempty artifacts, source changes during the build,
and the presence of the nonce and V2 marker in the application binary. Only
then is the manifest published atomically. Consumers must require it; leftover
binary files alone do not indicate success. Do not edit source files or copy
outputs concurrently with a build.

Git metadata is host-reported, and a dirty checkout is explicitly marked; the
commit alone does not describe uncommitted changes. The manifest hashes the
firmware CMake files, main sources, defaults, build scripts and project SDK
files, not the entire repository or the installed SDK. It is an inventory for
a trusted lab, not a reproducible-build attestation.

Offline helper tests (using a host Python 3 environment):

```shell
python3 -m unittest -v test_build_identity
```

To stop the build environment when finished:

```shell
workshop stop
```

## Validation (2026-10-01, original V1 baseline)

Workshop 0.1.29 reached `Ready` on the AMD64 laptop with Ubuntu 24.04 and the
local ESP-IDF v5.5.3 SDK. Both the initial build and a second, incremental
`workshop run --non-interactive -- build` completed successfully. The generated
project metadata identifies target `esp32s3`, project `tf_s3_hello`, version
`1.0.0`. All five artifact checksum checks passed on both invocations.

Binary sizes: bootloader 20,832 bytes, partition table 3,072 bytes, application
180,368 bytes. No flashing or Testflinger submission was performed.

The SDK reports missing Git metadata and falls back to its source version;
this warning did not prevent either build.

### V2 nonce and manifest validation

Ten offline identity tests passed. Two Workshop builds completed with different
nonces and different application SHA-256 hashes. Inspection of the second app
binary found its expected nonce and no copy of the first nonce:

- First nonce: `eec44da50fb280baba90908e263f4bee`
- Second nonce: `a49206474cccf09a405aafc01b1799ac`
- V2 application size: 180,416 bytes
- Manifest Git HEAD: `3035cd9b889cce9145def9829dee7e6e1a27adb4`, dirty: `true`

These values are validation examples, not fixed expected values for future
builds. Hardware execution and MAC/nonce serial matching remain untested.

### Local networking prerequisite

Initial setup stalled because the host's nft-backed iptables `FORWARD` policy
was `DROP`, with Docker-user exceptions for `lxdbr0` but not `workshopbr0`.
DNS worked, while container HTTPS to GitHub and PyPI timed out. The user added
temporary `DOCKER-USER` rules scoped to this container's IPv4 address
`10.116.53.184/32`, allowing outbound TCP ports 80/443 through `wlp0s20f3` and
established/related return traffic. GitHub then returned HTTP 200 and the
paused launch completed with `workshop launch --continue esp32s3-build`.

These host rules are not installed by this project and are not a permanent
network configuration. Recheck the container IP and uplink if connectivity
fails after recreation or network changes; do not flush firewall rules or
change the global forwarding policy. Use `workshop changes` and `workshop tasks`
to distinguish setup progress from a paused failure before triggering a build.
