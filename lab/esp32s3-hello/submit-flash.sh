#!/bin/bash
# Run on the laptop only after the Pi has registered the new queue.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
server=http://testflinger.local
bundle=build/esp32s3-hello-v1.tar.gz
job=../arm64-smoke/jobs/flash-hello.json
receipt=build/flash-job-id.txt

if [[ -e $receipt ]]; then
    echo "A submission receipt already exists: $receipt. Inspect that job; do not blindly reflash." >&2
    exit 2
fi
printf '%s  %s\n' c237b999de5a413cdcaed912d9aa81f3fffab3239e938e09bc31d18735234c57 "$bundle" | sha256sum --check --strict
curl -fsS --max-time 15 "$server/v1/agents/data/pi5-upstream-01" |
    jq -e '.state == "waiting" and (.queues | index("pi5-esp32s3-flash-hello-01") != null)' >/dev/null

# No retry on submission: an ambiguous network failure might already have created a job.
response=$(curl -fsS --max-time 30 -H 'Content-Type: application/json' \
    --data-binary "@$job" "$server/v1/job")
job_id=$(jq -er '.job_id | select(test("^[0-9a-f]{8}-[0-9a-f-]{27}$"))' <<< "$response")
# Keep the receipt even if attachment upload fails: resume that job, never resubmit.
printf '%s\n' "$job_id" | tee "$receipt"
curl -fsS --max-time 120 -F "file=@$bundle;type=application/gzip" \
    "$server/v1/job/$job_id/attachments"
printf '\nSubmitted one flash job: %s\n' "$job_id"