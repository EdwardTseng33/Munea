const assert = require('assert');
const fs = require('fs');

const deploy = fs.readFileSync('deploy/cloudrun/canary-deploy.sh', 'utf8');
const prodDeploy = fs.readFileSync('deploy/cloudrun/prod-deploy.sh', 'utf8');
const verify = fs.readFileSync('deploy/cloudrun/canary-verify.sh', 'utf8');
const promote = fs.readFileSync('deploy/cloudrun/promote.sh', 'utf8');

assert.match(deploy, /--no-traffic/);
assert.match(deploy, /canary-verify\.sh "\$WHAT" "\$TAG" staging "\$RELEASE_VERSION" "\$RELEASE_COMMIT"/);
assert.doesNotMatch(deploy, /update-traffic|--to-latest/);

assert.match(prodDeploy, /RELEASE_COMMIT="\$\(git rev-parse HEAD\)"/);
assert.match(prodDeploy, /git archive --format=tar "\$RELEASE_COMMIT"/);
assert.strictEqual((prodDeploy.match(/MUNEA_RELEASE_VERSION=\$RELEASE_VERSION/g) || []).length, 2);
assert.strictEqual((prodDeploy.match(/MUNEA_RELEASE_COMMIT=\$RELEASE_COMMIT/g) || []).length, 2);
assert.match(prodDeploy, /canary-verify\.sh "\$WHAT" "\$TAG" production "\$RELEASE_VERSION" "\$RELEASE_COMMIT"/);
assert.match(prodDeploy, /--no-traffic/);

assert.match(verify, /\[ "\$PERCENT" = "0" \]/);
assert.match(verify, /item\.get\("type"\) == "Ready"/);
assert.match(verify, /ROOT_CODE/);
assert.match(verify, /VERSION_JSON/);
assert.match(verify, /munea\.service-release\.v1/);
assert.match(verify, /release_metadata_mismatch/);
assert.match(verify, /revision=\$REVISION/);
assert.match(verify, /production:brain.*munea-brain/s);
assert.match(verify, /production:voice.*munea-voice/s);
assert.match(verify, /apple\/notifications/);
assert.match(verify, /NOTIFICATION_CODE.*400/s);
assert.match(verify, /尚未涵蓋.*Call Token/);
assert.doesNotMatch(verify, /update-traffic|--to-latest|promote\.sh/);

assert.match(promote, /canary-verify\.sh "\$WHAT" "\$TAG" "\$PROFILE" "\$EXPECTED_VERSION" "\$EXPECTED_COMMIT"/);
assert.match(promote, /--to-revisions "\$TARGET_REVISION=100"/);
assert.match(promote, /--to-revisions "\$PREVIOUS_REVISION=100"/);
assert.match(promote, /expected_one_100_percent_serving_revision/);
assert.match(promote, /VERIFIED_REVISION/);
assert.match(promote, /流量或 tag 已被其他 session 修改/);
assert.match(promote, /serving_release_mismatch/);
assert.match(promote, /for ATTEMPT in \{1\.\.10\}/);
assert.match(promote, /--connect-timeout 2 --max-time 4/);
assert.match(promote, /rollback_identity_mismatch/);
assert.match(promote, /rollback_traffic_not_restored/);
assert.match(promote, /promotion_traffic_not_exact_revision_100/);
assert.match(promote, /自動回滾後仍無法證明/);
assert.doesNotMatch(promote, /--to-latest/);

console.log('Cloud Run canary contract PASS: 0% identity checks and exact-revision promotion with rollback');
