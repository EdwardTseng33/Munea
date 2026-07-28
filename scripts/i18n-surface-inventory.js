'use strict';

const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..');
const INVENTORY_PATH = path.join(ROOT, 'docs', 'I18N-SURFACE-INVENTORY.json');
const NON_USER_FACING_REVIEW_PATH = path.join(
  ROOT,
  'docs',
  'I18N-NON-USER-FACING-REVIEW.json',
);
const CATALOG_DIR = path.join(ROOT, 'web', 'src', 'i18n');
const CATALOG_MANIFEST_PATH = path.join(CATALOG_DIR, 'catalog-manifest.json');
const HAN_RE = /[\u3400-\u9fff\uf900-\ufaff]/u;
const HTML_ATTRIBUTE_MARKERS = Object.freeze({
  'aria-label': 'data-i18n-aria-label',
  placeholder: 'data-i18n-placeholder',
  title: 'data-i18n-title',
  value: 'data-i18n-value',
});

let cachedCatalogKeys = null;
let cachedNonUserFacingReview = null;

function lineNumberAt(source, index) {
  let line = 1;
  for (let i = 0; i < index; i += 1) {
    if (source.charCodeAt(i) === 10) line += 1;
  }
  return line;
}

function normalizeCandidate(value) {
  return String(value || '')
    .replace(/\s+/g, ' ')
    .replace(/\\[nrt]/g, ' ')
    .trim();
}

function candidatePreview(text) {
  if (text.length <= 160) return text;
  const firstHan = text.search(HAN_RE);
  const start = firstHan > 120 ? Math.max(0, firstHan - 60) : 0;
  const prefix = start > 0 ? '...' : '';
  const available = 160 - prefix.length - 3;
  return `${prefix}${text.slice(start, start + available)}...`;
}

function loadCatalogKeys() {
  if (cachedCatalogKeys) return cachedCatalogKeys;
  const manifest = JSON.parse(fs.readFileSync(CATALOG_MANIFEST_PATH, 'utf8'));
  const keySets = manifest.locales.map(({ catalog }) => (
    new Set(Object.keys(JSON.parse(fs.readFileSync(path.join(CATALOG_DIR, catalog), 'utf8'))))
  ));
  const [first, ...rest] = keySets;
  cachedCatalogKeys = new Set(
    [...first].filter((key) => rest.every((keySet) => keySet.has(key))),
  );
  return cachedCatalogKeys;
}

function validBindingKey(key, catalogKeys = loadCatalogKeys()) {
  return typeof key === 'string' && catalogKeys.has(key);
}

function loadNonUserFacingReview() {
  if (cachedNonUserFacingReview) return cachedNonUserFacingReview;
  cachedNonUserFacingReview = JSON.parse(
    fs.readFileSync(NON_USER_FACING_REVIEW_PATH, 'utf8'),
  );
  return cachedNonUserFacingReview;
}

function applyNonUserFacingReview(relativePath, candidates, review = loadNonUserFacingReview()) {
  const failures = [];
  const entries = review.entries.filter((entry) => entry.path === relativePath);
  for (const entry of entries) {
    if (
      typeof entry.id !== 'string'
      || typeof entry.text !== 'string'
      || typeof entry.kind !== 'string'
      || !Number.isInteger(entry.expectedOccurrences)
      || entry.expectedOccurrences < 1
      || ![
        'backend-template-identity',
        'legacy-brand-migration-sentinel',
        'legacy-storage-identity',
      ]
        .includes(entry.reasonCode)
    ) {
      failures.push(`${relativePath}: invalid non-user-facing review entry ${entry.id || '<missing-id>'}`);
      continue;
    }
    if (!fs.existsSync(path.join(ROOT, entry.evidence || ''))) {
      failures.push(`${relativePath}: missing review evidence for ${entry.id}`);
      continue;
    }
    const matches = candidates.filter((candidate) => (
      candidate.bindingStatus === 'unbound'
      && candidate.kind === entry.kind
      && candidate.rawText === entry.text
    ));
    if (matches.length !== entry.expectedOccurrences) {
      failures.push(
        `${relativePath}: non-user-facing review ${entry.id} expected `
        + `${entry.expectedOccurrences} occurrence(s), found ${matches.length}`,
      );
      continue;
    }
    for (const candidate of matches) {
      candidate.bindingStatus = 'reviewed-non-user-facing';
      candidate.reviewId = entry.id;
      candidate.reviewReason = entry.reasonCode;
    }
  }
  return failures;
}

