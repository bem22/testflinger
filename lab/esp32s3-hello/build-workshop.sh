#!/bin/bash
# Run inside Workshop via: workshop run --non-interactive -- build
# Build only: no device access, flashing, or Testflinger submission.
set -eo pipefail

cd -- "$(dirname -- "${BASH_SOURCE[0]}")"

# Serialize builds sharing this output directory. Never leave a previous
# success manifest around if a new build fails, including SDK activation.
build_dir="$PWD/build/workshop"
mkdir -p "$build_dir"
exec 9>"$build_dir/.build.lock"
flock -n 9 || { echo 'Another Workshop build is running' >&2; exit 1; }
rm -f "$build_dir/manifest.json" "$build_dir/SHA256SUMS" "$build_dir/idf-version.txt"

# Actions are non-login shells. Load the SDK environment explicitly and fail
# if activation fails, rather than relying on an interactive shell profile.
source /etc/profile.d/freertos-esp-idf.sh
source "${IDF_PATH:?Workshop ESP-IDF SDK is required}/export.sh"

idf_version=$(idf.py --version)
if [[ "$idf_version" != 'ESP-IDF v5.5.3' ]]; then
    printf 'Expected ESP-IDF v5.5.3, got: %s\n' "$idf_version" >&2
    exit 1
fi

# Keep CMake caches and sdkconfig separate from the existing Docker build.
"$IDF_PYTHON_ENV_PATH/bin/python" build_identity.py prepare --project "$PWD" --build "$build_dir"
idf.py -B "$build_dir" -D "SDKCONFIG=$build_dir/sdkconfig" \
    -D "TF_BUILD_IDENTITY_DIR=$build_dir/identity" build

(
    cd "$build_dir"
    # Relative paths make this inventory usable after copying artifacts.
    sha256sum bootloader/bootloader.bin partition_table/partition-table.bin \
        tf_s3_hello.bin flasher_args.json flash_args > SHA256SUMS
    sha256sum --check SHA256SUMS
    printf '%s\n' "$idf_version" > idf-version.txt
)
"$IDF_PYTHON_ENV_PATH/bin/python" build_identity.py finalize --project "$PWD" --build "$build_dir"
printf '\nWorkshop build completed: %s\nNo firmware was flashed or submitted.\n' "$build_dir"