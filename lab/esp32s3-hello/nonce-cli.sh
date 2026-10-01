#!/bin/bash
# Dedicated contributor profile, outside the directory mounted by Workshop.
# Never use the admin profile for firmware submission.
set -euo pipefail
cli=${TESTFLINGER_LAB_CLI:-$HOME/code/tf-venv/.venv/bin/testflinger-cli}
if [[ ! -x $cli ]]; then
    echo 'Set TESTFLINGER_LAB_CLI to the installed non-snap CLI.' >&2
    exit 2
fi
profile="$HOME/.local/state/testflinger-demo-submitter"
export XDG_CONFIG_HOME="$profile/config"
export XDG_DATA_HOME="$profile/data"
export XDG_STATE_HOME="$profile/state"
export XDG_CACHE_HOME="$profile/cache"
umask 077
mkdir -p "$XDG_CONFIG_HOME" "$XDG_DATA_HOME" "$XDG_STATE_HOME" "$XDG_CACHE_HOME"
unset TESTFLINGER_CLIENT_ID TESTFLINGER_SECRET_KEY
exec "$cli" --server http://testflinger.local "$@"
