#!/usr/bin/env bash
set -euo pipefail

candidate_root="${1:-/root/munea-avatar-candidate}"
candidate_frame_size="${2:-512}"
candidate_port="${3:-8890}"
candidate_release="${4:-1.0.66-first-lip-preserve}"
candidate_video_lead_ms="${5:-0}"
candidate_release_commit="${6:-0d651ba3}"
formal_pid="$(pgrep -fo '/root/flashhead_server.py')"
if [[ -z "${formal_pid}" ]]; then
  echo "formal FlashHead process not found" >&2
  exit 1
fi

while IFS= read -r -d '' entry; do
  export "${entry}"
done < "/proc/${formal_pid}/environ"

export MUNEA_FACE_PORT="${candidate_port}"
export MUNEA_FH_FRAME_SIZE="${candidate_frame_size}"
export MUNEA_FH_VIDEO_LEAD_MS="${candidate_video_lead_ms}"
export MUNEA_FH_SLOTS=1
export MUNEA_FH_PROCS=1
export MUNEA_WORKER_ID="glows-tw06-candidate-${candidate_frame_size}"
export MUNEA_CALL_CONTROL_URL=
export MUNEA_CALL_TOKEN_SECRET=
export MUNEA_CALL_PROTOCOL_REQUIRED=0
export MUNEA_ALLOW_LEGACY_APP_KEY=1
export MUNEA_RELEASE_VERSION="${candidate_release}"
export MUNEA_RELEASE_COMMIT="${candidate_release_commit}"

cd /root/SoulX-FlashHead
exec /root/miniconda3/envs/workenv/bin/python -u "${candidate_root}/flashhead_server.py"
