const assert = require('assert');
const fs = require('fs');

function read(path) {
  return fs.readFileSync(path, 'utf8').replace(/\r\n/g, '\n');
}

function expectExitBeforeMutation(path, mutationPattern) {
  const source = read(path);
  const exit = source.search(/(?:^|\n)\s*(?:exit 1|exit \/b 1)\s*(?:\n|$)/i);
  const mutation = source.search(mutationPattern);
  assert.ok(exit >= 0, `${path} must fail closed with exit 1`);
  assert.ok(mutation < 0 || exit < mutation, `${path} can reach a mutating command before its fail-closed exit`);
}

const topology = read('deploy/cloudrun/SERVICE-TOPOLOGY.md');
const canaryDeploy = read('deploy/cloudrun/canary-deploy.sh');
const prodDeploy = read('deploy/cloudrun/prod-deploy.sh');
const promote = read('deploy/cloudrun/promote.sh');
const verify = read('deploy/cloudrun/canary-verify.sh');
const app = read('web/src/app.js');
const store = read('web/src/store.js');
const notify = read('web/src/notify.js');
const devProfile = read('scripts/enable-ios-development-profile.mjs');

assert.match(topology, /Status: `authority`/);
assert.match(topology, /production[^\n]*`munea-brain`[^\n]*`munea-voice`/);
assert.match(topology, /staging[^\n]*`munea-brain-staging`[^\n]*`munea-voice-staging`/);
assert.match(topology, /Operations console/);
assert.match(topology, /--to-latest[^\n]*prohibited/);

assert.match(canaryDeploy, /brain\) SVC="munea-brain-staging"/);
assert.match(canaryDeploy, /voice\) SVC="munea-voice-staging"/);
assert.match(canaryDeploy, /MUNEA_ENV_NAME=staging/);
assert.match(canaryDeploy, /--no-traffic/);
assert.match(canaryDeploy, /promote\.sh staging \$WHAT \$TAG \$RELEASE_VERSION \$RELEASE_COMMIT/);
assert.doesNotMatch(canaryDeploy, /update-traffic|--to-revisions|--to-latest/);

assert.match(prodDeploy, /brain\) SVC="munea-brain"/);
assert.match(prodDeploy, /voice\) SVC="munea-voice"/);
assert.match(prodDeploy, /MUNEA_ENV_NAME=production/);
assert.match(prodDeploy, /--no-traffic/);
assert.match(prodDeploy, /promote\.sh production \$WHAT \$TAG \$RELEASE_VERSION \$RELEASE_COMMIT/);
assert.doesNotMatch(prodDeploy, /update-traffic|--to-revisions|--to-latest/);

assert.match(promote, /staging:brain\) SVC="munea-brain-staging"/);
assert.match(promote, /staging:voice\) SVC="munea-voice-staging"/);
assert.match(promote, /production:brain\) SVC="munea-brain"/);
assert.match(promote, /production:voice\) SVC="munea-voice"/);
assert.match(promote, /canary-verify\.sh "\$WHAT" "\$TAG" "\$PROFILE" "\$EXPECTED_VERSION" "\$EXPECTED_COMMIT"/);
assert.match(promote, /--to-revisions "\$TARGET_REVISION=100"/);
assert.match(promote, /--to-revisions "\$PREVIOUS_REVISION=100"/);
assert.match(promote, /serving_release_mismatch/);
assert.match(promote, /TARGET_REVISION" = "\$VERIFIED_REVISION/);
assert.match(promote, /CURRENT_SERVING_REVISION" = "\$PREVIOUS_REVISION/);
assert.match(promote, /PROMOTION_OK=0/);
assert.match(promote, /ROLLBACK_OK=0/);
assert.doesNotMatch(promote, /--to-latest/);

assert.match(verify, /staging:brain\).*EXPECTED_ENV="staging".*EXPECTED_SERVICE="munea-brain"/);
assert.match(verify, /staging:voice\).*EXPECTED_ENV="staging".*EXPECTED_SERVICE="munea-voice"/);
assert.match(verify, /production:brain\).*SVC="munea-brain".*EXPECTED_ENV="production"/);
assert.match(verify, /production:voice\).*SVC="munea-voice".*EXPECTED_ENV="production"/);

const prodBrain = 'https://munea-brain-491603544409.asia-east1.run.app';
const prodVoice = 'wss://munea-voice-491603544409.asia-east1.run.app';
assert.ok(app.includes(`const BRAIN_URL_DEFAULT = '${prodBrain}'`));
assert.ok(app.includes(`const LIVE_VOICE_URL_DEFAULT = '${prodVoice}'`));
assert.ok(store.includes(`var BRAIN_URL = '${prodBrain}'`));
assert.ok(notify.includes(`var BRAIN_URL_DEFAULT = '${prodBrain}'`));
assert.ok(devProfile.includes("brainUrl: 'https://munea-brain-staging-491603544409.asia-east1.run.app'"));
assert.ok(devProfile.includes("voiceUrl: 'wss://munea-voice-staging-491603544409.asia-east1.run.app'"));

expectExitBeforeMutation('deploy/cloudrun/更新正式環境.sh', /gcloud\s+run\s+(?:deploy|services\s+update-traffic)/i);
expectExitBeforeMutation('deploy/cloudrun/更新測試環境.sh', /gcloud\s+run\s+(?:deploy|services\s+update-traffic)/i);
expectExitBeforeMutation('scripts/cloud-run-deploy-staging.ps1', /["']run["']\s*,\s*["']deploy["']/i);
expectExitBeforeMutation('deploy/cloudrun/正式開門-點兩下.bat', /run services add-iam-policy-binding/i);
expectExitBeforeMutation('deploy/cloudrun/發鑰匙權限-點兩下.bat', /secrets add-iam-policy-binding/i);

console.log('Cloud Run topology contract PASS: environment roles, exact revision promotion, App defaults, and retired entrypoints');
