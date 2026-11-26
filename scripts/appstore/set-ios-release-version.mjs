#!/usr/bin/env node
// 版號回寫工具（2026-10-29）：把 iOS 版號／Build 一次寫進所有正本位置，
// 不再靠 Mac 打包端手動回寫——這正是版號常常漂移（1.0.46～1.0.50、1.0.54 都發生過）的根因。
//
// 寫入位置：
//   1. package.json          version
//   2. package-lock.json     version（根層）＋ packages[""].version
//   3. web/src/version.js    current（＋在沒有這個版號的 changelog 記錄時補一筆最小項目）
//      ⚠ changelog 的 title／items 會原樣顯示在 App「版本更新」畫面給用戶看：
//        這裡只准寫入給用戶看的更新說明（--whats-new-file 的 whatsNew），
//        「這筆是自動建立的、合併前請人工補」這類內部作業的話只能寫成註解。
//        （2026-11-17：以前把那句話寫進 items，1.0.70／1.0.71 的用戶都看到了。）
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

const DEFAULT_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..');

function argValue(name, fallback) {
  const idx = process.argv.indexOf(name);
  return idx >= 0 && process.argv[idx + 1] !== undefined ? process.argv[idx + 1] : fallback;
}

const VERSION = argValue('--version');
const BUILD = argValue('--build');
const WHATS_NEW_FILE = argValue('--whats-new-file');
const DRY_RUN = process.argv.includes('--dry-run');
// --root 只給守門測試用（在暫存資料夾裡跑，不碰真的版號檔）；平常不帶＝本程式庫根目錄。
const ROOT = path.resolve(argValue('--root', DEFAULT_ROOT));

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

  // 2026-11-17 修：這條判斷以前寫在樣板字串裡、反斜線沒寫成兩條（空白與句點的跳脫被吃掉），
  // 冒號後面有空格就永遠對不上＝每跑一次就再補一筆，1.0.71 因此在「版本更新」畫面重複出現兩次。
  const versionPattern = VERSION.replace(/\./g, '\\.');
  const alreadyRecorded = new RegExp(`version\\s*:\\s*['"]${versionPattern}['"]`).test(source);
  if (!alreadyRecorded) {
    // 沒給更新說明就留空白標題（畫面只顯示版號與日期），不把內部作業的話當標題給用戶看。
    let whatsNewTitle = '';
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
      + `      // 發布流程自動建立；要補細項請寫給用戶看的白話，內部備註只能留在註解。\n`
      + `      items: [],\n`
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
