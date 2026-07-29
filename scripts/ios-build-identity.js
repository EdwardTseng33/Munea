'use strict';

const fs = require('node:fs');
const path = require('node:path');

const ROOT = path.resolve(__dirname, '..');
const SCHEMA = 'munea.ios-build-identity.v1';

function requiredString(value, label) {
  if (typeof value !== 'string' || value.trim() === '') {
    throw new Error(`${label} is required`);
  }
  return value.trim();
}

function uniqueProjectSetting(projectSource, name) {
  const pattern = new RegExp(`${name}\\s*=\\s*([^;]+);`, 'g');
  const values = new Set();
  for (const match of projectSource.matchAll(pattern)) {
    values.add(match[1].trim().replace(/^"(.*)"$/, '$1'));
  }
  if (values.size !== 1) {
    throw new Error(`${name} must have one value across Xcode configurations`);
  }
  return [...values][0];
}

function createIosBuildIdentity(exactCommit, root = ROOT) {
  const commit = requiredString(exactCommit, 'exactCommit').toLowerCase();
  if (!/^[0-9a-f]{40}$/.test(commit)) {
    throw new Error('exactCommit must be a 40-character Git SHA');
  }
  const packageJson = JSON.parse(
    fs.readFileSync(path.join(root, 'package.json'), 'utf8'),
  );
  const projectSource = fs.readFileSync(
    path.join(root, 'ios', 'App', 'App.xcodeproj', 'project.pbxproj'),
    'utf8',
  );
  const appVersion = requiredString(packageJson.version, 'package version');
  const marketingVersion = uniqueProjectSetting(projectSource, 'MARKETING_VERSION');
  if (marketingVersion !== appVersion) {
    throw new Error('Xcode MARKETING_VERSION must match package.json');
  }
  return {
    schema: SCHEMA,
    bundleIdentifier: uniqueProjectSetting(projectSource, 'PRODUCT_BUNDLE_IDENTIFIER'),
    exactCommit: commit,
    appVersion,
    build: uniqueProjectSetting(projectSource, 'CURRENT_PROJECT_VERSION'),
  };
}

function validateIosBuildIdentity(identity, expected = {}) {
  if (!identity || identity.schema !== SCHEMA) {
    throw new Error('iOS build identity schema is invalid');
  }
  const normalized = {
    schema: SCHEMA,
    bundleIdentifier: requiredString(identity.bundleIdentifier, 'bundleIdentifier'),
    exactCommit: requiredString(identity.exactCommit, 'exactCommit').toLowerCase(),
    appVersion: requiredString(identity.appVersion, 'appVersion'),
    build: requiredString(identity.build, 'build'),
  };
  if (!/^[0-9a-f]{40}$/.test(normalized.exactCommit)) {
    throw new Error('exactCommit must be a 40-character Git SHA');
  }
  for (const field of ['bundleIdentifier', 'exactCommit', 'appVersion', 'build']) {
    if (
      expected[field] !== undefined
      && normalized[field] !== String(expected[field]).toLowerCase()
    ) {
      throw new Error(`iOS build identity ${field} does not match`);
    }
  }
  return normalized;
}

function argValue(name) {
  const index = process.argv.indexOf(name);
  return index >= 0 ? process.argv[index + 1] : '';
}

function main() {
  if (process.argv.includes('--write')) {
    const output = path.resolve(requiredString(argValue('--output'), '--output'));
    const identity = createIosBuildIdentity(argValue('--commit'));
    fs.mkdirSync(path.dirname(output), { recursive: true });
    fs.writeFileSync(output, `${JSON.stringify(identity, null, 2)}\n`, 'utf8');
    process.stdout.write(
      `iOS build identity created: ${identity.appVersion} (${identity.build}) `
      + `${identity.exactCommit}\n`,
    );
    return;
  }
  if (process.argv.includes('--verify')) {
    const input = path.resolve(requiredString(argValue('--input'), '--input'));
    const identity = JSON.parse(fs.readFileSync(input, 'utf8'));
    const verified = validateIosBuildIdentity(identity, {
      bundleIdentifier: argValue('--bundle-id'),
      exactCommit: argValue('--commit'),
      appVersion: argValue('--version'),
      build: argValue('--build'),
    });
    process.stdout.write(
      `iOS build identity verified: ${verified.appVersion} (${verified.build}) `
      + `${verified.exactCommit}\n`,
    );
    return;
  }
  throw new Error('usage: --write --commit <sha> --output <json> OR --verify --input <json> --commit <sha> --version <version> --build <build> --bundle-id <id>');
}

if (require.main === module) {
  try {
    main();
  } catch (error) {
    process.stderr.write(`iOS build identity refused: ${error.message}\n`);
    process.exitCode = 1;
  }
}

module.exports = {
  SCHEMA,
  createIosBuildIdentity,
  uniqueProjectSetting,
  validateIosBuildIdentity,
};
