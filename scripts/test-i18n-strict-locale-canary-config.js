'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');

function read(filePath) {
  return fs.readFileSync(filePath, 'utf8').replace(/\r\n/g, '\n');
}

const canaryDeploy = read('deploy/cloudrun/canary-deploy.sh');
const canaryVerify = read('deploy/cloudrun/canary-verify.sh');
const promote = read('deploy/cloudrun/promote.sh');
const prodDeploy = read('deploy/cloudrun/prod-deploy.sh');
const gatewayDeploy = read('scripts/cloud-run-deploy-gateway.ps1');
const integration = JSON.parse(read('engine/voice-locale-integration-manifest.json'));

assert.match(
  canaryDeploy,
  /MUNEA_VOICE_ALLOW_LEGACY_LOCALE_CONTEXT:-1/,
  'Staging canary must preserve compatibility unless strict mode is explicit',
);
assert.match(
  canaryDeploy,
  /VOICE_ALLOW_LEGACY_LOCALE_CONTEXT" = "0"[\s\S]*VOICE_CALL_CONTROL_REQUIRED" != "1"/,
  'Strict Voice locale context must require Call Control',
);
assert.match(
  canaryDeploy,
  /MUNEA_VOICE_ALLOW_LEGACY_LOCALE_CONTEXT=\$VOICE_ALLOW_LEGACY_LOCALE_CONTEXT/,
  'Voice canary revision must record the selected locale mode',
);
assert.match(
  canaryDeploy,
  /strict LocaleContext canary 僅供 0% 驗收[\s\S]*promote\.sh 會拒絕切流量/,
  'Strict canary must not advertise a traffic-promotion command',
);

assert.match(canaryVerify, /EXPECTED_LOCALE_MODE="\$\{6:-\}"/);
assert.match(canaryVerify, /MUNEA_VOICE_ALLOW_LEGACY_LOCALE_CONTEXT/);
assert.match(canaryVerify, /strict LocaleContext revision 沒有同時要求 Call Control/);
assert.match(canaryVerify, /locale_mode=\$LOCALE_MODE/);

const strictPromotionGuard = promote.indexOf(
  'strict LocaleContext revision 目前只允許 0% canary 驗收',
);
const trafficMutation = promote.indexOf('run services update-traffic');
assert.ok(strictPromotionGuard >= 0, 'Promotion must reject strict Voice revisions');
assert.ok(
  trafficMutation < 0 || strictPromotionGuard < trafficMutation,
  'Strict Voice rejection must run before any traffic mutation',
);

assert.match(
  prodDeploy,
  /MUNEA_VOICE_ALLOW_LEGACY_LOCALE_CONTEXT=1/,
  'Production Voice deploy must explicitly preserve compatibility mode',
);
assert.match(
  prodDeploy,
  /VERIFY_LOCALE_MODE="compatibility"/,
  'Production verification must bind the expected compatibility mode',
);

assert.match(gatewayDeploy, /\[switch\]\$StrictLocaleContext/);
assert.match(
  gatewayDeploy,
  /\$StrictLocaleContext -and \$AllowTraffic/,
  'Strict Gateway mode must reject direct traffic deployment',
);
assert.match(
  gatewayDeploy,
  /MUNEA_GATEWAY_ALLOW_LEGACY_LOCALE_CONTEXT = if \(\$StrictLocaleContext\) \{ "0" \} else \{ "1" \}/,
  'Gateway canary revision must record strict or compatibility mode',
);
assert.match(gatewayDeploy, /if \(-not \$AllowTraffic\) \{ \$argsList \+= "--no-traffic" \}/);

assert.equal(
  integration.legacyTokenMode,
  'compatibility',
  'Repository release gate must stay blocked until strict canary and exact-build App E2E pass',
);
assert.equal(integration.appE2EStatus, 'pending');

console.log(
  'i18n strict LocaleContext canary config PASS: explicit opt-in, 0% only, promotion blocked',
);
