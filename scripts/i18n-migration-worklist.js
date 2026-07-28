'use strict';

const crypto = require('crypto');
const fs = require('fs');
const path = require('path');
const {
  buildReport,
  loadInventory,
} = require('./i18n-surface-inventory.js');

const ROOT = path.resolve(__dirname, '..');

function sha256(value) {
  return crypto.createHash('sha256').update(value).digest('hex');
}

function stableKey(source) {
  return `legacy.${sha256(String(source)).slice(0, 16)}`;
}

function bindingKind(candidate) {
  if (/<\/?[A-Za-z][^>]*>/.test(candidate.text)) return 'markup-refactor';
  if (candidate.kind.startsWith('attribute:')) return 'attribute';
  if (candidate.kind === 'text') return 'static-text';
  if (
    candidate.kind.includes('template')
    || /\$\{[^}]+\}|\{[A-Za-z][A-Za-z0-9_]*\}/.test(candidate.text)
  ) {
    return 'interpolated-copy';
  }
  return 'runtime-copy';
}

function buildMigrationWorklist(surfaceId = 'app-webview', inventory = loadInventory()) {
  const report = buildReport(inventory);
  const surface = report.surfaces.find((entry) => entry.id === surfaceId);
  if (!surface) throw new Error(`Unknown i18n surface: ${surfaceId}`);
  if (surface.scanMode !== 'localized-text') {
    throw new Error(`I18N surface ${surfaceId} is not a localized-text surface`);
  }

  const entries = new Map();
  const sourceFiles = {};
  for (const file of surface.files) {
    const absolutePath = path.join(ROOT, file.path);
    sourceFiles[file.path] = sha256(fs.readFileSync(absolutePath));
    for (const candidate of file.candidates) {
      if (candidate.bindingStatus === 'bound') continue;
      const key = stableKey(candidate.text);
      if (!entries.has(key)) {
        entries.set(key, {
          suggestedKey: key,
          source: candidate.text,
          bindingKind: bindingKind(candidate),
          reviewStatus: 'pending',
          occurrences: [],
        });
      }
      const entry = entries.get(key);
      const nextKind = bindingKind(candidate);
      if (nextKind === 'markup-refactor') entry.bindingKind = nextKind;
      entry.occurrences.push({
        file: file.path,
        line: candidate.line,
        kind: candidate.kind,
      });
    }
  }

  const worklist = [...entries.values()]
    .sort((left, right) => left.suggestedKey.localeCompare(right.suggestedKey));
  const bindingKinds = {};
  for (const entry of worklist) {
    bindingKinds[entry.bindingKind] = (bindingKinds[entry.bindingKind] || 0) + 1;
  }
  return {
    schema: 'munea.i18n-migration-worklist.v2',
    surface: surfaceId,
    requiredLocales: inventory.requiredLocales,
    sourceFiles,
    summary: {
      totalOccurrences: surface.hanCandidates,
      boundOccurrences: surface.boundHanCandidates,
      unboundOccurrences: surface.unboundHanCandidates,
      occurrences: surface.unboundHanCandidates,
      uniqueSourceStrings: worklist.length,
      bindingKinds,
    },
    entries: worklist,
  };
}

function formatSummary(worklist) {
  const lines = [
    `I18N migration worklist: ${worklist.surface}`,
    `Unbound occurrences: ${worklist.summary.unboundOccurrences}`,
    `Already bound fallbacks: ${worklist.summary.boundOccurrences}`,
    `Unique source strings: ${worklist.summary.uniqueSourceStrings}`,
  ];
  for (const [kind, count] of Object.entries(worklist.summary.bindingKinds).sort()) {
    lines.push(`- ${kind}: ${count}`);
  }
  return lines.join('\n');
}

if (require.main === module) {
  const surfaceFlag = process.argv.indexOf('--surface');
  const surfaceId = surfaceFlag >= 0 ? process.argv[surfaceFlag + 1] : 'app-webview';
  const worklist = buildMigrationWorklist(surfaceId);
  if (process.argv.includes('--json')) {
    process.stdout.write(`${JSON.stringify(worklist, null, 2)}\n`);
  } else {
    process.stdout.write(`${formatSummary(worklist)}\n`);
  }
}

module.exports = {
  bindingKind,
  buildMigrationWorklist,
  formatSummary,
  stableKey,
};
