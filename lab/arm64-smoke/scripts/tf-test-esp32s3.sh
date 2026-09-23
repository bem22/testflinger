#!/bin/bash
# Lab-only counterpart of tf-test: one serial device, no SSH/source write mounts.
# The unchanged upstream tf-cleanup removes the named container after this phase.
set -euo pipefail

if [[ ${agent_id:-} != pi5-upstream-01 || ${provision_type:-} != noprovision ]]; then
    echo 'This wrapper is only for pi5-upstream-01 with noprovision.' >&2
    exit 2
fi

device=/dev/esp32s3
config_dir=/srv/agent-configs/lab/arm64-smoke/agents/pi5-upstream-01
source_dir=/srv/testflinger/device-connectors
image=ghcr.io/canonical/testflinger/testflinger-testenv@sha256:a9ac9063e441bf54f30feb4ceaaa99423aac0329483bc6046f3d2c593c07bf52

if [[ ! -c $device || ! -r $device || ! -w $device ]]; then
    echo 'Selected ESP32-S3 serial device is absent or inaccessible.' >&2
    exit 2
fi
[[ -f $PWD/testflinger.json && -f $PWD/device-connector-error.json ]]
mkdir -p "$PWD/attachments"

# Preserve the test status while still attempting to collect failure artifacts.
test_status=0
docker run -t --name "$agent_id" \
    --device="$device:$device:rw" \
    --workdir /home/ubuntu \
    --mount "type=bind,src=$PWD/testflinger.json,dst=/home/ubuntu/testflinger.json,readonly" \
    --mount "type=bind,src=$PWD/device-connector-error.json,dst=/home/ubuntu/device-connector-error.json" \
    --mount "type=bind,src=$PWD/attachments,dst=/home/ubuntu/attachments,readonly" \
    --mount "type=bind,src=$source_dir,dst=/srv/testflinger/device-connectors,readonly" \
    --mount "type=bind,src=$config_dir,dst=/config,readonly" \
    "$image" \
    bash -c 'set -euo pipefail
      mkdir -p artifacts
      sudo -n uv pip install --system /srv/testflinger/device-connectors esptool==4.8.1
      PYTHONUNBUFFERED=1 testflinger-device-connector noprovision runtest \
        -c /config/default.yaml testflinger.json' || test_status=$?

artifact_status=0
docker cp "$agent_id:/home/ubuntu/artifacts" "$PWD/" || artifact_status=$?
if (( test_status != 0 )); then
    exit "$test_status"
fi
exit "$artifact_status"