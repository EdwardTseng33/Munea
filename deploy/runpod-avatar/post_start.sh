#!/usr/bin/env bash
set -euo pipefail

export MUNEA_SERVICE_ROOT="${MUNEA_SERVICE_ROOT:-/workspace/munea-service}"
export MUNEA_RUNTIME_ENV_FILE="${MUNEA_RUNTIME_ENV_FILE:-/etc/rp_environment}"

exec /workspace/munea-service/start-flashhead.sh
