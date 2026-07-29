'use strict';

const assert = require('node:assert');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { spawnSync } = require('node:child_process');

const source = fs.readFileSync('scripts/ios-export-app-store.sh', 'utf8')
  .replace(/\r\n/g, '\n');
const startMarker = '# MUNEA_I18N_BINARY_GATE_START';
const endMarker = '# MUNEA_I18N_BINARY_GATE_END';
const start = source.indexOf(startMarker);
const end = source.indexOf(endMarker);
assert.ok(start >= 0 && end > start, 'could not locate the IPA i18n binary gate');
const gate = source.slice(start + startMarker.length, end);
assert.match(gate, /exit 1/, 'the IPA i18n binary gate must fail closed');
assert.match(gate, /catalog-manifest\.json/, 'the binary gate must follow the release manifest');
assert.match(
  gate,
  /binaryLocalizationEnabled/,
  'the binary gate must only ship release-enabled binary localizations',
);

const manifest = JSON.parse(
  fs.readFileSync('web/src/i18n/catalog-manifest.json', 'utf8'),
);
const requiredLocales = manifest.locales
  .filter((entry) => entry.binaryLocalizationEnabled)
  .map((entry) => entry.nativeLocale);
assert.deepEqual(requiredLocales, ['zh-Hant']);

function gitBashPath() {
  if (process.platform !== 'win32') return 'bash';
  const candidate = path.join(
    process.env.ProgramFiles || 'C:\\Program Files',
    'Git',
    'bin',
    'bash.exe',
  );
  return fs.existsSync(candidate) ? candidate : 'bash';
}

function runGate(options = {}) {
  const temp = fs.mkdtempSync(path.join(os.tmpdir(), 'munea-ipa-i18n-gate-'));
  const appPath = path.join(temp, 'Payload', 'App.app');
  fs.mkdirSync(appPath, { recursive: true });
  fs.writeFileSync(path.join(appPath, 'Info.plist'), 'fixture', 'utf8');
  for (const locale of requiredLocales) {
    if (locale === options.missingLocaleFile) continue;
    const localeDir = path.join(appPath, `${locale}.lproj`);
    fs.mkdirSync(localeDir, { recursive: true });
    fs.writeFileSync(path.join(localeDir, 'InfoPlist.strings'), 'fixture', 'utf8');
  }
  const bundleLocales = options.bundleLocales || requiredLocales;
  const wrapper = [
    'set -euo pipefail',
    'APP_PATH="$1"',
    `MUNEA_REQUIRED_IOS_LOCALIZATIONS='${requiredLocales.join('\n')}'`,
    `MUNEA_TEST_BUNDLE_LOCALES='${JSON.stringify(bundleLocales)}'`,
    `MUNEA_TEST_MISSING_KEY='${options.missingKey || ''}'`,
    'plutil() {',
    '  if [ "$2" = "CFBundleLocalizations" ]; then',
    '    printf "%s\\n" "$MUNEA_TEST_BUNDLE_LOCALES"',
    '  elif [ "$2" = "$MUNEA_TEST_MISSING_KEY" ]; then',
    '    return 1',
    '  else',
    '    printf "%s\\n" "localized-value"',
    '  fi',
    '}',
    gate,
    'echo GATE_PASS',
  ].join('\n');
  const result = spawnSync(
    gitBashPath(),
    ['-c', wrapper, 'bash', appPath.replaceAll('\\', '/')],
    { encoding: 'utf8' },
  );
  fs.rmSync(temp, { recursive: true, force: true });
  if (result.error) throw result.error;
  return result;
}

const complete = runGate();
assert.equal(
  complete.status,
  0,
  `complete four-locale IPA fixture failed: ${complete.stdout} ${complete.stderr}`,
);
assert.match(complete.stdout, /GATE_PASS/);

const missingFile = runGate({ missingLocaleFile: 'zh-Hant' });
assert.equal(missingFile.status, 1);
assert.match(missingFile.stdout, /missing binary localization: zh-Hant/);

const missingDeclaration = runGate({ bundleLocales: [] });
assert.equal(missingDeclaration.status, 1);
assert.match(missingDeclaration.stdout, /missing binary localization: zh-Hant/);

const missingUsageCopy = runGate({ missingKey: 'NSHealthShareUsageDescription' });
assert.equal(missingUsageCopy.status, 1);
assert.match(
  missingUsageCopy.stdout,
  /localization zh-Hant is missing NSHealthShareUsageDescription/,
);

console.log('PASS: IPA export rejects missing release-enabled localizations and usage copy');
