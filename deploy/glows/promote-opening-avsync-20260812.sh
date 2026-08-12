#!/usr/bin/env bash
set -euo pipefail

backup="/root/munea-backup-before-opening-avsync-20260812-$(date +%H%M%S)"
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

upsert_env() {
  local name="$1"
  local value="$2"
  if grep -qE "^(export )?${name}=" "${env_file}"; then
    sed -i -E "s|^(export )?${name}=.*|export ${name}=${value}|" "${env_file}"
  else
    printf 'export %s=%s\n' "${name}" "${value}" >>"${env_file}"
  fi
}

upsert_env MUNEA_FH_SLOTS 2
upsert_env MUNEA_FH_FRAME_SIZE 512
upsert_env MUNEA_FH_OUTPUT_FRAME_SIZE 640
upsert_env MUNEA_FH_OUTPUT_SHARPEN 1
upsert_env MUNEA_FH_VIDEO_LEAD_MS -350
upsert_env MUNEA_RELEASE_VERSION 1.0.67-opening-avsync
upsert_env MUNEA_RELEASE_COMMIT dc87c152

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
