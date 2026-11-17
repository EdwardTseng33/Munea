#!/usr/bin/env bash
# iOS simulator call test (test branch only).
# Installs the simulator build, lets the injected scenario (scripts/ios-sim-scenario.js) drive
# the App, and plays the part of the thumb: sends the App to the background and brings it back.
# Everything is recorded to $OUT (console log, screenshots, summary). Never fails the job on a
# product finding: the point is to see what really happens.
set -uo pipefail

OUT="${OUT:-ios-sim-out}"
APP_PATH="${APP_PATH:?APP_PATH is required}"
BUNDLE="net.munea.app"
mkdir -p "$OUT"
CONSOLE="$OUT/app-console.txt"
: > "$CONSOLE"

echo "== pick simulator =="
UDID="$(xcrun simctl list devices available -j | python3 -c '
import json, sys
d = json.load(sys.stdin)["devices"]
best = None
for runtime, devs in d.items():
    if "iOS" not in runtime:
        continue
    ver = tuple(int(x) for x in runtime.split("iOS-")[-1].split("-") if x.isdigit())
    for dev in devs:
        name = dev.get("name", "")
        if not name.startswith("iPhone") or not dev.get("isAvailable", True):
            continue
        score = (ver, 1 if "Pro" not in name and "Plus" not in name and "SE" not in name and "e" != name[-1] else 0, name)
        if best is None or score > best[0]:
            best = (score, dev["udid"], name, runtime)
print(best[1] if best else "")
sys.stderr.write("picked: %s on %s\n" % (best[2], best[3]) if best else "none\n")
')"
if [ -z "$UDID" ]; then echo "no iPhone simulator available"; xcrun simctl list devices available; exit 1; fi
echo "UDID=$UDID"

xcrun simctl boot "$UDID" || true
xcrun simctl bootstatus "$UDID" -b || true
open -a Simulator --args -CurrentDeviceUDID "$UDID" >/dev/null 2>&1 || true

echo "== install =="
xcrun simctl install "$UDID" "$APP_PATH" || { echo "install failed"; exit 1; }
xcrun simctl privacy "$UDID" grant microphone "$BUNDLE" || true

xcrun simctl spawn "$UDID" log stream --level debug --style compact \
  --predicate 'process == "App" OR process CONTAINS "WebKit" OR eventMessage CONTAINS "MUNEA_SIM"' > "$OUT/oslog.txt" 2>&1 &
OSLOG_PID=$!

shot() { xcrun simctl io "$UDID" screenshot "$OUT/$1.png" >/dev/null 2>&1 || echo "screenshot $1 failed"; }
have() { grep -qE "$1" "$CONSOLE" "$OUT/oslog.txt" 2>/dev/null; }
wait_marker() { # $1 = regex, $2 = timeout seconds
  local i=0
  while [ "$i" -lt "$2" ]; do
    if have "$1"; then echo "  seen: $1 (${i}s)"; return 0; fi
    sleep 1; i=$((i + 1))
  done
  echo "  NOT seen within ${2}s: $1"
  return 1
}
to_background() { xcrun simctl launch "$UDID" com.apple.Preferences >/dev/null 2>&1 || echo "could not open Settings"; }
to_foreground() { xcrun simctl launch "$UDID" "$BUNDLE" >/dev/null 2>&1 || echo "could not bring App back"; }

echo "== launch =="
xcrun simctl launch --console-pty "$UDID" "$BUNDLE" -AppleLanguages "(zh-Hant-TW)" -AppleLocale zh_TW >> "$CONSOLE" 2>&1 &
LAUNCH_PID=$!
sleep 12; shot 01-launch
wait_marker 'MUNEA_SIM BOOT' 90; shot 02-booted

echo "== call 1 (cold start) =="
wait_marker "CALL1_CONSENT_SHEET" 40 && shot 03a-consent-sheet
wait_marker "CALL1_(CONNECTED|DONE)" 90; sleep 3; shot 03-call1-live
wait_marker 'READY_FOR_BACKGROUND_1' 60; shot 04-call1-ended

echo "== background 20s between calls =="
to_background; sleep 4; shot 05-in-background-1; sleep 16
to_foreground
wait_marker 'BACK_FROM_BACKGROUND_1' 30

echo "== call 2 (first call after coming back) =="
wait_marker 'CALL2_(CONNECTED|DONE)' 80; sleep 3; shot 06-call2-live
wait_marker 'CALL2_DONE' 60; shot 07-call2-ended

echo "== native pulse, then call 3 =="
wait_marker 'CALL3_(CONNECTED|DONE)' 90; sleep 3; shot 08-call3-live
wait_marker 'CALL3_DONE' 60

echo "== call 4, leave the screen mid-call for 12s =="
wait_marker 'READY_FOR_BACKGROUND_2' 90; shot 09-call4-live
to_background; sleep 12; shot 10-in-background-2
to_foreground; sleep 3; shot 11-call4-after-return
wait_marker 'CALL4_AFTER_RETURN_LATER' 30; shot 12-call4-after-return-later
wait_marker 'SCENARIO_DONE' 40; shot 13-scenario-done

echo "== tour =="
wait_marker 'TOUR .*"at":"status"' 30 && { sleep 2; shot 14-status; }
wait_marker 'TOUR .*"at":"settings"' 30 && { sleep 2; shot 15-settings; }
wait_marker 'TOUR .*"at":"seat-code"' 30 && { sleep 2; shot 16-seat-code; }
wait_marker 'TOUR_DONE' 30

sleep 2
kill "$LAUNCH_PID" >/dev/null 2>&1 || true
kill "$OSLOG_PID" >/dev/null 2>&1 || true

echo "== summary =="
{
  echo "# MUNEA_SIM lines (console)"
  grep -ao 'MUNEA_SIM .*' "$CONSOLE" | cut -c1-1200
  echo
  echo "# MUNEA_SIM lines (os log, only if console is empty)"
  if ! grep -q 'MUNEA_SIM' "$CONSOLE"; then grep -ao 'MUNEA_SIM .*' "$OUT/oslog.txt" | cut -c1-1200; fi
} > "$OUT/summary.txt"
wc -l "$OUT/summary.txt" "$CONSOLE" "$OUT/oslog.txt"
grep -aE 'MUNEA_SIM (BOOT|NATIVE_|CLOCK_PROBE|CALL._CONNECTED|CALL._DONE|PHASE|CALL4_AFTER|SCENARIO_DONE|JS_ERROR|JS_REJECTION|MISSING)' "$OUT/summary.txt" | cut -c1-400
ls -la "$OUT"
exit 0
