#!/bin/bash
set -euo pipefail

N="${1:-2}"
CHUNKS="${2:-21}"
MODE="${3:-eager}"
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

PIDS=()
for i in $(seq 1 "$N"); do
  python /workspace/bench_fh.py "$MODE" /root/poc-mandarin.wav "$CHUNKS" \
    > "${OUT}-${i}.log" 2>&1 &
  PIDS+=("$!")
done
for pid in "${PIDS[@]}"; do
  wait "$pid"
done
touch "$DONE"
wait "$MON_PID"

for i in $(seq 1 "$N"); do
  grep '^RESULT ' "${OUT}-${i}.log"
done
echo "GPU_PEAK memory_mib=$(cut -d, -f1 "$MON" | sort -nr | head -1) util_pct=$(cut -d, -f2 "$MON" | sort -nr | head -1) power_w=$(cut -d, -f3 "$MON" | sort -nr | head -1)"
