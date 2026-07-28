'use strict';

const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..');
const INVENTORY_PATH = path.join(ROOT, 'docs', 'I18N-SURFACE-INVENTORY.json');
const HAN_RE = /[\u3400-\u9fff\uf900-\ufaff]/u;

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

function pushCandidate(candidates, source, index, kind, value) {
  const text = normalizeCandidate(value);
  if (!text || !HAN_RE.test(text)) return;
  candidates.push({
    line: lineNumberAt(source, index),
    kind,
    text: text.length > 160 ? `${text.slice(0, 157)}...` : text,
  });
}

function scanJavaScript(source) {
  const candidates = [];
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

function scanHtml(source) {
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
      for (const candidate of scanJavaScript(scriptBody)) {
        pushCandidate(
          candidates,
          source,
          bodyOffset + scriptBody.split('\n').slice(0, candidate.line - 1).join('\n').length,
          `inline-${candidate.kind}`,
          candidate.text,
        );
      }
      return ' '.repeat(match.length);
    },
  );

  const attributePattern = /\b(title|placeholder|aria-label|alt|content|value)\s*=\s*(["'])(.*?)\2/gis;
  let match;
  while ((match = attributePattern.exec(withoutScripts)) !== null) {
    pushCandidate(candidates, source, match.index, `attribute:${match[1].toLowerCase()}`, match[3]);
  }

  const textPattern = />([^<>]+)</gs;
  while ((match = textPattern.exec(withoutScripts)) !== null) {
    pushCandidate(candidates, source, match.index + 1, 'text', match[1]);
  }
  return candidates;
}

function scanFile(relativePath) {
  const absolutePath = path.join(ROOT, relativePath);
  if (!fs.existsSync(absolutePath)) {
    return { path: relativePath, exists: false, candidates: [] };
  }
  const source = fs.readFileSync(absolutePath, 'utf8');
  const extension = path.extname(relativePath).toLowerCase();
  const candidates = extension === '.html'
    ? scanHtml(source)
    : scanJavaScript(source);
  return {
    path: relativePath,
    exists: true,
    candidates,
  };
}

function loadInventory() {
  return JSON.parse(fs.readFileSync(INVENTORY_PATH, 'utf8'));
}

function buildReport(inventory = loadInventory()) {
  const seen = new Map();
  const surfaces = inventory.surfaces.map((surface) => {
    const files = surface.files.map((relativePath) => {
      if (seen.has(relativePath)) {
        throw new Error(
          `Inventory file ${relativePath} is assigned to both ${seen.get(relativePath)} and ${surface.id}`,
        );
      }
      seen.set(relativePath, surface.id);
      if (surface.scanMode === 'localized-text') return scanFile(relativePath);
      return {
        path: relativePath,
        exists: fs.existsSync(path.join(ROOT, relativePath)),
        candidates: [],
      };
    });
    const hanCandidates = files.reduce((sum, file) => sum + file.candidates.length, 0);
    return {
      id: surface.id,
      label: surface.label,
      scanMode: surface.scanMode,
      baselineHanCandidates: surface.baselineHanCandidates ?? null,
      hanCandidates,
      missingFiles: files.filter((file) => !file.exists).map((file) => file.path),
      files: files.map((file) => ({
        path: file.path,
        exists: file.exists,
        hanCandidates: file.candidates.length,
        candidates: file.candidates,
      })),
    };
  });
  return {
    schemaVersion: inventory.schemaVersion,
    requiredLocales: inventory.requiredLocales,
    generatedAt: new Date().toISOString(),
    totalHanCandidates: surfaces.reduce((sum, surface) => sum + surface.hanCandidates, 0),
    surfaces,
  };
}

function validateReport(report) {
  const failures = [];
  for (const surface of report.surfaces) {
    for (const missingFile of surface.missingFiles) {
      failures.push(`${surface.id}: missing file ${missingFile}`);
    }
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
  }
  return failures;
}

function printSummary(report) {
  console.log(`I18N surface inventory: ${report.totalHanCandidates} Han candidates`);
  for (const surface of report.surfaces) {
    const baseline = Number.isInteger(surface.baselineHanCandidates)
      ? ` / baseline ${surface.baselineHanCandidates}`
      : '';
    console.log(`- ${surface.id}: ${surface.hanCandidates}${baseline}`);
    for (const file of surface.files) {
      if (surface.scanMode === 'localized-text') {
        console.log(`  ${file.path}: ${file.hanCandidates}`);
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
  buildReport,
  loadInventory,
  scanFile,
  scanHtml,
  scanJavaScript,
  validateReport,
};
