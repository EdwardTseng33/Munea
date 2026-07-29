'use strict';

const crypto = require('crypto');
const fs = require('fs');
const path = require('path');
const {
  buildReport,
  loadInventory,
} = require('./i18n-surface-inventory.js');

const ROOT = path.resolve(__dirname, '..');
const ZH_CATALOG_PATH = path.join(ROOT, 'web', 'src', 'i18n', 'zh-TW.json');

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

function catalogValueIndex() {
  const catalog = JSON.parse(fs.readFileSync(ZH_CATALOG_PATH, 'utf8'));
  const index = new Map();
  for (const [key, value] of Object.entries(catalog)) {
    const source = String(value).replace(/\s+/g, ' ').trim();
    if (!index.has(source)) index.set(source, []);
    index.get(source).push(key);
  }
  for (const matches of index.values()) matches.sort();
  return index;
}

function buildMigrationWorklist(surfaceId = 'app-webview', inventory = loadInventory()) {
  const report = buildReport(inventory);
  const surface = report.surfaces.find((entry) => entry.id === surfaceId);
  if (!surface) throw new Error(`Unknown i18n surface: ${surfaceId}`);
  if (surface.scanMode !== 'localized-text') {
    throw new Error(`I18N surface ${surfaceId} is not a localized-text surface`);
  }

  const entries = new Map();
  const catalogMatchesBySource = catalogValueIndex();
  const sourceFiles = {};
  for (const file of surface.files) {
    const absolutePath = path.join(ROOT, file.path);
    sourceFiles[file.path] = sha256(fs.readFileSync(absolutePath));
    for (const candidate of file.candidates) {
      if (candidate.bindingStatus !== 'unbound') continue;
      const source = candidate.rawText || candidate.text;
      const entryId = stableKey(source);
      if (!entries.has(entryId)) {
        const catalogMatches = catalogMatchesBySource.get(source) || [];
        const resolutionKind = catalogMatches.length === 1
          ? 'reuse-existing-key'
          : catalogMatches.length > 1
            ? 'review-existing-keys'
            : 'create-key';
        entries.set(entryId, {
          suggestedKey: catalogMatches.length === 1 ? catalogMatches[0] : entryId,
          source,
          catalogMatches,
          resolutionKind,
          bindingKind: bindingKind(candidate),
          reviewStatus: 'pending',
          occurrences: [],
        });
      }
      const entry = entries.get(entryId);
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
  const resolutionKinds = {};
  for (const entry of worklist) {
    bindingKinds[entry.bindingKind] = (bindingKinds[entry.bindingKind] || 0) + 1;
    resolutionKinds[entry.resolutionKind] = (resolutionKinds[entry.resolutionKind] || 0) + 1;
  }
  return {
    schema: 'munea.i18n-migration-worklist.v3',
    surface: surfaceId,
    requiredLocales: inventory.requiredLocales,
    sourceFiles,
    summary: {
      totalOccurrences: surface.hanCandidates,
      boundOccurrences: surface.boundHanCandidates,
      reviewedNonUserFacingOccurrences: surface.reviewedNonUserFacingHanCandidates,
      unboundOccurrences: surface.unboundHanCandidates,
      occurrences: surface.unboundHanCandidates,
      uniqueSourceStrings: worklist.length,
      bindingKinds,
      resolutionKinds,
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
  for (const [kind, count] of Object.entries(worklist.summary.resolutionKinds).sort()) {
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
  catalogValueIndex,
  formatSummary,
  stableKey,
};
