#!/bin/bash
# Laptop convenience launcher; packaging/submission is done by the real CLI.
set -euo pipefail
base=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
cli=${TESTFLINGER_LAB_CLI:-$HOME/code/tf-venv/.venv/bin/testflinger-cli}
if [[ ! -x $cli ]]; then
    echo 'Set TESTFLINGER_LAB_CLI to the installed non-snap testflinger-cli executable.' >&2
    exit 2
fi
# A non-snap CLI honors these paths; the snap launcher overwrites XDG variables.
# Keep the saved agent-role snap login untouched and use an independent lab profile.
export XDG_CONFIG_HOME="$base/build/cli-profile/config"
export XDG_DATA_HOME="$base/build/cli-profile/data"
export XDG_STATE_HOME="$base/build/cli-profile/state"
export XDG_CACHE_HOME="$base/build/cli-profile/cache"
mkdir -p "$XDG_CONFIG_HOME" "$XDG_DATA_HOME" "$XDG_STATE_HOME" "$XDG_CACHE_HOME"
unset TESTFLINGER_CLIENT_ID TESTFLINGER_SECRET_KEY
exec "$cli" --server http://testflinger.local "$@"