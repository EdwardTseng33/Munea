#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

missing=0

section() {
  printf '\n== %s ==\n' "$1"
}

check_cmd() {
  local name="$1"
  local hint="$2"
  if command -v "$name" >/dev/null 2>&1; then
    printf 'PASS %s: %s\n' "$name" "$(command -v "$name")"
  else
    printf 'MISSING %s: %s\n' "$name" "$hint"
    missing=1
  fi
}

section "Required command line tools"
check_cmd git "Install Git or Xcode Command Line Tools."
check_cmd node "Install Node.js 22+."
check_cmd npm "Install npm with Node.js."
check_cmd npx "Install npm/npx with Node.js."

section "Python runtime"
if command -v python3 >/dev/null 2>&1; then
  python_version="$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:3])))')"
  if python3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)'; then
    printf 'PASS python3: %s (%s)\n' "$(command -v python3)" "$python_version"
  else
    printf 'MISSING python3 3.10+: found %s. Install Python 3.12 before running release checks.\n' "$python_version"
    missing=1
  fi
else
  printf 'MISSING python3: install Python 3.12 before running release checks.\n'
  missing=1
fi

section "PowerShell for repo smoke scripts"
if command -v pwsh >/dev/null 2>&1; then
  printf 'PASS pwsh: %s\n' "$(command -v pwsh)"
elif command -v powershell >/dev/null 2>&1; then
  printf 'PASS powershell: %s\n' "$(command -v powershell)"
else
  printf 'MISSING pwsh/powershell: install PowerShell so npm run smoke:no-api and release:check can run on Mac.\n'
  printf 'Hint: brew install --cask powershell\n'
  missing=1
fi

section "Xcode"
if command -v xcodebuild >/dev/null 2>&1; then
  xcodebuild -version
else
  printf 'MISSING xcodebuild: install Xcode and open it once to accept setup.\n'
  missing=1
fi

if command -v xcrun >/dev/null 2>&1; then
  if xcrun simctl help >/dev/null 2>&1; then
    printf 'PASS xcrun simctl is available.\n'
  else
    printf 'WARN xcrun exists but simctl is not ready. Open Xcode once and finish setup.\n'
  fi
fi

section "Repo state"
git rev-parse --show-toplevel
git status --short --branch

section "Capacitor config"
node -e "const fs=require('fs'); const c=JSON.parse(fs.readFileSync('capacitor.config.json','utf8')); console.log('appId=' + c.appId); console.log('appName=' + c.appName); console.log('webDir=' + c.webDir);"

if [ -d "ios/App" ]; then
  printf 'PASS ios/App exists. Next: npm run cap:sync && npm run cap:open:ios\n'
else
  printf 'INFO ios/App does not exist yet. Next on Mac: npm install && npm run cap:add:ios\n'
fi

section "Next commands on Mac"
cat <<'EOF'
1. npm install
2. python3 -m venv .venv && .venv/bin/python -m pip install -r engine/requirements.txt
3. npm run mac:doctor
4. npm run smoke:no-api
5. npm run test:launch
6. npm run cap:doctor
7. npm run cap:add:ios   # skip if ios/App already exists
8. npm run cap:sync
9. npm run cap:open:ios
EOF

if [ "$missing" -ne 0 ]; then
  printf '\nMac day-one check finished with missing prerequisites.\n'
  exit 1
fi

printf '\nMac day-one check passed.\n'
