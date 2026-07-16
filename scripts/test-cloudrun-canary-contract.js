const assert = require('assert');
const fs = require('fs');

const deploy = fs.readFileSync('deploy/cloudrun/canary-deploy.sh', 'utf8');
const verify = fs.readFileSync('deploy/cloudrun/canary-verify.sh', 'utf8');

assert.match(deploy, /--no-traffic/);
assert.match(deploy, /canary-verify\.sh "\$WHAT" "\$TAG"/);
assert.doesNotMatch(deploy, /update-traffic|--to-latest/);

assert.match(verify, /\[ "\$PERCENT" = "0" \]/);
assert.match(verify, /Ready\\tTrue/);
assert.match(verify, /ROOT_CODE/);
assert.match(verify, /apple\/notifications/);
assert.match(verify, /NOTIFICATION_CODE.*400/s);
assert.match(verify, /尚未涵蓋.*Call Token/);
assert.doesNotMatch(verify, /update-traffic|--to-latest|promote\.sh/);

console.log('Cloud Run canary contract PASS: no traffic, Ready/root checks, Apple JWS rejection, and no promotion');
