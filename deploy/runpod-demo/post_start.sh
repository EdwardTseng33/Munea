#!/usr/bin/env bash
set -euo pipefail

ROOT="${MUNEA_DEMO_ROOT:-/workspace/munea-demo}"
exec "$ROOT/current/manage-demo.sh" start
