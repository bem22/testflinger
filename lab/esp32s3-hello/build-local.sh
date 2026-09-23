#!/bin/bash
# Uses the existing laptop image by immutable local image ID, not a moving tag.
# No network, USB device, or Docker socket is exposed to the build container.
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
docker run --rm --network none \
    --user "$(id -u):$(id -g)" \
    --mount "type=bind,src=$PWD,dst=/project" \
    --workdir /project \
    sha256:7e26ff11c758e5b93cb8303cbe27a8e658ed362e89bbb798d4f8eeefc1e3a092 \
    bash -lc 'source "$IDF_PATH/export.sh" >/dev/null && idf.py build'
