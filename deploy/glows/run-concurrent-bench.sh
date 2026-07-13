#!/bin/bash
set -euo pipefail

N="${1:-2}"
CHUNKS="${2:-21}"
MODE="${3:-eager}"
PY="${PY:-/root/miniconda3/envs/workenv/bin/python}"
OUT="/workspace/bench-${N}way-${MODE}"
MON="${OUT}-gpu.csv"
DONE="${OUT}.done"

rm -f "${OUT}"-*.log "$MON" "$DONE"
(
  while [ ! -f "$DONE" ]; do
    nvidia-smi --query-gpu=memory.used,utilization.gpu,power.draw \
      --format=csv,noheader,nounits >> "$MON"
    sleep 0.2
  done
) &
MON_PID=$!
cleanup() {
  touch "$DONE"
  kill "$MON_PID" 2>/dev/null || true
  wait "$MON_PID" 2>/dev/null || true
}
trap cleanup EXIT

PIDS=()
for i in $(seq 1 "$N"); do
  "$PY" /workspace/bench_fh.py "$MODE" /root/poc-mandarin.wav "$CHUNKS" \
    > "${OUT}-${i}.log" 2>&1 &
  PIDS+=("$!")
done
STATUS=0
for pid in "${PIDS[@]}"; do
  wait "$pid" || STATUS=$?
done
touch "$DONE"
wait "$MON_PID"
trap - EXIT

for i in $(seq 1 "$N"); do
  if ! grep '^RESULT ' "${OUT}-${i}.log"; then
    echo "RESULT_MISSING worker=$i"
    tail -20 "${OUT}-${i}.log"
  fi
done
echo "GPU_PEAK memory_mib=$(cut -d, -f1 "$MON" | sort -nr | head -1) util_pct=$(cut -d, -f2 "$MON" | sort -nr | head -1) power_w=$(cut -d, -f3 "$MON" | sort -nr | head -1)"
exit "$STATUS"
