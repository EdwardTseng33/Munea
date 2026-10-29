#!/usr/bin/env node
// 版號回寫工具（2026-10-29）：把 iOS 版號／Build 一次寫進所有正本位置，
// 不再靠 Mac 打包端手動回寫——這正是版號常常漂移（1.0.46～1.0.50、1.0.54 都發生過）的根因。
//
// 寫入位置：
//   1. package.json          version
//   2. package-lock.json     version（根層）＋ packages[""].version
//   3. web/src/version.js    current（＋在沒有這個版號的 changelog 記錄時補一筆最小項目）
//   4. ios/App/App.xcodeproj/project.pbxproj  MARKETING_VERSION（全部出現處）
//                                              CURRENT_PROJECT_VERSION（全部出現處）
//
// 寫完務必接著跑：node scripts/check-release-consistency.js --strict-ios
//
// 用法：
//   node scripts/appstore/set-ios-release-version.mjs --version 1.0.70 --build 541 \
//     [--whats-new-file app-store/localizations/zh-Hant.json] [--dry-run]
'use strict';

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..');

function argValue(name, fallback) {
  const idx = process.argv.indexOf(name);
  return idx >= 0 && process.argv[idx + 1] !== undefined ? process.argv[idx + 1] : fallback;
}

const VERSION = argValue('--version');
const BUILD = argValue('--build');
const WHATS_NEW_FILE = argValue('--whats-new-file');
const DRY_RUN = process.argv.includes('--dry-run');

if (!VERSION || !/^\d+\.\d+\.\d+$/.test(VERSION)) {
  console.error('FAIL --version is required and must look like 1.0.70');
  process.exit(1);
}
if (!BUILD || !/^\d+$/.test(BUILD)) {
  console.error('FAIL --build is required and must be a plain integer, e.g. 541');
  process.exit(1);
}

function readText(relativePath) {
  return fs.readFileSync(path.join(ROOT, relativePath), 'utf8');
}
function writeText(relativePath, content) {
  if (DRY_RUN) {
    console.log(`DRY-RUN would write: ${relativePath}`);
    return;
  }
  fs.writeFileSync(path.join(ROOT, relativePath), content, 'utf8');
  console.log(`wrote: ${relativePath}`);
}

// 1. package.json
{
  const relativePath = 'package.json';
  const json = JSON.parse(readText(relativePath));
  json.version = VERSION;
  writeText(relativePath, `${JSON.stringify(json, null, 2)}\n`);
}

// 2. package-lock.json
{
  const relativePath = 'package-lock.json';
  const json = JSON.parse(readText(relativePath));
  json.version = VERSION;
  if (json.packages && json.packages[''] && typeof json.packages[''] === 'object') {
    json.packages[''].version = VERSION;
  }
  writeText(relativePath, `${JSON.stringify(json, null, 2)}\n`);
}

// 3. web/src/version.js
{
  const relativePath = 'web/src/version.js';
  let source = readText(relativePath);

  const currentPattern = /current\s*:\s*['"][^'"]+['"]/;
  if (!currentPattern.test(source)) {
    console.error(`FAIL could not find "current:" field in ${relativePath}`);
    process.exit(1);
  }
  source = source.replace(currentPattern, `current: '${VERSION}'`);

  const alreadyRecorded = new RegExp(`version\s*:\s*['"]${VERSION.replace(/\./g, '\.')}['"]`).test(source);
  if (!alreadyRecorded) {
    let whatsNewTitle = `iOS ${VERSION} (Build ${BUILD}) 發布流程自動建立的最小紀錄`;
    if (WHATS_NEW_FILE) {
      try {
        const meta = JSON.parse(readText(WHATS_NEW_FILE));
        if (meta.whatsNew) whatsNewTitle = String(meta.whatsNew);
      } catch (error) {
        console.warn(`WARN could not read --whats-new-file ${WHATS_NEW_FILE}: ${error.message}`);
      }
    }
    const titleLiteral = JSON.stringify(whatsNewTitle);
    const today = new Date().toISOString().slice(0, 10);
    const entry = `    {\n`
      + `      version: '${VERSION}',\n`
      + `      date: '${today}',\n`
      + `      title: ${titleLiteral},\n`
      + `      items: [\n`
      + `        '本筆由 iOS 發布流程自動建立以保持版號一致；完整更新內容請於合併前人工補上。',\n`
      + `      ],\n`
      + `    },\n`;
    const changelogMarker = /changelog\s*:\s*\[\n/;
    if (!changelogMarker.test(source)) {
      console.error(`FAIL could not find "changelog: [" in ${relativePath}`);
      process.exit(1);
    }
    source = source.replace(changelogMarker, (match) => `${match}${entry}`);
  } else {
    console.log(`web/src/version.js already has a changelog entry for ${VERSION}; left unchanged.`);
  }

  writeText(relativePath, source);
}

// 4. ios/App/App.xcodeproj/project.pbxproj
{
  const relativePath = 'ios/App/App.xcodeproj/project.pbxproj';
  let source = readText(relativePath);

  const marketingPattern = /MARKETING_VERSION\s*=\s*[^;]+;/g;
  const buildPattern = /CURRENT_PROJECT_VERSION\s*=\s*[^;]+;/g;
  const marketingCount = [...source.matchAll(marketingPattern)].length;
  const buildCount = [...source.matchAll(buildPattern)].length;
  if (marketingCount === 0 || buildCount === 0) {
    console.error(`FAIL could not find MARKETING_VERSION/CURRENT_PROJECT_VERSION in ${relativePath}`);
    process.exit(1);
  }
  source = source.replace(marketingPattern, `MARKETING_VERSION = ${VERSION};`);
  source = source.replace(buildPattern, `CURRENT_PROJECT_VERSION = ${BUILD};`);

  writeText(relativePath, source);
  console.log(`updated ${marketingCount} MARKETING_VERSION and ${buildCount} CURRENT_PROJECT_VERSION occurrence(s)`);
}

console.log(`${DRY_RUN ? 'DRY-RUN ' : ''}iOS release version set to ${VERSION} (Build ${BUILD}).`);
console.log('Next: node scripts/check-release-consistency.js --strict-ios');