function applyStaticLocalizedAssetBinding(
  relativePath,
  candidates,
  config,
  requiredLocales,
) {
  if (!config) return [];
  const failures = [];
  const pageKind = config.pageBySource && config.pageBySource[relativePath];
  if (
    typeof config.manifest !== 'string'
    || typeof config.sourceLocale !== 'string'
    || !requiredLocales.includes(config.sourceLocale)
    || !config.pageBySource
    || typeof config.pageBySource !== 'object'
    || typeof pageKind !== 'string'
  ) {
    return [`${relativePath}: invalid static localized asset configuration`];
  }

  const manifestPath = path.resolve(ROOT, config.manifest);
  if (
    !manifestPath.startsWith(`${ROOT}${path.sep}`)
    || !fs.existsSync(manifestPath)
  ) {
    return [`${relativePath}: missing or unsafe static localization manifest ${config.manifest}`];
  }

  let manifest;
  try {
    manifest = JSON.parse(fs.readFileSync(manifestPath, 'utf8'));
  } catch (error) {
    return [`${relativePath}: invalid static localization manifest ${config.manifest}`];
  }
  if (!manifest.locales || typeof manifest.locales !== 'object') {
    return [`${relativePath}: static localization manifest has no locales`];
  }

  const manifestDir = path.dirname(manifestPath);
  for (const locale of requiredLocales) {
    const localeConfig = manifest.locales[locale];
    const assetPath = localeConfig
      && localeConfig.pages
      && localeConfig.pages[pageKind];
    if (
      !localeConfig
      || typeof localeConfig.htmlLang !== 'string'
      || typeof assetPath !== 'string'
    ) {
      failures.push(`${relativePath}: ${locale} is missing static ${pageKind} metadata`);
      continue;
    }
    const absoluteAssetPath = path.resolve(manifestDir, assetPath);
    if (
      !absoluteAssetPath.startsWith(`${ROOT}${path.sep}`)
      || !fs.existsSync(absoluteAssetPath)
    ) {
      failures.push(`${relativePath}: ${locale} static ${pageKind} asset is missing or unsafe`);
      continue;
    }
    const html = fs.readFileSync(absoluteAssetPath, 'utf8');
    const escapedLang = localeConfig.htmlLang.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    if (!new RegExp(`<html\\s+lang=["']${escapedLang}["']`, 'i').test(html)) {
      failures.push(
        `${relativePath}: ${locale} static ${pageKind} asset has the wrong html lang`,
      );
    }
    if (
      !/<title>[^<]+<\/title>/i.test(html)
      || !/class=["'][^"']*\bprivacy-page\b/i.test(html)
      || !/class=["'][^"']*\bprivacy-section\b/i.test(html)
      || /<script[\s>]/i.test(html)
    ) {
      failures.push(
        `${relativePath}: ${locale} static ${pageKind} asset is incomplete or executable`,
      );
    }
    if (locale === config.sourceLocale) {
      const sourcePath = path.resolve(ROOT, relativePath);
      if (absoluteAssetPath !== sourcePath) {
        failures.push(
          `${relativePath}: source locale ${locale} does not resolve to the inventoried asset`,
        );
      }
    }
  }

  if (!failures.length) {
    for (const candidate of candidates) {
      if (candidate.bindingStatus !== 'unbound') continue;
      candidate.bindingStatus = 'bound';
      candidate.bindingKey = `static-asset:${pageKind}`;
      candidate.bindingType = 'localized-static-asset';
    }
  }
  return failures;
}

function pushCandidate(candidates, source, index, kind, value, binding = null) {
  const text = normalizeCandidate(value);
  if (!text || !HAN_RE.test(text)) return;
  const candidate = {
    line: lineNumberAt(source, index),
    kind,
    text: candidatePreview(text),
    bindingStatus: binding ? 'bound' : 'unbound',
  };
  if (binding) {
    candidate.bindingKey = binding.key;
    candidate.bindingType = binding.type;
  }
  Object.defineProperty(candidate, 'sourceIndex', {
    configurable: false,
    enumerable: false,
    value: index,
  });
  Object.defineProperty(candidate, 'rawText', {
    configurable: false,
    enumerable: false,
    value: text,
  });
  candidates.push(candidate);
}

function parseCallArguments(source, openParenIndex) {
  const args = [];
  let argumentStart = openParenIndex + 1;
  let state = 'code';
  let quote = '';
  let depth = 1;
  let i = argumentStart;

  while (i < source.length) {
    const char = source[i];
    const next = source[i + 1];
    if (state === 'line-comment') {
      if (char === '\n') state = 'code';
      i += 1;
      continue;
    }
    if (state === 'block-comment') {
      if (char === '*' && next === '/') {
        state = 'code';
        i += 2;
      } else {
        i += 1;
      }
      continue;
    }
    if (state === 'string') {
      if (char === '\\') {
        i += 2;
        continue;
      }
      if (char === quote) {
        state = 'code';
        quote = '';
      }
      i += 1;
      continue;
    }
    if (char === '/' && next === '/') {
      state = 'line-comment';
      i += 2;
      continue;
    }
    if (char === '/' && next === '*') {
      state = 'block-comment';
      i += 2;
      continue;
    }
    if (char === '"' || char === "'" || char === '`') {
      state = 'string';
      quote = char;
      i += 1;
      continue;
    }
    if (char === '(' || char === '[' || char === '{') depth += 1;
    if (char === ')' || char === ']' || char === '}') depth -= 1;
    if ((char === ',' && depth === 1) || (char === ')' && depth === 0)) {
      args.push({ start: argumentStart, end: i });
      if (char === ')') return args;
      argumentStart = i + 1;
    }
    i += 1;
  }
  return [];
}

function staticCatalogKey(source, argument) {
  if (!argument) return null;
  const value = source.slice(argument.start, argument.end).trim();
  const match = value.match(/^(['"])([A-Za-z0-9_.-]+)\1$/);
  return match ? match[2] : null;
}

function javaScriptBindings(source, catalogKeys) {
  const bindings = [];
  const callPattern = /\b(muneaT|t|localizedFallback|(?:window\.)?MuneaI18n(?:\.|\?\.)t)\s*\(/g;
  let match;
  while ((match = callPattern.exec(source)) !== null) {
    const openParenIndex = source.indexOf('(', match.index + match[1].length);
    const args = parseCallArguments(source, openParenIndex);
    const key = staticCatalogKey(source, args[0]);
    if (!validBindingKey(key, catalogKeys)) continue;
    const fallbackIndex = match[1].endsWith('MuneaI18n.t')
      || match[1].endsWith('MuneaI18n?.t')
      ? 2
      : 1;
    if (!args[fallbackIndex]) continue;
    bindings.push({
      start: args[fallbackIndex].start,
      end: args[fallbackIndex].end,
      key,
      type: 'translation-call',
    });
  }
  return bindings;
}

function bindingForIndex(bindings, index) {
  const binding = bindings.find(({ start, end }) => index >= start && index < end);
  return binding ? { key: binding.key, type: binding.type } : null;
}

function scanJavaScript(source, catalogKeys = loadCatalogKeys()) {
  const candidates = [];
  const bindings = javaScriptBindings(source, catalogKeys);
  let i = 0;
  let state = 'code';
  let quote = '';
  let start = 0;
  let value = '';

  while (i < source.length) {
    const char = source[i];
    const next = source[i + 1];

    if (state === 'line-comment') {
      if (char === '\n') state = 'code';
      i += 1;
      continue;
    }
    if (state === 'block-comment') {
      if (char === '*' && next === '/') {
        state = 'code';
        i += 2;
      } else {
        i += 1;
      }
      continue;
    }
    if (state === 'string') {
      if (char === '\\') {
        value += char + (next || '');
        i += 2;
        continue;
      }
      if (char === quote) {
        pushCandidate(
          candidates,
          source,
          start,
          quote === '`' ? 'template-string' : 'string',
          value,
          bindingForIndex(bindings, start),
        );
        state = 'code';
        quote = '';
        value = '';
        i += 1;
        continue;
      }
      value += char;
      i += 1;
      continue;
    }

    if (char === '/' && next === '/') {
      state = 'line-comment';
      i += 2;
      continue;
    }
    if (char === '/' && next === '*') {
      state = 'block-comment';
      i += 2;
      continue;
    }
    if (char === '"' || char === "'" || char === '`') {
      state = 'string';
      quote = char;
      start = i;
      value = '';
      i += 1;
      continue;
    }
    i += 1;
  }
  return candidates;
}

function markerKey(tag, marker) {
  if (!tag || !marker) return null;
  const pattern = new RegExp(`\\b${marker}\\s*=\\s*(["'])(.*?)\\1`, 'is');
  const match = tag.match(pattern);
  return match ? match[2].trim() : null;
}

function containingTag(source, index) {
  const start = source.lastIndexOf('<', index);
  const end = source.indexOf('>', start);
  if (start < 0 || end < index) return '';
  return source.slice(start, end + 1);
}

function openingTagBeforeText(source, textIndex) {
  const end = source.lastIndexOf('>', textIndex);
  const start = source.lastIndexOf('<', end);
  if (start < 0 || end < 0) return '';
  const tag = source.slice(start, end + 1);
  return /^<\s*[A-Za-z]/.test(tag) ? tag : '';
}

function htmlBinding(tag, marker, type, catalogKeys) {
  const key = markerKey(tag, marker);
  return validBindingKey(key, catalogKeys) ? { key, type } : null;
}

function scanHtml(source, catalogKeys = loadCatalogKeys()) {
  const candidates = [];
  const withoutComments = source.replace(/<!--[\s\S]*?-->/g, (match) => ' '.repeat(match.length));
  const withoutStyles = withoutComments.replace(
    /<style\b[^>]*>[\s\S]*?<\/style>/gi,
    (match) => ' '.repeat(match.length),
  );
  const withoutScripts = withoutStyles.replace(
    /<script\b[^>]*>([\s\S]*?)<\/script>/gi,
    (match, scriptBody, offset) => {
      const bodyOffset = offset + match.indexOf(scriptBody);
      for (const candidate of scanJavaScript(scriptBody, catalogKeys)) {
        const binding = candidate.bindingStatus === 'bound'
          ? { key: candidate.bindingKey, type: candidate.bindingType }
          : null;
        pushCandidate(
          candidates,
          source,
          bodyOffset + candidate.sourceIndex,
          `inline-${candidate.kind}`,
          candidate.rawText,
          binding,
        );
      }
      return ' '.repeat(match.length);
    },
  );

  const attributePattern = /\b(title|placeholder|aria-label|alt|content|value)\s*=\s*(["'])(.*?)\2/gis;
  let match;
  while ((match = attributePattern.exec(withoutScripts)) !== null) {
    const attribute = match[1].toLowerCase();
    const marker = HTML_ATTRIBUTE_MARKERS[attribute];
    pushCandidate(
      candidates,
      source,
      match.index,
      `attribute:${attribute}`,
      match[3],
      htmlBinding(
        containingTag(source, match.index),
        marker,
        marker || 'unrecognized-attribute',
        catalogKeys,
      ),
    );
  }

  const textPattern = />([^<>]+)</gs;
  while ((match = textPattern.exec(withoutScripts)) !== null) {
    pushCandidate(
      candidates,
      source,
      match.index + 1,
      'text',
      match[1],
      htmlBinding(
        openingTagBeforeText(source, match.index + 1),
        'data-i18n',
        'data-i18n',
        catalogKeys,
      ),
    );
  }
  return candidates;
}

function scanFile(relativePath) {
  const absolutePath = path.join(ROOT, relativePath);
  if (!fs.existsSync(absolutePath)) {
    return {
      path: relativePath,
      exists: false,
      candidates: [],
      reviewFailures: [],
    };
  }
  const source = fs.readFileSync(absolutePath, 'utf8');
  const extension = path.extname(relativePath).toLowerCase();
  const candidates = extension === '.html'
    ? scanHtml(source)
    : scanJavaScript(source);
  const reviewFailures = applyNonUserFacingReview(relativePath, candidates);
  return {
    path: relativePath,
    exists: true,
    candidates,
    reviewFailures,
  };
}

function loadInventory() {
  return JSON.parse(fs.readFileSync(INVENTORY_PATH, 'utf8'));
}

function buildReport(inventory = loadInventory()) {
  const seen = new Map();
  const surfaces = inventory.surfaces.map((surface) => {
    const staticConfig = surface.staticLocalizedAssets || null;
    const staticConfigFailures = [];
    if (staticConfig) {
      const configuredSources = Object.keys(staticConfig.pageBySource || {});
      for (const relativePath of surface.files) {
        if (!configuredSources.includes(relativePath)) {
          staticConfigFailures.push(
            `${surface.id}: static localization source is not mapped: ${relativePath}`,
          );
        }
      }
      for (const relativePath of configuredSources) {
        if (!surface.files.includes(relativePath)) {
          staticConfigFailures.push(
            `${surface.id}: static localization mapping is outside the surface: ${relativePath}`,
          );
        }
      }
    }
    const files = surface.files.map((relativePath) => {
      if (seen.has(relativePath)) {
        throw new Error(
          `Inventory file ${relativePath} is assigned to both ${seen.get(relativePath)} and ${surface.id}`,
        );
      }
      seen.set(relativePath, surface.id);
      if (surface.scanMode === 'localized-text') {
        const file = scanFile(relativePath);
        file.reviewFailures.push(...applyStaticLocalizedAssetBinding(
          relativePath,
          file.candidates,
          staticConfig,
          inventory.requiredLocales,
        ));
        return file;
      }
      return {
        path: relativePath,
        exists: fs.existsSync(path.join(ROOT, relativePath)),
        candidates: [],
        reviewFailures: [],
      };
    });
    const hanCandidates = files.reduce((sum, file) => sum + file.candidates.length, 0);
    const boundHanCandidates = files.reduce(
      (sum, file) => sum + file.candidates.filter(
        (candidate) => candidate.bindingStatus === 'bound',
      ).length,
      0,
    );
    const reviewedNonUserFacingHanCandidates = files.reduce(
      (sum, file) => sum + file.candidates.filter(
        (candidate) => candidate.bindingStatus === 'reviewed-non-user-facing',
      ).length,
      0,
    );
    const unboundHanCandidates = files.reduce(
      (sum, file) => sum + file.candidates.filter(
        (candidate) => candidate.bindingStatus === 'unbound',
      ).length,
      0,
    );
    return {
      id: surface.id,
      label: surface.label,
      scanMode: surface.scanMode,
      baselineHanCandidates: surface.baselineHanCandidates ?? null,
      hanCandidates,
      boundHanCandidates,
      reviewedNonUserFacingHanCandidates,
      unboundHanCandidates,
      reviewFailures: [
        ...staticConfigFailures,
        ...files.flatMap((file) => file.reviewFailures),
      ],
      missingFiles: files.filter((file) => !file.exists).map((file) => file.path),
      files: files.map((file) => ({
        path: file.path,
        exists: file.exists,
        hanCandidates: file.candidates.length,
        boundHanCandidates: file.candidates.filter(
          (candidate) => candidate.bindingStatus === 'bound',
        ).length,
        reviewedNonUserFacingHanCandidates: file.candidates.filter(
          (candidate) => candidate.bindingStatus === 'reviewed-non-user-facing',
        ).length,
        unboundHanCandidates: file.candidates.filter(
          (candidate) => candidate.bindingStatus === 'unbound',
        ).length,
        reviewFailures: file.reviewFailures,
        candidates: file.candidates,
      })),
    };
  });
  const review = loadNonUserFacingReview();
  const reviewFailures = [];
  if (
    review.schema !== 'munea.i18n-non-user-facing-review.v1'
    || !review.policy
    || review.policy.exactFileTextKindAndOccurrenceMatchRequired !== true
    || review.policy.newOccurrencesFailClosed !== true
    || review.policy.userVisibleFallbacksForbidden !== true
    || review.policy.evidenceFileRequired !== true
  ) {
    reviewFailures.push('invalid non-user-facing review policy');
  }
  const reviewIds = review.entries.map(({ id }) => id);
  if (new Set(reviewIds).size !== reviewIds.length) {
    reviewFailures.push('non-user-facing review IDs must be unique');
  }
  for (const entry of review.entries) {
    if (!seen.has(entry.path)) {
      reviewFailures.push(`non-user-facing review path is outside the surface inventory: ${entry.path}`);
    }
  }
  return {
    schemaVersion: inventory.schemaVersion,
    requiredLocales: inventory.requiredLocales,
    generatedAt: new Date().toISOString(),
    totalHanCandidates: surfaces.reduce((sum, surface) => sum + surface.hanCandidates, 0),
    totalBoundHanCandidates: surfaces.reduce(
      (sum, surface) => sum + surface.boundHanCandidates,
      0,
    ),
    totalReviewedNonUserFacingHanCandidates: surfaces.reduce(
      (sum, surface) => sum + surface.reviewedNonUserFacingHanCandidates,
      0,
    ),
    totalUnboundHanCandidates: surfaces.reduce(
      (sum, surface) => sum + surface.unboundHanCandidates,
      0,
    ),
    reviewFailures,
    surfaces,
  };
}

function validateReport(report) {
  const failures = [...(report.reviewFailures || [])];
  for (const surface of report.surfaces) {
    for (const missingFile of surface.missingFiles) {
      failures.push(`${surface.id}: missing file ${missingFile}`);
    }
    failures.push(...surface.reviewFailures);
    if (
      surface.scanMode === 'localized-text'
      && Number.isInteger(surface.baselineHanCandidates)
      && surface.hanCandidates > surface.baselineHanCandidates
    ) {
      failures.push(
        `${surface.id}: Han candidates increased `
        + `${surface.baselineHanCandidates} -> ${surface.hanCandidates}`,
      );
    }
    if (
      surface.boundHanCandidates
      + surface.reviewedNonUserFacingHanCandidates
      + surface.unboundHanCandidates
      !== surface.hanCandidates
    ) {
      failures.push(`${surface.id}: Han candidate classifications do not reconcile`);
    }
  }
  return failures;
}

function printSummary(report) {
  console.log(
    `I18N surface inventory: ${report.totalHanCandidates} Han candidates `
    + `(${report.totalBoundHanCandidates} bound, `
    + `${report.totalReviewedNonUserFacingHanCandidates} reviewed internal, `
    + `${report.totalUnboundHanCandidates} unbound)`,
  );
  for (const surface of report.surfaces) {
    const baseline = Number.isInteger(surface.baselineHanCandidates)
      ? ` / baseline ${surface.baselineHanCandidates}`
      : '';
    console.log(
      `- ${surface.id}: ${surface.hanCandidates}${baseline} `
      + `(${surface.boundHanCandidates} bound, `
      + `${surface.reviewedNonUserFacingHanCandidates} reviewed internal, `
      + `${surface.unboundHanCandidates} unbound)`,
    );
    for (const file of surface.files) {
      if (surface.scanMode === 'localized-text') {
        console.log(
          `  ${file.path}: ${file.hanCandidates} `
          + `(${file.boundHanCandidates} bound, `
          + `${file.reviewedNonUserFacingHanCandidates} reviewed internal, `
          + `${file.unboundHanCandidates} unbound)`,
        );
      }
    }
  }
}

if (require.main === module) {
  const report = buildReport();
  const wantsJson = process.argv.includes('--json');
  const wantsCheck = process.argv.includes('--check');
  if (wantsJson) {
    process.stdout.write(`${JSON.stringify(report, null, 2)}\n`);
  } else {
    printSummary(report);
  }
  if (wantsCheck) {
    const failures = validateReport(report);
    if (failures.length) {
      console.error(failures.join('\n'));
      process.exitCode = 1;
    }
  }
}

module.exports = {
  applyNonUserFacingReview,
  applyStaticLocalizedAssetBinding,
  buildReport,
  loadCatalogKeys,
  loadInventory,
  loadNonUserFacingReview,
  scanFile,
  scanHtml,
  scanJavaScript,
  validateReport,
};
