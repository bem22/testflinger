#!/bin/bash
# Host runner entry point: build and snapshot only, never submit or flash.
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
[[ ${GITHUB_REPOSITORY:-} == bem22/testflinger ]]
[[ ${GITHUB_EVENT_NAME:-} == workflow_dispatch ]]
[[ ${GITHUB_REF:-} == refs/heads/lab/workshop-esp32s3-build ]]
[[ ${RUNNER_NAME:-} == freertos-demo ]]
[[ ${GITHUB_SHA:-} =~ ^[0-9a-f]{40}$ ]]
[[ ${GITHUB_RUN_ID:-} =~ ^[0-9]+$ && ${GITHUB_RUN_ATTEMPT:-} =~ ^[0-9]+$ ]]
: "${RUNNER_TEMP:?}" "${GITHUB_OUTPUT:?}" "${GITHUB_STEP_SUMMARY:?}"
[[ -d "$RUNNER_TEMP" ]]
python="$HOME/code/tf-venv/.venv/bin/python"
[[ -x "$python" ]]
mkdir -p build
exec 8>build/.ci.lock
flock -n 8 || { echo 'Another CI build/snapshot is running' >&2; exit 1; }

check_source() {
    [[ "$(git branch --show-current)" == lab/workshop-esp32s3-build ]]
    [[ "$(git rev-parse HEAD)" == "$GITHUB_SHA" ]]
    [[ -z "$(git status --porcelain --untracked-files=normal)" ]]
}
check_source
bash build-workshop-local.sh
check_source

# Copy only this successful build's allowlisted artifacts, not build/ as a whole:
# the project also contains old evidence and an unrelated local CLI profile.
bundle=$(mktemp -d "$RUNNER_TEMP/workshop-esp32s3.XXXXXXXX")
mkdir -p "$bundle/bootloader" "$bundle/partition_table"
for file in bootloader/bootloader.bin partition_table/partition-table.bin \
    tf_s3_hello.bin flasher_args.json flash_args manifest.json SHA256SUMS idf-version.txt; do
    cp -- "build/workshop/$file" "$bundle/$file"
done
(
    cd "$bundle"
    sha256sum --check SHA256SUMS
)
jq -e --arg commit "$GITHUB_SHA" \
    '.source.commit == $commit and .source.dirty == false' "$bundle/manifest.json"
# Revalidate the copied bundle with the same hardware-free agent preflight.
"$python" prepare-workshop-job.py --build "$bundle"
check_source
jq -n --arg run_id "$GITHUB_RUN_ID" --arg attempt "$GITHUB_RUN_ATTEMPT" \
    --arg commit "$GITHUB_SHA" --arg repository "$GITHUB_REPOSITORY" \
    '{repository:$repository,run_id:$run_id,run_attempt:$attempt,commit:$commit,submitted:false}' \
    > "$bundle/github-run.json"
printf 'bundle=%s\n' "$bundle" >> "$GITHUB_OUTPUT"
nonce=$(jq -r .nonce "$bundle/manifest.json")
{
    printf '## Workshop build passed\n\n'
    printf -- '- Source commit: `%s` (clean)\n' "$GITHUB_SHA"
    printf -- '- Build nonce: `%s`\n' "$nonce"
    printf -- '- SDK: ESP-IDF 5.5.3; target: ESP32-S3\n'
    printf -- '- Bundle passed agent-side preflight.\n'
    printf -- '- **Not submitted; no firmware flashed.**\n'
} >> "$GITHUB_STEP_SUMMARY"
