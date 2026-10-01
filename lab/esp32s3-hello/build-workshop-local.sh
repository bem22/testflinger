#!/bin/bash
# Host-side launcher: only Git metadata is passed, never Git credentials.
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
TF_SOURCE_COMMIT=$(git rev-parse --verify HEAD)
export TF_SOURCE_COMMIT
status=$(git status --porcelain --untracked-files=normal)
export TF_SOURCE_DIRTY=false
if [[ -n "$status" ]]; then
    export TF_SOURCE_DIRTY=true
fi
exec workshop run --non-interactive \
    --env "TF_SOURCE_COMMIT=$TF_SOURCE_COMMIT" \
    --env "TF_SOURCE_DIRTY=$TF_SOURCE_DIRTY" -- build
