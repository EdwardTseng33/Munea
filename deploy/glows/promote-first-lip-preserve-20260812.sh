#!/usr/bin/env bash
set -euo pipefail

backup=/root/munea-backup-before-first-lip-preserve-20260812-0449
server=/root/flashhead_server.py
core=/root/flashhead_engine_core.py
env_file=/root/munea-face.env
python_bin=/root/miniconda3/envs/workenv/bin/python
runtime_dir=/root/SoulX-FlashHead

formal_pid="$(pgrep -fo "${python_bin} -u ${server}")"
formal_cmd="$(ps -p "${formal_pid}" -o args=)"
if [[ "${formal_cmd}" != "${python_bin} -u ${server}" ]]; then
  echo "unexpected formal process: ${formal_cmd}" >&2
  exit 1
fi
test -s "${server}.next"
test -s "${core}.next"

mkdir -p "${backup}"
cp -a "${server}" "${core}" "${env_file}" "${backup}/"

mapfile -t candidate_pids < <(pgrep -f "/root/munea-avatar-candidate-0c0028f7/flashhead_server.py" || true)
for candidate_pid in "${candidate_pids[@]}"; do
  kill "${candidate_pid}"
done

kill "${formal_pid}"
for _ in $(seq 1 15); do
  kill -0 "${formal_pid}" 2>/dev/null || break
  sleep 1
done
if kill -0 "${formal_pid}" 2>/dev/null; then
  echo "formal process did not stop" >&2
  exit 1
fi

install -m 0644 "${server}.next" "${server}"
install -m 0644 "${core}.next" "${core}"
sed -i -E \
  -e 's|^export MUNEA_FH_VIDEO_LEAD_MS=.*|export MUNEA_FH_VIDEO_LEAD_MS=-80|' \
  -e 's|^export MUNEA_RELEASE_VERSION=.*|export MUNEA_RELEASE_VERSION=1.0.66-first-lip-preserve|' \
  -e 's|^(export )?MUNEA_RELEASE_COMMIT=.*|export MUNEA_RELEASE_COMMIT=0d651ba3|' \
  "${env_file}"

start_formal() {
  cd "${runtime_dir}"
  set -a
  # shellcheck disable=SC1090
  source "${env_file}"
  set +a
  nohup "${python_bin}" -u "${server}" > /root/flashhead.log 2>&1 &
  started_pid=$!
}

rollback() {
  echo "promotion failed; restoring ${backup}" >&2
  cp -a "${backup}/flashhead_server.py" "${server}"
  cp -a "${backup}/flashhead_engine_core.py" "${core}"
  cp -a "${backup}/munea-face.env" "${env_file}"
  start_formal
  echo "rollback_pid=${started_pid}" >&2
}

start_formal
for _ in $(seq 1 75); do
  if ! kill -0 "${started_pid}" 2>/dev/null; then
    rollback
    exit 1
  fi
  if ss -ltnp | grep -q ':8888'; then
    echo "promoted_pid=${started_pid} backup=${backup}"
    exit 0
  fi
  sleep 1
done

kill "${started_pid}" 2>/dev/null || true
rollback
exit 1
