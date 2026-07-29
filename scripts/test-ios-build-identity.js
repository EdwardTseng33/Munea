'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const {
  createIosBuildIdentity,
  uniqueProjectSetting,
  validateIosBuildIdentity,
} = require('./ios-build-identity.js');

const exactCommit = 'a'.repeat(40);
const identity = createIosBuildIdentity(exactCommit);
assert.equal(identity.schema, 'munea.ios-build-identity.v1');
assert.equal(identity.bundleIdentifier, 'net.munea.app');
assert.equal(identity.exactCommit, exactCommit);
assert.equal(identity.appVersion, JSON.parse(fs.readFileSync('package.json', 'utf8')).version);
assert.match(identity.build, /^\d+$/);
assert.deepEqual(validateIosBuildIdentity(identity, identity), identity);
assert.throws(
  () => validateIosBuildIdentity(identity, { exactCommit: 'b'.repeat(40) }),
  /exactCommit does not match/,
);
assert.throws(
  () => validateIosBuildIdentity(identity, { build: `${identity.build}0` }),
  /build does not match/,
);
assert.throws(
  () => uniqueProjectSetting(
    'CURRENT_PROJECT_VERSION = 48; CURRENT_PROJECT_VERSION = 49;',
    'CURRENT_PROJECT_VERSION',
  ),
  /must have one value/,
);

const archiveScript = fs.readFileSync('scripts/ios-archive.sh', 'utf8');
const exportScript = fs.readFileSync('scripts/ios-export-app-store.sh', 'utf8');
assert.match(archiveScript, /git status --porcelain --untracked-files=normal/);
assert.match(archiveScript, /ios-build-identity\.js[\s\S]*--write/);
assert.match(archiveScript, /public\/src\/build-identity\.json/);
assert.match(exportScript, /ios-build-identity\.js[\s\S]*--verify/);
assert.match(exportScript, /public\/src\/build-identity\.json/);

console.log('PASS: iOS archive embeds commit, version, build, and bundle identity');
