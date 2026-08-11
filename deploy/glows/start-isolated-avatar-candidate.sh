#!/usr/bin/env bash
set -euo pipefail

candidate_root="${1:-/root/munea-candidate-640}"
formal_pid="$(pgrep -fo '/root/flashhead_server.py')"
if [[ -z "${formal_pid}" ]]; then
  echo "formal FlashHead process not found" >&2
  exit 1
fi

while IFS= read -r -d '' entry; do
  export "${entry}"
done < "/proc/${formal_pid}/environ"

export MUNEA_FACE_PORT=8890
export MUNEA_FH_FRAME_SIZE=640
export MUNEA_FH_SLOTS=1
export MUNEA_FH_PROCS=1
export MUNEA_WORKER_ID=glows-tw06-candidate640
export MUNEA_CALL_CONTROL_URL=
export MUNEA_CALL_TOKEN_SECRET=
export MUNEA_CALL_PROTOCOL_REQUIRED=0
export MUNEA_ALLOW_LEGACY_APP_KEY=1
export MUNEA_RELEASE_VERSION=1.0.66-candidate
export MUNEA_RELEASE_COMMIT=codex-fix-1.0.65-call-start-avsync-20260812

cd /root/SoulX-FlashHead
exec /root/miniconda3/envs/workenv/bin/python -u "${candidate_root}/flashhead_server.py"
